"""
V3 Point System for NBA Pregame Predictions.

Lineup-aware, matchup-sensitive prediction system with:
- 20 weighted factors (sum = 100)
- Lineup-adjusted team strength
- Home/road performance splits
- Recent form with guardrails
- Volatility-based confidence levels
- Calibrated win probabilities

Total weights sum to 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, tanh
from typing import Any, Optional
import re
import copy
import os

from .factor_debug import (
    DEBUG_FACTORS, DataSource, FactorDebugInfo, StatsWithProvenance,
    add_debug_info, clear_debug_info, validate_distinct_stats,
    ensure_distinct_copies, get_debug_summary,
)
from .totals_prediction import predict_game_totals, TotalsPrediction


# ============================================================================
# CONSTANTS AND WEIGHTS (V3)
# ============================================================================

# Factor weights (must sum to 100)
# V3.2: Simplified to reduce double counting and improve interpretability
# - Merged shot_quality + three_point_edge into shooting_advantage
# - Replaced free_throw_rate with free_throw_differential
# - Reduced defense and bench weights to avoid overlap with net rating
FACTOR_WEIGHTS = {
    "lineup_net_rating": 18,     # Primary team strength signal (softcapped)
    "star_impact": 7,            # Injury awareness
    "rotation_replacement": 5,   # Next-man-up quality
    "off_vs_def": 12,            # Matchup efficiency
    "turnover_diff": 6,          # Ball security
    "shooting_advantage": 8,     # Combined eFG + 3P (replaces shot_quality + three_point_edge)
    "free_throw_diff": 4,        # FT rate differential (replaces free_throw_rate)
    "rebounding": 6,             # Board control
    "home_road_split": 3,        # Home/road performance split
    "home_court": 4,             # Basic home advantage
    "rest_fatigue": 5,           # Rest days
    "rim_protection": 3,         # Interior defense (reduced to avoid overlap)
    "perimeter_defense": 2,      # Perimeter D (reduced to avoid overlap)
    "matchup_fit": 4,            # Style matchups
    "bench_depth": 3,            # Rotation quality (reduced to avoid net rating overlap)
    "pace_control": 2,           # Tempo advantage
    "late_game_creation": 3,     # Clutch proxy
    "variance_signal": 5,        # 3P reliance (affects confidence)
    "coaching": 0,               # Neutral (no data)
    "motivation": 0,             # Neutral (no data)
}

# Verify weights sum to 100
_weight_sum = sum(FACTOR_WEIGHTS.values())
assert _weight_sum == 100, f"Weights sum to {_weight_sum}, not 100"

# Factor display names
FACTOR_NAMES = {
    "lineup_net_rating": "Lineup Net Rating",
    "star_impact": "Star Impact",
    "rotation_replacement": "Rotation Replacement",
    "off_vs_def": "Off vs Def Efficiency",
    "turnover_diff": "Turnover Differential",
    "shooting_advantage": "Shooting Advantage",
    "free_throw_diff": "Free Throw Differential",
    "rebounding": "Rebounding",
    "home_road_split": "Home/Road Split",
    "home_court": "Home Court",
    "rest_fatigue": "Rest/Fatigue",
    "rim_protection": "Rim Protection",
    "perimeter_defense": "Perimeter Defense",
    "matchup_fit": "Matchup Fit",
    "bench_depth": "Bench Depth",
    "pace_control": "Pace Control",
    "late_game_creation": "Late Game Creation",
    "variance_signal": "Variance Signal",
    "coaching": "Coaching",
    "motivation": "Motivation",
}

# Scaling constants for normalization
SCALES = {
    "net_rating": 10.0,
    "off_vs_def": 10.0,
    "turnover": 4.0,
    "shooting": 0.06,       # Combined eFG + 3P scale (6% diff ~= max)
    "ftr": 0.12,            # FT rate differential scale
    "rebounding": 6.0,
    "home_road": 8.0,
    "pace": 6.0,
    "bench": 5.0,
    "rest": 2.0,
    "rim": 6.0,
    "perimeter": 6.0,
    "availability": 0.25,
}

# Edge score to margin mapping
# Edge scores typically range 15-30, we want margins 3-7
EDGE_TO_MARGIN = 4.5

# Margin to probability scale (flattened to reduce overconfidence)
# margin 0 -> 50%, margin 5 -> ~64%, margin 10 -> ~76%
MARGIN_PROB_SCALE = 8.8

# Probability clamps to prevent overconfidence (tightened)
PROB_MIN = 0.05
PROB_MAX = 0.93

# Confidence bucket thresholds (raised to reduce overconfidence)
# These define the boundaries for HIGH / MEDIUM / LOW confidence labels
# HIGH also requires multi-signal confirmation (see GameScore.strong_signal_count)
CONF_HIGH_MIN = 72.0   # confidence_pct >= 72.0 AND multi-signal -> HIGH
CONF_MED_MIN = 60.0    # confidence_pct >= 60.0 -> MEDIUM, else LOW


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FactorResult:
    """Result for a single factor calculation."""
    name: str
    display_name: str
    weight: int
    signed_value: float  # [-1, +1]
    contribution: float  # weight * signed_value
    inputs_used: str  # Description of inputs
    # New fields for provenance tracking
    home_raw: float = 0.0
    away_raw: float = 0.0
    home_fallback: bool = False
    away_fallback: bool = False


@dataclass
class GameScore:
    """Complete scoring result for a game."""
    away_team: str
    home_team: str
    edge_score_total: float
    home_win_prob: float
    away_win_prob: float
    projected_margin_home: float
    predicted_winner: str
    confidence: float  # Win probability of the chosen pick (0.0-1.0)
    home_power_rating: float = 0.0  # Team power rating (0-100)
    away_power_rating: float = 0.0
    factors: list[FactorResult] = field(default_factory=list)
    
    # Totals prediction fields
    expected_possessions: float = 0.0
    ppp_home: float = 0.0
    ppp_away: float = 0.0
    predicted_home_points: float = 0.0
    predicted_away_points: float = 0.0
    predicted_total: float = 0.0
    total_range_low: float = 0.0
    total_range_high: float = 0.0
    variance_score: float = 0.0
    totals_band_width: int = 12
    
    @property
    def pick_prob(self) -> float:
        """Get win probability of the predicted winner."""
        return self.confidence  # confidence IS the pick probability now
    
    @property
    def confidence_pct_value(self) -> float:
        """Get confidence as percentage float (0.0-100.0)."""
        return round(self.confidence * 100, 1)
    
    @property
    def confidence_pct(self) -> str:
        """Get confidence as percentage string."""
        return f"{self.confidence_pct_value:.1f}%"
    
    def strong_signal_count(self) -> int:
        """
        Count strong independent signals supporting the pick.
        
        Excludes lineup_net_rating, home_road_split, and home_court to avoid
        labeling games HIGH off a single dominant source.
        
        Returns:
            Number of strong (signed_value >= 0.35) independent signals
        """
        factor_map = {f.name: f for f in self.factors}
        
        def is_strong(name: str, thresh: float = 0.35) -> bool:
            f = factor_map.get(name)
            return (f is not None) and (f.signed_value >= thresh)
        
        count = 0
        
        # Efficiency, ball security
        if is_strong("off_vs_def"):
            count += 1
        if is_strong("turnover_diff"):
            count += 1
        
        # Shooting advantage (combined signal)
        if is_strong("shooting_advantage"):
            count += 1
        
        # Defense signals
        if is_strong("rim_protection"):
            count += 1
        if is_strong("perimeter_defense"):
            count += 1
        
        # Rebounding and bench stability
        if is_strong("rebounding"):
            count += 1
        if is_strong("bench_depth"):
            count += 1
        
        return count
    
    @property
    def confidence_bucket(self) -> str:
        """
        Get confidence bucket label (HIGH / MEDIUM / LOW).
        
        HIGH requires both:
        1. confidence_pct >= CONF_HIGH_MIN (72%)
        2. At least 2 strong independent signals (multi-signal confirmation)
        
        This prevents HIGH labels driven mostly by net rating + home stacking.
        """
        pct = self.confidence_pct_value
        
        if pct >= CONF_HIGH_MIN:
            # Require multi-signal confirmation for HIGH
            if self.strong_signal_count() >= 2:
                return "HIGH"
            # Downgrade to MEDIUM if insufficient signal confirmation
            return "MEDIUM"
        elif pct >= CONF_MED_MIN:
            return "MEDIUM"
        else:
            return "LOW"
    
    @property
    def confidence_label(self) -> str:
        """
        Get confidence category label (for UI tagging).
        Based on configurable thresholds. Returns lowercase for CSS/tag usage.
        """
        return self.confidence_bucket.lower()
    
    @property
    def confidence_display(self) -> str:
        """Get formatted confidence display: '71.3% (HIGH)'."""
        return f"{self.confidence_pct} ({self.confidence_bucket})"
    
    @property
    def top_5_factors_str(self) -> str:
        """Get string of top 5 contributing factors."""
        sorted_factors = sorted(
            self.factors,
            key=lambda f: abs(f.contribution),
            reverse=True
        )[:5]
        
        parts = []
        for f in sorted_factors:
            if f.contribution != 0:
                sign = "+" if f.contribution >= 0 else ""
                parts.append(f"{f.display_name}:{sign}{f.contribution:.1f}")
        
        return ", ".join(parts) if parts else "No factors"
    
    # Totals display properties
    @property
    def display_home_points(self) -> int:
        """Rounded home points for display."""
        return round(self.predicted_home_points)
    
    @property
    def display_away_points(self) -> int:
        """Rounded away points for display."""
        return round(self.predicted_away_points)
    
    @property
    def display_total(self) -> int:
        """Rounded total for display (ensures sum consistency)."""
        return self.display_home_points + self.display_away_points
    
    @property
    def display_predicted_score(self) -> str:
        """Formatted predicted score string: 'AWAY 108 - HOME 114'."""
        return f"{self.away_team} {self.display_away_points} - {self.home_team} {self.display_home_points}"
    
    @property
    def display_total_range(self) -> str:
        """Formatted total range string: '210-234'."""
        return f"{round(self.total_range_low)}-{round(self.total_range_high)}"
    
    @property
    def display_total_with_range(self) -> str:
        """Formatted total with range: '222 (210-234)'."""
        return f"{self.display_total} ({self.display_total_range})"


# ============================================================================
# PICK DECISION LOGIC
# ============================================================================

# Edge tie threshold - below this, use probability as tie-breaker
EDGE_TIE_THRESHOLD = 0.5


def decide_pick(
    edge_score_total: float,
    home_team: str,
    away_team: str,
    home_win_prob: float,
    away_win_prob: float,
) -> tuple[str, float]:
    """
    Decide the predicted winner based on EDGE, not probability.
    
    PICK is determined by edge_score_total sign:
    - Positive edge -> Home team
    - Negative edge -> Away team
    - Near-zero edge -> Use probability as tie-breaker
    
    Args:
        edge_score_total: The edge score (positive = home advantage)
        home_team: Home team abbreviation
        away_team: Away team abbreviation
        home_win_prob: Model's home win probability
        away_win_prob: Model's away win probability
    
    Returns:
        Tuple of (predicted_winner, pick_probability)
    """
    if edge_score_total > EDGE_TIE_THRESHOLD:
        # Edge favors home team
        return home_team, home_win_prob
    elif edge_score_total < -EDGE_TIE_THRESHOLD:
        # Edge favors away team
        return away_team, away_win_prob
    else:
        # Edge is in tie range - use probability as tie-breaker
        if home_win_prob >= away_win_prob:
            return home_team, home_win_prob
        else:
            return away_team, away_win_prob


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def clamp(value: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
    """Clamp value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


