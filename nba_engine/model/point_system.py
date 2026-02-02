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
from math import exp
from typing import Any, Optional
import re


# ============================================================================
# CONSTANTS AND WEIGHTS (V3)
# ============================================================================

# Factor weights (must sum to 100)
# V3: Updated with home/road split replacing generic home court
FACTOR_WEIGHTS = {
    "lineup_net_rating": 14,     # Lineup-adjusted net rating
    "star_availability": 13,     # Injury impact on key players
    "off_vs_def": 8,             # Offensive vs defensive matchup
    "turnover_diff": 6,          # Ball security
    "shot_quality": 6,           # eFG% advantage
    "three_point_edge": 6,       # 3P shooting edge
    "free_throw_rate": 5,        # Getting to the line
    "rebounding": 5,             # Board control
    "home_road_split": 5,        # Home/road performance (NEW)
    "home_court": 4,             # Basic home advantage (reduced)
    "rest_fatigue": 5,           # Rest days
    "rim_protection": 4,         # Interior defense
    "perimeter_defense": 4,      # Perimeter D
    "matchup_fit": 3,            # Style matchup (Four Factors)
    "bench_depth": 4,            # Rotation quality
    "pace_control": 3,           # Tempo
    "late_game_creation": 3,     # Clutch proxy
    "coaching": 0,               # Neutral (no data)
    "shooting_variance": 2,      # 3P reliance (affects confidence)
    "motivation": 0,             # Neutral (no data)
}

# Verify weights sum to 100
_weight_sum = sum(FACTOR_WEIGHTS.values())
assert _weight_sum == 100, f"Weights sum to {_weight_sum}, not 100"

# Factor display names
FACTOR_NAMES = {
    "lineup_net_rating": "Lineup Net Rating",
    "star_availability": "Star Availability",
    "off_vs_def": "Off vs Def Efficiency",
    "turnover_diff": "Turnover Differential",
    "shot_quality": "Shot Quality",
    "three_point_edge": "3P Edge",
    "free_throw_rate": "Free Throw Rate",
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
    "coaching": "Coaching",
    "shooting_variance": "Shooting Variance",
    "motivation": "Motivation",
}