# Softcap scales (prevents saturation at exactly +/-1.0)
# These values make typical deltas land around 0.2-0.7, not 1.0
NET_RATING_SOFTCAP = 12.0
HOME_ROAD_SOFTCAP = 10.0


def softcap_tanh(value: float, scale: float) -> float:
    """
    Smoothly compress value to (-1, 1) without hard clipping.
    Prevents frequent saturation at exactly +/-1.0.
    
    Args:
        value: The raw delta value to compress
        scale: The scale factor (larger = more gradual compression)
    
    Returns:
        Compressed value in range (-1, 1)
    """
    if scale <= 0:
        return clamp(value)
    return tanh(value / scale)


def safe_get(stats: dict, key: str, default: float = 0.0) -> float:
    """Safely get a numeric value from stats dict."""
    val = stats.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_get_with_fallback(
    stats: dict, 
    key: str, 
    default: float,
    team: str = "",
) -> tuple[float, bool, str]:
    """
    Safely get a numeric value from stats dict, tracking if fallback was used.
    
    Returns:
        Tuple of (value, fallback_used, source_description)
    """
    val = stats.get(key)
    
    if val is None:
        return default, True, f"fallback({default})"
    
    try:
        float_val = float(val)
        # Check if value looks like a default/fallback (exact match to common defaults)
        common_defaults = {0.52, 0.36, 0.40, 0.25, 14.0, 25.0, 100.0, 110.0}
        is_likely_default = float_val in common_defaults
        source = "api" if not is_likely_default else f"api({float_val})"
        return float_val, False, source
    except (ValueError, TypeError):
        return default, True, f"fallback({default})"


def edge_to_margin(edge_score: float, scale: float = EDGE_TO_MARGIN) -> float:
    """
    Convert edge score to projected point margin.
    
    Args:
        edge_score: Total edge score from factors (-100 to +100 range).
        scale: Divisor to convert to margin (default 4.5).
    
    Returns:
        Projected margin in points.
    """
    return edge_score / scale


def margin_to_win_prob(margin: float, scale: float = MARGIN_PROB_SCALE) -> float:
    """
    Convert projected margin to win probability using logistic function.
    
    This is the CANONICAL probability calculation. Probabilities should
    always be derived from margin, not from edge score directly.
    
    Reference probabilities:
        margin  0 -> 50%
        margin  3 -> 60%
        margin  5 -> 67%
        margin  7 -> 73%
        margin 10 -> 81%
        margin 15 -> 89%
    
    Args:
        margin: Projected point margin (positive = home favored).
        scale: Controls steepness (default 7.0).
    
    Returns:
        Win probability clamped to [0.05, 0.95].
    """
    raw_prob = 1.0 / (1.0 + exp(-margin / scale))
    # Clamp to prevent overconfidence
    return max(PROB_MIN, min(PROB_MAX, raw_prob))


# Legacy function for backwards compatibility
def edge_to_win_prob(edge_score: float, scale: float = EDGE_TO_MARGIN) -> float:
    """
    DEPRECATED: Use margin_to_win_prob instead.
    
    This converts edge directly to probability via margin for compatibility.
    """
    margin = edge_to_margin(edge_score, scale)
    return margin_to_win_prob(margin)


def calculate_power_rating(
    net_rating: float,
    availability: float = 1.0,
) -> float:
    """
    Calculate team power rating on 0-100 scale.
    
    Based on net rating (-15 to +15 mapped to 0-100).
    """
    # Net rating typically ranges from -15 (worst) to +15 (best)
    # Map to 0-100 scale
    base = 50 + (net_rating * 2.5)  # -15 = 12.5, 0 = 50, +15 = 87.5
    
    # Adjust for availability
    adjusted = base * availability
    
    return max(0, min(100, adjusted))


# ============================================================================
# FACTOR CALCULATORS
# ============================================================================