# Scaling constants for normalization
SCALES = {
    "net_rating": 10.0,
    "off_vs_def": 10.0,
    "turnover": 4.0,
    "shot_quality": 6.0,
    "three_point": 6.0,
    "ft_rate": 0.08,
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

# Margin to probability scale
# margin 0 -> 50%, margin 3 -> ~60%, margin 5 -> ~67%, margin 10 -> ~80%
MARGIN_PROB_SCALE = 7.0

# Probability clamps to prevent overconfidence
PROB_MIN = 0.05
PROB_MAX = 0.95


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
    confidence: str  # "high", "medium", "low"
    home_power_rating: float = 0.0  # Team power rating (0-100)
    away_power_rating: float = 0.0
    factors: list[FactorResult] = field(default_factory=list)
    
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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def clamp(value: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
    """Clamp value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def safe_get(stats: dict, key: str, default: float = 0.0) -> float:
    """Safely get a numeric value from stats dict."""
    val = stats.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


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
    Factor 1: Lineup-Adjusted Net Rating (14 points)
    Uses lineup-adjusted ratings that account for injuries.
    """
    delta = home_adjusted_net - away_adjusted_net
    signed_value = clamp(delta / SCALES["net_rating"])
    
    return FactorResult(
        name="lineup_net_rating",
        display_name=FACTOR_NAMES["lineup_net_rating"],
        weight=FACTOR_WEIGHTS["lineup_net_rating"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["lineup_net_rating"] * signed_value,
        inputs_used=f"Home:{home_adjusted_net:+.1f} Away:{away_adjusted_net:+.1f} (lineup-adjusted)",
    )


def calc_star_availability(
    home_availability: float,
    away_availability: float,
    home_missing: list[str],
    away_missing: list[str],
) -> FactorResult:
    """
    Factor 2: Star Availability (13 points)
    Impact of injuries on key players.
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
        name="star_availability",
        display_name=FACTOR_NAMES["star_availability"],
        weight=FACTOR_WEIGHTS["star_availability"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["star_availability"] * signed_value,
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
) -> FactorResult:
    """Factor 4: Turnover Differential (7 points)"""
    delta = away_tov_pct - home_tov_pct  # Lower is better
    signed_value = clamp(delta / SCALES["turnover"])
    
    return FactorResult(
        name="turnover_diff",
        display_name=FACTOR_NAMES["turnover_diff"],
        weight=FACTOR_WEIGHTS["turnover_diff"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["turnover_diff"] * signed_value,
        inputs_used=f"HomeTOV%:{home_tov_pct:.1f} AwayTOV%:{away_tov_pct:.1f}",
    )


def calc_shot_quality(
    home_efg: float,
    away_efg: float,
) -> FactorResult:
    """Factor 5: Shot Quality (7 points)"""
    delta = (home_efg - away_efg) * 100
    signed_value = clamp(delta / SCALES["shot_quality"])
    
    return FactorResult(
        name="shot_quality",
        display_name=FACTOR_NAMES["shot_quality"],
        weight=FACTOR_WEIGHTS["shot_quality"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["shot_quality"] * signed_value,
        inputs_used=f"HomeEFG:{home_efg:.1%} AwayEFG:{away_efg:.1%}",
    )


def calc_three_point_edge(
    home_fg3_pct: float,
    home_fg3a_rate: float,
    away_fg3_pct: float,
    away_fg3a_rate: float,
) -> FactorResult:
    """Factor 6: 3P Volume and Accuracy (7 points)"""
    home_score = home_fg3_pct * 100 + home_fg3a_rate * 20
    away_score = away_fg3_pct * 100 + away_fg3a_rate * 20
    delta = home_score - away_score
    signed_value = clamp(delta / SCALES["three_point"])
    
    return FactorResult(
        name="three_point_edge",
        display_name=FACTOR_NAMES["three_point_edge"],
        weight=FACTOR_WEIGHTS["three_point_edge"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["three_point_edge"] * signed_value,
        inputs_used=f"Home3P%:{home_fg3_pct:.1%} Away3P%:{away_fg3_pct:.1%}",
    )


def calc_free_throw_rate(
    home_ft_rate: float,
    away_ft_rate: float,
) -> FactorResult:
    """Factor 7: Free Throw Rate (6 points)"""
    delta = home_ft_rate - away_ft_rate
    signed_value = clamp(delta / SCALES["ft_rate"])
    
    return FactorResult(
        name="free_throw_rate",
        display_name=FACTOR_NAMES["free_throw_rate"],
        weight=FACTOR_WEIGHTS["free_throw_rate"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["free_throw_rate"] * signed_value,
        inputs_used=f"HomeFTr:{home_ft_rate:.3f} AwayFTr:{away_ft_rate:.3f}",
    )


def calc_rebounding(
    home_oreb_pct: float,
    away_oreb_pct: float,
) -> FactorResult:
    """Factor 8: Rebounding Edge (6 points)"""
    delta = home_oreb_pct - away_oreb_pct
    signed_value = clamp(delta / SCALES["rebounding"])
    
    return FactorResult(
        name="rebounding",
        display_name=FACTOR_NAMES["rebounding"],
        weight=FACTOR_WEIGHTS["rebounding"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rebounding"] * signed_value,
        inputs_used=f"HomeOREB%:{home_oreb_pct:.1f} AwayOREB%:{away_oreb_pct:.1f}",
    )


def calc_home_road_split(
    home_home_net: float,
    away_road_net: float,
) -> FactorResult:
    """
    Factor 9: Home/Road Performance Split (5 points) - NEW in v3
    Uses actual home/road performance splits.
    """
    delta = home_home_net - away_road_net
    signed_value = clamp(delta / SCALES["home_road"])
    
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
) -> FactorResult:
    """Factor 13: Perimeter Defense (4 points)"""
    delta = (away_opp_fg3_pct - home_opp_fg3_pct) * 100  # Lower is better
    signed_value = clamp(delta / SCALES["perimeter"])
    
    return FactorResult(
        name="perimeter_defense",
        display_name=FACTOR_NAMES["perimeter_defense"],
        weight=FACTOR_WEIGHTS["perimeter_defense"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["perimeter_defense"] * signed_value,
        inputs_used=f"HomeOpp3P%:{home_opp_fg3_pct:.1%} AwayOpp3P%:{away_opp_fg3_pct:.1%}",
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
) -> FactorResult:
    """Factor 16: Pace Control (3 points)"""
    delta = home_pace - away_pace
    signed_value = clamp(delta / SCALES["pace"])
    
    return FactorResult(
        name="pace_control",
        display_name=FACTOR_NAMES["pace_control"],
        weight=FACTOR_WEIGHTS["pace_control"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["pace_control"] * signed_value,
        inputs_used=f"HomePace:{home_pace:.1f} AwayPace:{away_pace:.1f}",
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


def calc_shooting_variance(
    home_fg3a_rate: float,
    away_fg3a_rate: float,
) -> FactorResult:
    """Factor 19: Shooting Variance (2 points)"""
    delta = away_fg3a_rate - home_fg3a_rate  # Less 3P reliance = more stable
    signed_value = clamp(delta / 0.10)
    
    return FactorResult(
        name="shooting_variance",
        display_name=FACTOR_NAMES["shooting_variance"],
        weight=FACTOR_WEIGHTS["shooting_variance"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["shooting_variance"] * signed_value,
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
) -> GameScore:
    """
    Score a game using the v3 20-factor weighted point system.
    
    This version uses lineup-adjusted strengths and home/road splits.
    """
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
    
    # Get stats
    home_off = safe_get(home_stats, 'off_rating', 110)
    home_def = safe_get(home_stats, 'def_rating', 110)
    away_off = safe_get(away_stats, 'off_rating', 110)
    away_def = safe_get(away_stats, 'def_rating', 110)
    
    home_home_net = safe_get(home_stats, 'home_net_rating', home_adj_net + 2)
    away_road_net = safe_get(away_stats, 'road_net_rating', away_adj_net - 2)
    
    factors = []
    
    # Calculate all 20 factors
    factors.append(calc_lineup_net_rating(home_adj_net, away_adj_net))
    factors.append(calc_star_availability(home_availability, away_availability, home_missing, away_missing))
    factors.append(calc_off_vs_def(home_off, home_def, away_off, away_def))
    factors.append(calc_turnover_diff(safe_get(home_stats, 'tov_pct', 14), safe_get(away_stats, 'tov_pct', 14)))
    factors.append(calc_shot_quality(safe_get(home_stats, 'efg_pct', 0.52), safe_get(away_stats, 'efg_pct', 0.52)))
    factors.append(calc_three_point_edge(
        safe_get(home_stats, 'fg3_pct', 0.36), safe_get(home_stats, 'fg3a_rate', 0.40),
        safe_get(away_stats, 'fg3_pct', 0.36), safe_get(away_stats, 'fg3a_rate', 0.40)
    ))
    factors.append(calc_free_throw_rate(safe_get(home_stats, 'ft_rate', 0.25), safe_get(away_stats, 'ft_rate', 0.25)))
    factors.append(calc_rebounding(safe_get(home_stats, 'oreb_pct', 25), safe_get(away_stats, 'oreb_pct', 25)))
    factors.append(calc_home_road_split(home_home_net, away_road_net))
    factors.append(calc_home_court())
    factors.append(calc_rest_fatigue(home_rest_days, away_rest_days))
    factors.append(calc_rim_protection(home_def, away_def))
    factors.append(calc_perimeter_defense(
        safe_get(home_stats, 'opp_efg_pct', 0.52), safe_get(away_stats, 'opp_efg_pct', 0.52)
    ))
    factors.append(calc_matchup_fit(
        safe_get(home_stats, 'oreb_pct', 25), safe_get(home_stats, 'fg3a_rate', 0.40),
        safe_get(away_stats, 'oreb_pct', 25), safe_get(away_stats, 'fg3a_rate', 0.40)
    ))
    factors.append(calc_bench_depth(home_adj_net, away_adj_net))
    factors.append(calc_pace_control(safe_get(home_stats, 'pace', 100), safe_get(away_stats, 'pace', 100)))
    factors.append(calc_late_game_creation(home_off, away_off))
    factors.append(calc_coaching())
    factors.append(calc_shooting_variance(
        safe_get(home_stats, 'fg3a_rate', 0.40), safe_get(away_stats, 'fg3a_rate', 0.40)
    ))
    factors.append(calc_motivation())
    
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
    
    # Determine predicted winner
    if home_win_prob > 0.5:
        predicted_winner = home_team
    else:
        predicted_winner = away_team
    
    # Calculate confidence level
    home_vol = safe_get(home_stats, 'volatility_score', 0.5)
    away_vol = safe_get(away_stats, 'volatility_score', 0.5)
    avg_volatility = (home_vol + away_vol) / 2
    
    injury_penalty = home_confidence_penalty + away_confidence_penalty
    edge_magnitude = abs(edge_score_total)
    
    confidence_score = (
        0.3 * (1 - min(1, injury_penalty))
        + 0.3 * (1 - avg_volatility)
        + 0.4 * min(1, edge_magnitude / 15)
    )
    
    if confidence_score >= 0.65:
        confidence = "high"
    elif confidence_score >= 0.40:
        confidence = "medium"
    else:
        confidence = "low"
    
    # Calculate power ratings
    home_power = calculate_power_rating(home_adj_net, home_availability)
    away_power = calculate_power_rating(away_adj_net, away_availability)
    
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