def calc_lineup_net_rating(
    home_adjusted_net: float,
    away_adjusted_net: float,
) -> FactorResult:
    """
    Factor 1: Lineup-Adjusted Net Rating
    Uses lineup-adjusted ratings that account for injuries.
    
    Uses softcap_tanh to prevent saturation at exactly +/-1.0.
    """
    delta = home_adjusted_net - away_adjusted_net
    # Use softcap instead of hard clamp to prevent saturation
    signed_value = softcap_tanh(delta, NET_RATING_SOFTCAP)
    
    return FactorResult(
        name="lineup_net_rating",
        display_name=FACTOR_NAMES["lineup_net_rating"],
        weight=FACTOR_WEIGHTS["lineup_net_rating"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["lineup_net_rating"] * signed_value,
        inputs_used=f"Home:{home_adjusted_net:+.1f} Away:{away_adjusted_net:+.1f} (lineup-adjusted)",
    )


def calc_star_impact(
    home_players: list,
    away_players: list,
    home_injuries: list = None,
    away_injuries: list = None,
    context: dict = None,
) -> tuple[FactorResult, dict]:
    """
    Factor 2: Star Impact (9 points)
    Tiered star availability system.
    
    Tier A (top star) = 4 points
    Tier B (next 2 stars) = 2 points each
    """
    from .star_impact import compute_star_factor, format_star_detail
    
    signed_value, dampened_edge, detail = compute_star_factor(
        home_players, away_players,
        home_injuries, away_injuries,
        context,
    )
    
    weight = FACTOR_WEIGHTS["star_impact"]
    contribution = weight * signed_value
    
    inputs = format_star_detail(detail)
    
    return FactorResult(
        name="star_impact",
        display_name=FACTOR_NAMES["star_impact"],
        weight=weight,
        signed_value=signed_value,
        contribution=contribution,
        inputs_used=inputs,
    ), detail


def calc_rotation_replacement(
    home_players: list,
    away_players: list,
    home_tiers: dict,
    away_tiers: dict,
    home_injuries: list = None,
    away_injuries: list = None,
) -> tuple[FactorResult, dict]:
    """
    Factor 3: Rotation Replacement (4 points)
    Only activates when Tier A/B star is OUT or DOUBTFUL.
    Evaluates next-man-up quality.
    """
    from .rotation_replacement import compute_rotation_replacement, format_replacement_detail, REPLACEMENT_EDGE_CLAMP
    
    edge_points, detail = compute_rotation_replacement(
        home_players, away_players,
        home_tiers, away_tiers,
        home_injuries, away_injuries,
    )
    
    weight = FACTOR_WEIGHTS["rotation_replacement"]
    
    if detail.get("active"):
        signed_value = edge_points / REPLACEMENT_EDGE_CLAMP
        signed_value = max(-1.0, min(1.0, signed_value))
        contribution = weight * signed_value
    else:
        signed_value = 0.0
        contribution = 0.0
    
    inputs = format_replacement_detail(detail)
    
    return FactorResult(
        name="rotation_replacement",
        display_name=FACTOR_NAMES["rotation_replacement"],
        weight=weight,
        signed_value=signed_value,
        contribution=contribution,
        inputs_used=inputs,
    ), detail


def calc_star_availability_legacy(
    home_availability: float,
    away_availability: float,
    home_missing: list[str],
    away_missing: list[str],
) -> FactorResult:
    """
    DEPRECATED: Legacy star availability for backward compatibility.
    Use calc_star_impact instead for new code.
    """
    delta = home_availability - away_availability
    signed_value = clamp(delta / SCALES["availability"])
    
    home_str = f"{home_availability:.0%}"
    away_str = f"{away_availability:.0%}"
    
    missing_info = []
    if home_missing:
        missing_info.append(f"Home missing: {', '.join(home_missing[:2])}")
    if away_missing:
        missing_info.append(f"Away missing: {', '.join(away_missing[:2])}")
    
    inputs = f"Home:{home_str} Away:{away_str}"
    if missing_info:
        inputs += f" | {'; '.join(missing_info)}"
    
    return FactorResult(
        name="star_impact",
        display_name=FACTOR_NAMES["star_impact"],
        weight=FACTOR_WEIGHTS["star_impact"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["star_impact"] * signed_value,
        inputs_used=inputs,
    )


def calc_off_vs_def(
    home_off: float,
    home_def: float,
    away_off: float,
    away_def: float,
) -> FactorResult:
    """
    Factor 3: Off vs Def Efficiency (8 points)
    """
    home_edge = home_off - away_def
    away_edge = away_off - home_def
    delta = home_edge - away_edge
    signed_value = clamp(delta / SCALES["off_vs_def"])
    
    return FactorResult(
        name="off_vs_def",
        display_name=FACTOR_NAMES["off_vs_def"],
        weight=FACTOR_WEIGHTS["off_vs_def"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["off_vs_def"] * signed_value,
        inputs_used=f"HomeOff:{home_off:.1f} vs AwayDef:{away_def:.1f} | AwayOff:{away_off:.1f} vs HomeDef:{home_def:.1f}",
    )


def calc_turnover_diff(
    home_tov_pct: float,
    away_tov_pct: float,
    home_fallback: bool = False,
    away_fallback: bool = False,
) -> FactorResult:
    """Factor 4: Turnover Differential (7 points)"""
    delta = away_tov_pct - home_tov_pct  # Lower is better
    signed_value = clamp(delta / SCALES["turnover"])
    
    home_str = f"HomeTOV%:{home_tov_pct:.1f}"
    away_str = f"AwayTOV%:{away_tov_pct:.1f}"
    if home_fallback:
        home_str += " [FB]"
    if away_fallback:
        away_str += " [FB]"
    
    return FactorResult(
        name="turnover_diff",
        display_name=FACTOR_NAMES["turnover_diff"],
        weight=FACTOR_WEIGHTS["turnover_diff"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["turnover_diff"] * signed_value,
        inputs_used=f"{home_str} {away_str}",
        home_raw=home_tov_pct,
        away_raw=away_tov_pct,
        home_fallback=home_fallback,
        away_fallback=away_fallback,
    )


def calc_shooting_advantage(
    home_efg: float,
    away_efg: float,
    home_fg3_pct: float,
    away_fg3_pct: float,
    home_fallback: bool = False,
    away_fallback: bool = False,
) -> FactorResult:
    """
    Factor: Shooting Advantage (combined eFG + 3P)
    
    Merges shot_quality and three_point_edge to reduce double counting.
    Weights eFG more heavily (0.7) as it's the more comprehensive measure.
    """
    efg_delta = home_efg - away_efg
    three_delta = home_fg3_pct - away_fg3_pct
    
    # Combined shooting advantage (70% eFG, 30% 3P)
    combined = (0.7 * efg_delta) + (0.3 * three_delta)
    signed_value = clamp(combined / SCALES["shooting"])
    
    # Build inputs string
    home_str = f"HomeEFG:{home_efg:.1%} 3P:{home_fg3_pct:.1%}"
    away_str = f"AwayEFG:{away_efg:.1%} 3P:{away_fg3_pct:.1%}"
    if home_fallback:
        home_str += " [FB]"
    if away_fallback:
        away_str += " [FB]"
    
    return FactorResult(
        name="shooting_advantage",
        display_name=FACTOR_NAMES["shooting_advantage"],
        weight=FACTOR_WEIGHTS["shooting_advantage"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["shooting_advantage"] * signed_value,
        inputs_used=f"{home_str} | {away_str}",
        home_raw=home_efg,
        away_raw=away_efg,
        home_fallback=home_fallback,
        away_fallback=away_fallback,
    )


def calc_free_throw_diff(
    home_ft_rate: float,
    away_ft_rate: float,
    home_fallback: bool = False,
    away_fallback: bool = False,
) -> FactorResult:
    """
    Factor: Free Throw Differential
    
    Uses FT rate (FTA/FGA) differential between teams.
    Positive = home team gets to the line more often.
    """
    delta = home_ft_rate - away_ft_rate
    signed_value = clamp(delta / SCALES["ftr"])
    
    home_str = f"HomeFTr:{home_ft_rate:.3f}"
    away_str = f"AwayFTr:{away_ft_rate:.3f}"
    if home_fallback:
        home_str += " [FB]"
    if away_fallback:
        away_str += " [FB]"
    
    return FactorResult(
        name="free_throw_diff",
        display_name=FACTOR_NAMES["free_throw_diff"],
        weight=FACTOR_WEIGHTS["free_throw_diff"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["free_throw_diff"] * signed_value,
        inputs_used=f"{home_str} {away_str}",
        home_raw=home_ft_rate,
        away_raw=away_ft_rate,
        home_fallback=home_fallback,
        away_fallback=away_fallback,
    )


def calc_rebounding(
    home_oreb_pct: float,
    away_oreb_pct: float,
    home_fallback: bool = False,
    away_fallback: bool = False,
) -> FactorResult:
    """Factor 8: Rebounding Edge (6 points)"""
    delta = home_oreb_pct - away_oreb_pct
    signed_value = clamp(delta / SCALES["rebounding"])
    
    home_str = f"HomeOREB%:{home_oreb_pct:.1f}"
    away_str = f"AwayOREB%:{away_oreb_pct:.1f}"
    if home_fallback:
        home_str += " [FB]"
    if away_fallback:
        away_str += " [FB]"
    
    return FactorResult(
        name="rebounding",
        display_name=FACTOR_NAMES["rebounding"],
        weight=FACTOR_WEIGHTS["rebounding"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rebounding"] * signed_value,
        inputs_used=f"{home_str} {away_str}",
        home_raw=home_oreb_pct,
        away_raw=away_oreb_pct,
        home_fallback=home_fallback,
        away_fallback=away_fallback,
    )


def calc_home_road_split(
    home_home_net: float,
    away_road_net: float,
) -> FactorResult:
    """
    Factor 9: Home/Road Performance Split
    Uses actual home/road performance splits.
    
    Uses softcap_tanh to prevent saturation, and applies a 0.75 stacking gate
    to reduce double counting with home_court factor.
    """
    delta = home_home_net - away_road_net
    # Use softcap instead of hard clamp to prevent saturation
    signed_value = softcap_tanh(delta, HOME_ROAD_SOFTCAP)
    # Apply stacking gate to reduce double counting with home_court
    signed_value *= 0.75
    
    return FactorResult(
        name="home_road_split",
        display_name=FACTOR_NAMES["home_road_split"],
        weight=FACTOR_WEIGHTS["home_road_split"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["home_road_split"] * signed_value,
        inputs_used=f"HomeAtHome:{home_home_net:+.1f} AwayOnRoad:{away_road_net:+.1f}",
    )


def calc_home_court() -> FactorResult:
    """Factor 10: Basic Home Court (4 points) - Reduced in v3"""
    return FactorResult(
        name="home_court",
        display_name=FACTOR_NAMES["home_court"],
        weight=FACTOR_WEIGHTS["home_court"],
        signed_value=1.0,
        contribution=FACTOR_WEIGHTS["home_court"] * 1.0,
        inputs_used="Home team always +1",
    )


def calc_rest_fatigue(
    home_rest_days: int,
    away_rest_days: int,
) -> FactorResult:
    """Factor 11: Rest and Fatigue (5 points)"""
    delta = home_rest_days - away_rest_days
    signed_value = clamp(delta / SCALES["rest"])
    
    return FactorResult(
        name="rest_fatigue",
        display_name=FACTOR_NAMES["rest_fatigue"],
        weight=FACTOR_WEIGHTS["rest_fatigue"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rest_fatigue"] * signed_value,
        inputs_used=f"HomeRest:{home_rest_days}d AwayRest:{away_rest_days}d",
    )


def calc_rim_protection(
    home_def_rating: float,
    away_def_rating: float,
) -> FactorResult:
    """Factor 12: Rim Protection (4 points)"""
    delta = away_def_rating - home_def_rating  # Lower is better
    signed_value = clamp(delta / SCALES["rim"])
    
    return FactorResult(
        name="rim_protection",
        display_name=FACTOR_NAMES["rim_protection"],
        weight=FACTOR_WEIGHTS["rim_protection"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rim_protection"] * signed_value,
        inputs_used=f"HomeDef:{home_def_rating:.1f} AwayDef:{away_def_rating:.1f}",
    )


def calc_perimeter_defense(
    home_opp_fg3_pct: float,
    away_opp_fg3_pct: float,
    home_fallback: bool = False,
    away_fallback: bool = False,
) -> FactorResult:
    """Factor 13: Perimeter Defense (4 points)"""
    delta = (away_opp_fg3_pct - home_opp_fg3_pct) * 100  # Lower is better
    signed_value = clamp(delta / SCALES["perimeter"])
    
    home_str = f"HomeOpp3P%:{home_opp_fg3_pct:.1%}"
    away_str = f"AwayOpp3P%:{away_opp_fg3_pct:.1%}"
    if home_fallback:
        home_str += " [FB]"
    if away_fallback:
        away_str += " [FB]"
    
    return FactorResult(
        name="perimeter_defense",
        display_name=FACTOR_NAMES["perimeter_defense"],
        weight=FACTOR_WEIGHTS["perimeter_defense"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["perimeter_defense"] * signed_value,
        inputs_used=f"{home_str} {away_str}",
        home_raw=home_opp_fg3_pct,
        away_raw=away_opp_fg3_pct,
        home_fallback=home_fallback,
        away_fallback=away_fallback,
    )


def calc_matchup_fit(
    home_oreb_pct: float,
    home_fg3a_rate: float,
    away_oreb_pct: float,
    away_fg3a_rate: float,
) -> FactorResult:
    """Factor 14: Matchup Fit (4 points) - Four Factors style"""
    home_style = home_oreb_pct * away_fg3a_rate
    away_style = away_oreb_pct * home_fg3a_rate
    delta = home_style - away_style
    signed_value = clamp(delta / 4.0)
    
    return FactorResult(
        name="matchup_fit",
        display_name=FACTOR_NAMES["matchup_fit"],
        weight=FACTOR_WEIGHTS["matchup_fit"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["matchup_fit"] * signed_value,
        inputs_used="Four Factors style matchup",
    )


def calc_bench_depth(
    home_net: float,
    away_net: float,
) -> FactorResult:
    """Factor 15: Bench Depth (4 points)"""
    delta = (home_net - away_net) * 0.3
    signed_value = clamp(delta / SCALES["bench"])
    
    return FactorResult(
        name="bench_depth",
        display_name=FACTOR_NAMES["bench_depth"],
        weight=FACTOR_WEIGHTS["bench_depth"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["bench_depth"] * signed_value,
        inputs_used="Net rating proxy (scaled)",
    )


def calc_pace_control(
    home_pace: float,
    away_pace: float,
    home_fallback: bool = False,
    away_fallback: bool = False,
) -> FactorResult:
    """Factor 16: Pace Control (3 points)"""
    delta = home_pace - away_pace
    signed_value = clamp(delta / SCALES["pace"])
    
    home_str = f"HomePace:{home_pace:.1f}"
    away_str = f"AwayPace:{away_pace:.1f}"
    if home_fallback:
        home_str += " [FB]"
    if away_fallback:
        away_str += " [FB]"
    
    return FactorResult(
        name="pace_control",
        display_name=FACTOR_NAMES["pace_control"],
        weight=FACTOR_WEIGHTS["pace_control"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["pace_control"] * signed_value,
        inputs_used=f"{home_str} {away_str}",
        home_raw=home_pace,
        away_raw=away_pace,
        home_fallback=home_fallback,
        away_fallback=away_fallback,
    )


def calc_late_game_creation(
    home_off: float,
    away_off: float,
) -> FactorResult:
    """Factor 17: Late Game Creation (3 points)"""
    delta = (home_off - away_off) * 0.5
    signed_value = clamp(delta / 5.0)
    
    return FactorResult(
        name="late_game_creation",
        display_name=FACTOR_NAMES["late_game_creation"],
        weight=FACTOR_WEIGHTS["late_game_creation"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["late_game_creation"] * signed_value,
        inputs_used="Offensive rating proxy",
    )


def calc_coaching() -> FactorResult:
    """Factor 18: Coaching (0 points) - Neutral"""
    return FactorResult(
        name="coaching",
        display_name=FACTOR_NAMES["coaching"],
        weight=FACTOR_WEIGHTS["coaching"],
        signed_value=0.0,
        contribution=0.0,
        inputs_used="Neutral (no data)",
    )


def calc_variance_signal(
    home_fg3a_rate: float,
    away_fg3a_rate: float,
) -> FactorResult:
    """
    Factor: Variance Signal
    
    Measures 3P reliance differential. Less 3P reliance = more stable outcomes.
    """
    delta = away_fg3a_rate - home_fg3a_rate  # Less 3P reliance = more stable
    signed_value = clamp(delta / 0.10)
    
    return FactorResult(
        name="variance_signal",
        display_name=FACTOR_NAMES["variance_signal"],
        weight=FACTOR_WEIGHTS["variance_signal"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["variance_signal"] * signed_value,
        inputs_used=f"Home3PAr:{home_fg3a_rate:.1%} Away3PAr:{away_fg3a_rate:.1%}",
    )


def calc_motivation() -> FactorResult:
    """Factor 20: Motivation (0 points) - Neutral"""
    return FactorResult(
        name="motivation",
        display_name=FACTOR_NAMES["motivation"],
        weight=FACTOR_WEIGHTS["motivation"],
        signed_value=0.0,
        contribution=0.0,
        inputs_used="Neutral (no data)",
    )


# ============================================================================
# MAIN SCORING FUNCTION (V3)
# ============================================================================

def score_game_v3(
    home_team: str,
    away_team: str,
    home_strength,  # LineupAdjustedStrength or dict
    away_strength,  # LineupAdjustedStrength or dict
    home_stats: dict,
    away_stats: dict,
    home_rest_days: int = 1,
    away_rest_days: int = 1,
    home_players: list = None,
    away_players: list = None,
    home_injuries: list = None,
    away_injuries: list = None,
) -> GameScore:
    """
    Score a game using the v3 20-factor weighted point system.
    
    This version uses lineup-adjusted strengths, home/road splits,
    and the new tiered star impact system.
    """
    # CRITICAL: Ensure home_stats and away_stats are distinct objects
    # This prevents shared reference bugs
    home_stats, away_stats = ensure_distinct_copies(home_stats, away_stats)
    
    # Validate stats are distinct (log warnings if issues found)
    if DEBUG_FACTORS:
        warnings = validate_distinct_stats(home_team, away_team, home_stats, away_stats)
        for w in warnings:
            print(f"  [STATS_VALIDATION] {w}")
    
    # Extract strength values
    if hasattr(home_strength, 'adjusted_net_rating'):
        home_adj_net = home_strength.adjusted_net_rating
        home_availability = home_strength.availability_score
        home_missing = home_strength.missing_players
        home_confidence_penalty = home_strength.confidence_penalty
    else:
        home_adj_net = safe_get(home_stats, 'net_rating', 0)
        home_availability = 1.0
        home_missing = []
        home_confidence_penalty = 0.0
    
    if hasattr(away_strength, 'adjusted_net_rating'):
        away_adj_net = away_strength.adjusted_net_rating
        away_availability = away_strength.availability_score
        away_missing = away_strength.missing_players
        away_confidence_penalty = away_strength.confidence_penalty
    else:
        away_adj_net = safe_get(away_stats, 'net_rating', 0)
        away_availability = 1.0
        away_missing = []
        away_confidence_penalty = 0.0
    
    # Get stats with fallback tracking
    home_off, home_off_fb, _ = safe_get_with_fallback(home_stats, 'off_rating', 110, home_team)
    home_def, home_def_fb, _ = safe_get_with_fallback(home_stats, 'def_rating', 110, home_team)
    away_off, away_off_fb, _ = safe_get_with_fallback(away_stats, 'off_rating', 110, away_team)
    away_def, away_def_fb, _ = safe_get_with_fallback(away_stats, 'def_rating', 110, away_team)
    
    home_home_net = safe_get(home_stats, 'home_net_rating', home_adj_net + 2)
    away_road_net = safe_get(away_stats, 'road_net_rating', away_adj_net - 2)
    
    # Get advanced stats with fallback tracking
    home_tov, home_tov_fb, _ = safe_get_with_fallback(home_stats, 'tov_pct', 14, home_team)
    away_tov, away_tov_fb, _ = safe_get_with_fallback(away_stats, 'tov_pct', 14, away_team)
    
    home_efg, home_efg_fb, _ = safe_get_with_fallback(home_stats, 'efg_pct', 0.52, home_team)
    away_efg, away_efg_fb, _ = safe_get_with_fallback(away_stats, 'efg_pct', 0.52, away_team)
    
    home_fg3, home_fg3_fb, _ = safe_get_with_fallback(home_stats, 'fg3_pct', 0.36, home_team)
    away_fg3, away_fg3_fb, _ = safe_get_with_fallback(away_stats, 'fg3_pct', 0.36, away_team)
    
    home_fg3a_rate, home_fg3a_fb, _ = safe_get_with_fallback(home_stats, 'fg3a_rate', 0.40, home_team)
    away_fg3a_rate, away_fg3a_fb, _ = safe_get_with_fallback(away_stats, 'fg3a_rate', 0.40, away_team)
    
    home_ft_rate, home_ft_fb, _ = safe_get_with_fallback(home_stats, 'ft_rate', 0.25, home_team)
    away_ft_rate, away_ft_fb, _ = safe_get_with_fallback(away_stats, 'ft_rate', 0.25, away_team)
    
    home_oreb, home_oreb_fb, _ = safe_get_with_fallback(home_stats, 'oreb_pct', 25, home_team)
    away_oreb, away_oreb_fb, _ = safe_get_with_fallback(away_stats, 'oreb_pct', 25, away_team)
    
    home_opp_efg, home_opp_efg_fb, _ = safe_get_with_fallback(home_stats, 'opp_efg_pct', 0.52, home_team)
    away_opp_efg, away_opp_efg_fb, _ = safe_get_with_fallback(away_stats, 'opp_efg_pct', 0.52, away_team)
    
    home_pace, home_pace_fb, _ = safe_get_with_fallback(home_stats, 'pace', 100, home_team)
    away_pace, away_pace_fb, _ = safe_get_with_fallback(away_stats, 'pace', 100, away_team)
    
    # Debug logging for data provenance
    if DEBUG_FACTORS:
        print(f"\n[FACTOR_DEBUG] Game: {away_team} @ {home_team}")
        print(f"[FACTOR_DEBUG] home_stats id={id(home_stats)}, away_stats id={id(away_stats)}")
        print(f"[FACTOR_DEBUG] Stats comparison:")
        print(f"  efg_pct: home={home_efg:.4f} (fb={home_efg_fb}) away={away_efg:.4f} (fb={away_efg_fb}) diff={home_efg-away_efg:.4f}")
        print(f"  tov_pct: home={home_tov:.4f} (fb={home_tov_fb}) away={away_tov:.4f} (fb={away_tov_fb}) diff={home_tov-away_tov:.4f}")
        print(f"  oreb_pct: home={home_oreb:.4f} (fb={home_oreb_fb}) away={away_oreb:.4f} (fb={away_oreb_fb}) diff={home_oreb-away_oreb:.4f}")
        print(f"  pace: home={home_pace:.4f} (fb={home_pace_fb}) away={away_pace:.4f} (fb={away_pace_fb}) diff={home_pace-away_pace:.4f}")
    
    factors = []
    
    # Calculate all factors
    factors.append(calc_lineup_net_rating(home_adj_net, away_adj_net))
    
    # Star Impact and Rotation Replacement (new tiered system)
    if home_players and away_players:
        # Use new star impact system with player data
        star_factor, star_detail = calc_star_impact(
            home_players, away_players,
            home_injuries, away_injuries,
        )
        factors.append(star_factor)
        
        # Get tiers for rotation replacement
        from .star_impact import select_star_tiers
        home_tiers = select_star_tiers(home_players)
        away_tiers = select_star_tiers(away_players)
        
        # Rotation replacement (only activates for star absences)
        repl_factor, repl_detail = calc_rotation_replacement(
            home_players, away_players,
            home_tiers, away_tiers,
            home_injuries, away_injuries,
        )
        factors.append(repl_factor)
    else:
        # Fallback to legacy availability-based calculation
        factors.append(calc_star_availability_legacy(
            home_availability, away_availability,
            home_missing, away_missing
        ))
        # Add zero rotation replacement factor when no player data
        factors.append(FactorResult(
            name="rotation_replacement",
            display_name=FACTOR_NAMES["rotation_replacement"],
            weight=FACTOR_WEIGHTS["rotation_replacement"],
            signed_value=0.0,
            contribution=0.0,
            inputs_used="INACTIVE (no player data)",
        ))
    factors.append(calc_off_vs_def(home_off, home_def, away_off, away_def))
    factors.append(calc_turnover_diff(home_tov, away_tov, home_tov_fb, away_tov_fb))
    # Combined shooting factor (replaces shot_quality + three_point_edge)
    factors.append(calc_shooting_advantage(
        home_efg, away_efg, home_fg3, away_fg3,
        home_efg_fb or home_fg3_fb, away_efg_fb or away_fg3_fb
    ))
    factors.append(calc_free_throw_diff(home_ft_rate, away_ft_rate, home_ft_fb, away_ft_fb))
    factors.append(calc_rebounding(home_oreb, away_oreb, home_oreb_fb, away_oreb_fb))
    factors.append(calc_home_road_split(home_home_net, away_road_net))
    factors.append(calc_home_court())
    factors.append(calc_rest_fatigue(home_rest_days, away_rest_days))
    factors.append(calc_rim_protection(home_def, away_def))
    factors.append(calc_perimeter_defense(home_opp_efg, away_opp_efg, home_opp_efg_fb, away_opp_efg_fb))
    factors.append(calc_matchup_fit(
        home_oreb, home_fg3a_rate,
        away_oreb, away_fg3a_rate
    ))
    factors.append(calc_bench_depth(home_adj_net, away_adj_net))
    factors.append(calc_pace_control(home_pace, away_pace, home_pace_fb, away_pace_fb))
    factors.append(calc_late_game_creation(home_off, away_off))
    factors.append(calc_coaching())
    factors.append(calc_variance_signal(home_fg3a_rate, away_fg3a_rate))
    factors.append(calc_motivation())
    
    # Debug: Log factor debug info
    if DEBUG_FACTORS:
        for f in factors:
            if hasattr(f, 'home_raw') and f.home_raw != 0:
                info = FactorDebugInfo(
                    factor_name=f.name,
                    home_team=home_team,
                    away_team=away_team,
                    home_raw=f.home_raw,
                    away_raw=f.away_raw,
                    home_source=DataSource.FALLBACK_LEAGUE_AVG if f.home_fallback else DataSource.API_SEASON,
                    away_source=DataSource.FALLBACK_LEAGUE_AVG if f.away_fallback else DataSource.API_SEASON,
                    home_fallback=f.home_fallback,
                    away_fallback=f.away_fallback,
                    signed_value=f.signed_value,
                    contribution=f.contribution,
                )
                add_debug_info(info)
    
    # Sum contributions
    edge_score_total = sum(f.contribution for f in factors)
    
    # STEP 1: Convert edge score to projected margin
    projected_margin = edge_to_margin(edge_score_total)
    
    # STEP 2: Convert margin to win probability (NOT edge score!)
    # This prevents overconfident probabilities
    home_win_prob = margin_to_win_prob(projected_margin)
    away_win_prob = 1.0 - home_win_prob
    
    # Sanity check: warn if probability seems wrong
    if abs(projected_margin) < 6 and home_win_prob > 0.85:
        print(f"  Warning: margin={projected_margin:.1f} but prob={home_win_prob:.1%} - check calibration")
    
    # Determine predicted winner using EDGE (not probability!)
    # Confidence is the win probability of the chosen pick
    predicted_winner, confidence = decide_pick(
        edge_score_total=edge_score_total,
        home_team=home_team,
        away_team=away_team,
        home_win_prob=home_win_prob,
        away_win_prob=away_win_prob,
    )
    
    # Calculate power ratings
    home_power = calculate_power_rating(home_adj_net, home_availability)
    away_power = calculate_power_rating(away_adj_net, away_availability)
    
    # Calculate totals prediction
    totals = predict_game_totals(
        home_team=home_team,
        away_team=away_team,
        home_stats=home_stats,
        away_stats=away_stats,
        predicted_margin=projected_margin,
        win_prob=confidence,
        home_rest_days=home_rest_days,
        away_rest_days=away_rest_days,
    )
    
    # Log totals fallbacks if in debug mode
    if DEBUG_FACTORS and totals.fallbacks_used:
        print(f"  [TOTALS_FALLBACKS] {', '.join(totals.fallbacks_used)}")
    
    return GameScore(
        away_team=away_team,
        home_team=home_team,
        edge_score_total=round(edge_score_total, 2),
        home_win_prob=round(home_win_prob, 4),
        away_win_prob=round(away_win_prob, 4),
        projected_margin_home=round(projected_margin, 2),
        predicted_winner=predicted_winner,
        confidence=confidence,
        home_power_rating=round(home_power, 1),
        away_power_rating=round(away_power, 1),
        factors=factors,
        # Totals prediction fields
        expected_possessions=round(totals.expected_possessions, 1),
        ppp_home=round(totals.ppp_home, 3),
        ppp_away=round(totals.ppp_away, 3),
        predicted_home_points=totals.predicted_home_points,
        predicted_away_points=totals.predicted_away_points,
        predicted_total=totals.predicted_total,
        total_range_low=totals.total_range_low,
        total_range_high=totals.total_range_high,
        variance_score=round(totals.variance_score, 2),
        totals_band_width=totals.band_width,
    )


# Backwards compatibility
def score_game(
    home_team: str,
    away_team: str,
    team_stats: dict[str, dict],
    injuries: list = None,
    player_stats: dict = None,
    home_rest_days: int = 1,
    away_rest_days: int = 1,
) -> GameScore:
    """
    Legacy scoring function for backwards compatibility.
    Wraps score_game_v3 with simple stats dicts.
    """
    home_stats = team_stats.get(home_team, {})
    away_stats = team_stats.get(away_team, {})
    
    return score_game_v3(
        home_team=home_team,
        away_team=away_team,
        home_strength=None,
        away_strength=None,
        home_stats=home_stats,
        away_stats=away_stats,
        home_rest_days=home_rest_days,
        away_rest_days=away_rest_days,
    )


def validate_system():
    """Validate that the point system is correctly configured."""
    errors = []
    
    total = sum(FACTOR_WEIGHTS.values())
    if total != 100:
        errors.append(f"Weights sum to {total}, not 100")
    
    for key in FACTOR_WEIGHTS:
        if key not in FACTOR_NAMES:
            errors.append(f"Missing display name for factor: {key}")
    
    # Validate probability calibration
    calibration_errors = validate_probability_calibration()
    errors.extend(calibration_errors)
    
    return errors


def validate_probability_calibration():
    """
    Validate that probability calibration is producing reasonable values.
    
    Expected ranges:
        margin  0 -> ~50%
        margin  3 -> ~60%
        margin  5 -> ~67%
        margin 10 -> ~80%
    """
    errors = []
    
    # Test cases: (margin, expected_min, expected_max)
    test_cases = [
        (0, 0.48, 0.52),    # Even game -> ~50%
        (3, 0.55, 0.65),    # Small edge -> ~60%
        (5, 0.62, 0.72),    # Medium edge -> ~67%
        (10, 0.75, 0.87),   # Large edge -> ~80%
        (-5, 0.28, 0.38),   # Away favored -> ~33%
    ]
    
    for margin, exp_min, exp_max in test_cases:
        prob = margin_to_win_prob(margin)
        if not (exp_min <= prob <= exp_max):
            errors.append(
                f"Calibration error: margin={margin} gives prob={prob:.1%}, "
                f"expected {exp_min:.0%}-{exp_max:.0%}"
            )
    
    # Verify clamps work
    extreme_prob = margin_to_win_prob(50)  # Huge margin
    if extreme_prob > PROB_MAX:
        errors.append(f"Probability clamp not working: margin=50 gives {extreme_prob:.1%}")
    
    return errors


def print_calibration_table():
    """Print a reference table of margin -> probability mappings."""
    print("\nProbability Calibration Reference:")
    print("-" * 40)
    print(f"{'Margin':<10} {'Home Win %':<12} {'Away Win %':<12}")
    print("-" * 40)
    
    for margin in [-10, -7, -5, -3, 0, 3, 5, 7, 10, 15]:
        home_prob = margin_to_win_prob(margin)
        away_prob = 1.0 - home_prob
        print(f"{margin:>+6.1f}     {home_prob:>10.1%}   {away_prob:>10.1%}")
    
    print("-" * 40)
    print(f"Constants: EDGE_TO_MARGIN={EDGE_TO_MARGIN}, MARGIN_PROB_SCALE={MARGIN_PROB_SCALE}")
    print(f"Probability clamped to [{PROB_MIN:.0%}, {PROB_MAX:.0%}]")
    print()
