"""
Total Points Prediction Module

Predicts final scores and totals using:
1. Expected possessions (pace model)
2. Points per possession (PPP) for each team
3. Game-state adjustments
4. Variance-based margin bands

This module is additive to the existing winner prediction logic.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
import math


# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

# League averages (2024-25 season estimates)
LEAGUE_AVG_PACE = 99.5
LEAGUE_AVG_OFF_RTG = 114.0
LEAGUE_AVG_PPP = LEAGUE_AVG_OFF_RTG / 100  # 1.14

# Pace bounds
PACE_MIN = 92.0
PACE_MAX = 105.0
PACE_ADJ_MAX = 3.0

# PPP bounds
PPP_MIN = 0.95
PPP_MAX = 1.18
PPP_ADJ_MAX = 0.04

# Game-state adjustment bounds
TOTAL_ADJ_MAX = 6.0

# Variance band widths
BAND_LOW = 9
BAND_MED = 12
BAND_HIGH = 15

# Blowout/close game thresholds
MARGIN_BLOWOUT = 10.0
MARGIN_CLOSE = 4.0
WIN_PROB_BLOWOUT = 0.70


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class TotalsContext:
    """Context flags for game situation adjustments."""
    is_back_to_back_home: bool = False
    is_back_to_back_away: bool = False
    is_3_in_4_home: bool = False
    is_3_in_4_away: bool = False
    is_long_travel: bool = False
    is_altitude_game: bool = False  # Denver home games
    predicted_margin: float = 0.0
    win_prob: float = 0.5


@dataclass
class TotalsPrediction:
    """Complete totals prediction output for a game."""
    # Core predictions
    expected_possessions: float
    ppp_home: float
    ppp_away: float
    
    # Raw points (before adjustments)
    raw_home_points: float
    raw_away_points: float
    raw_total: float
    
    # Adjusted points (final predictions)
    predicted_home_points: float
    predicted_away_points: float
    predicted_total: float
    
    # Range bands
    variance_score: float
    band_width: int
    total_range_low: float
    total_range_high: float
    home_range_low: float = 0.0
    home_range_high: float = 0.0
    away_range_low: float = 0.0
    away_range_high: float = 0.0
    
    # Adjustments applied
    pace_adjustment: float = 0.0
    ppp_adj_home: float = 0.0
    ppp_adj_away: float = 0.0
    game_state_adjustment: float = 0.0
    
    # Debug/logging
    fallbacks_used: List[str] = field(default_factory=list)
    
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
        # Ensure displayed total matches sum of displayed team points
        return self.display_home_points + self.display_away_points
    
    @property
    def display_range(self) -> str:
        """Formatted range string for display."""
        return f"{round(self.total_range_low)}-{round(self.total_range_high)}"
    
    @property
    def display_score(self) -> str:
        """Formatted predicted score string."""
        return f"{self.display_away_points} - {self.display_home_points}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/export."""
        return {
            'expected_possessions': round(self.expected_possessions, 1),
            'ppp_home': round(self.ppp_home, 3),
            'ppp_away': round(self.ppp_away, 3),
            'predicted_home_points': round(self.predicted_home_points, 1),
            'predicted_away_points': round(self.predicted_away_points, 1),
            'predicted_total': round(self.predicted_total, 1),
            'total_range_low': round(self.total_range_low, 1),
            'total_range_high': round(self.total_range_high, 1),
            'variance_score': round(self.variance_score, 2),
            'band_width': self.band_width,
            'fallbacks_used': self.fallbacks_used,
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def safe_get(stats: dict, key: str, default: float, team: str = "", fallbacks: list = None) -> float:
    """
    Safely get a numeric value from stats dict, logging fallback usage.
    
    Args:
        stats: Dictionary of stats
        key: Key to look up
        default: Default value if not found
        team: Team identifier for logging
        fallbacks: List to append fallback info to
    
    Returns:
        Float value
    """
    val = stats.get(key)
    if val is None:
        if fallbacks is not None:
            fallbacks.append(f"{team}:{key}=league_avg({default})")
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        if fallbacks is not None:
            fallbacks.append(f"{team}:{key}=league_avg({default})")
        return default


def z_score(value: float, mean: float, std: float) -> float:
    """Calculate standardized z-score."""
    if std == 0:
        return 0.0
    return (value - mean) / std


def scale_to_range(value: float, max_abs: float) -> float:
    """Scale a value to be within [-max_abs, +max_abs]."""
    return clamp(value, -max_abs, max_abs)


# ============================================================================
# PART 1: EXPECTED POSSESSIONS (PACE) MODEL
# ============================================================================

def predict_possessions(
    home_stats: dict,
    away_stats: dict,
    context: TotalsContext = None,
    home_team: str = "",
    away_team: str = "",
    fallbacks: list = None,
) -> Tuple[float, float]:
    """
    Predict expected possessions for the game.
    
    Uses blended pace from both teams plus contextual adjustments.
    
    Args:
        home_stats: Home team stats dict
        away_stats: Away team stats dict
        context: Game context flags (optional)
        home_team: Home team name for logging
        away_team: Away team name for logging
        fallbacks: List to track fallback usage
    
    Returns:
        Tuple of (expected_possessions, pace_adjustment)
    """
    if fallbacks is None:
        fallbacks = []
    
    # Get team paces
    pace_home = safe_get(home_stats, 'pace', LEAGUE_AVG_PACE, home_team, fallbacks)
    pace_away = safe_get(away_stats, 'pace', LEAGUE_AVG_PACE, away_team, fallbacks)
    
    # Baseline: average of both teams' pace
    baseline_pace = 0.5 * pace_home + 0.5 * pace_away
    
    # Context adjustments
    pace_adj = 0.0
    
    if context is not None:
        # Back-to-back fatigue
        if context.is_back_to_back_home:
            pace_adj -= 0.8
        if context.is_back_to_back_away:
            pace_adj -= 0.8
        
        # 3-in-4 nights
        if context.is_3_in_4_home:
            pace_adj -= 0.6
        if context.is_3_in_4_away:
            pace_adj -= 0.6
        
        # Travel
        if context.is_long_travel:
            pace_adj -= 0.4
        
        # Altitude (Denver)
        if context.is_altitude_game:
            pace_adj -= 0.3
        
        # Blowout projection (games tend to slow down)
        if abs(context.predicted_margin) >= MARGIN_BLOWOUT:
            pace_adj -= 0.7
        # Close game projection (slightly faster with urgency)
        elif abs(context.predicted_margin) <= MARGIN_CLOSE:
            pace_adj += 0.2
    
    # Clamp adjustment
    pace_adj = clamp(pace_adj, -PACE_ADJ_MAX, PACE_ADJ_MAX)
    
    # Apply adjustment
    expected_pace = baseline_pace + pace_adj
    
    # Enforce realistic bounds
    expected_pace = clamp(expected_pace, PACE_MIN, PACE_MAX)
    
    return expected_pace, pace_adj


# ============================================================================
# PART 2: TEAM PPP MODEL
# ============================================================================

def predict_ppp(
    team_stats: dict,
    opp_stats: dict,
    team_name: str = "",
    opp_name: str = "",
    fallbacks: list = None,
) -> Tuple[float, float]:
    """
    Predict points per possession for a team against opponent.
    
    Uses offense/defense efficiency ratings plus small nudge factors.
    
    Args:
        team_stats: Offensive team stats
        opp_stats: Defensive opponent stats
        team_name: Team name for logging
        opp_name: Opponent name for logging
        fallbacks: List to track fallback usage
    
    Returns:
        Tuple of (final_ppp, ppp_adjustment)
    """
    if fallbacks is None:
        fallbacks = []
    
    # Get offensive and defensive ratings
    off_rtg = safe_get(team_stats, 'off_rating', LEAGUE_AVG_OFF_RTG, team_name, fallbacks)
    opp_def_rtg = safe_get(opp_stats, 'def_rating', LEAGUE_AVG_OFF_RTG, opp_name, fallbacks)
    
    # Convert to PPP
    off_ppp = off_rtg / 100
    opp_def_ppp = opp_def_rtg / 100
    
    # Base PPP: center around league average with offense/defense deviations
    # Strong offense (high off_rtg) increases PPP
    # Strong defense (LOW def_rtg) decreases PPP (they allow fewer points)
    # Note: Lower def_rtg = better defense = should decrease our PPP
    base_ppp = LEAGUE_AVG_PPP + (off_ppp - LEAGUE_AVG_PPP) + (opp_def_ppp - LEAGUE_AVG_PPP)
    
    # Small nudge factors
    ppp_adj = 0.0
    
    # Turnover nudge
    team_tov = safe_get(team_stats, 'tov_pct', 14.0, team_name, fallbacks)
    opp_tov_forced = safe_get(opp_stats, 'opp_tov_pct', 14.0, opp_name, fallbacks)
    
    # Higher opponent forced TOV rate hurts our PPP
    tov_edge = (team_tov - opp_tov_forced) / 100  # Normalize
    tov_nudge = scale_to_range(-tov_edge * 0.5, 0.015)  # Invert: high TOV = bad
    ppp_adj += tov_nudge
    
    # Free throw rate nudge
    team_ft_rate = safe_get(team_stats, 'ft_rate', 0.25, team_name, fallbacks)
    opp_opp_ft_rate = safe_get(opp_stats, 'opp_ft_rate', 0.25, opp_name, fallbacks)
    
    # Use league average if opp_ft_rate not available
    if 'opp_ft_rate' not in opp_stats:
        opp_opp_ft_rate = 0.25
    
    ft_edge = team_ft_rate - opp_opp_ft_rate
    ft_nudge = scale_to_range(ft_edge * 0.3, 0.015)
    ppp_adj += ft_nudge
    
    # eFG nudge (optional)
    team_efg = safe_get(team_stats, 'efg_pct', 0.52, team_name, fallbacks)
    opp_opp_efg = safe_get(opp_stats, 'opp_efg_pct', 0.52, opp_name, fallbacks)
    
    efg_edge = team_efg - opp_opp_efg
    efg_nudge = scale_to_range(efg_edge * 0.2, 0.015)
    ppp_adj += efg_nudge
    
    # Clamp total adjustment
    ppp_adj = clamp(ppp_adj, -PPP_ADJ_MAX, PPP_ADJ_MAX)
    
    # Final PPP
    final_ppp = base_ppp + ppp_adj
    final_ppp = clamp(final_ppp, PPP_MIN, PPP_MAX)
    
    return final_ppp, ppp_adj


# ============================================================================
# PART 3 & 4: CONVERT TO POINTS + GAME-STATE ADJUSTMENTS
# ============================================================================

def predict_points(
    expected_possessions: float,
    ppp_home: float,
    ppp_away: float,
    context: TotalsContext = None,
) -> Tuple[float, float, float, float]:
    """
    Convert possessions and PPP to predicted points with game-state adjustments.
    
    Args:
        expected_possessions: Predicted game possessions
        ppp_home: Home team PPP
        ppp_away: Away team PPP
        context: Game context for adjustments
    
    Returns:
        Tuple of (home_points, away_points, total, game_state_adjustment)
    """
    # Raw points
    raw_home = expected_possessions * ppp_home
    raw_away = expected_possessions * ppp_away
    raw_total = raw_home + raw_away
    
    # Game-state adjustments
    total_adj = 0.0
    
    if context is not None:
        # Blowout dampener (reduces totals - garbage time, less urgency)
        if context.win_prob >= 0.75:
            total_adj -= 4.0
        elif context.win_prob >= WIN_PROB_BLOWOUT:
            total_adj -= 3.0
        elif abs(context.predicted_margin) >= MARGIN_BLOWOUT:
            total_adj -= 2.0
        
        # Close-game foul inflation (increases totals - intentional fouls late)
        elif abs(context.predicted_margin) <= 2:
            total_adj += 3.0
        elif abs(context.predicted_margin) <= MARGIN_CLOSE:
            total_adj += 2.0
    
    # Clamp adjustment
    total_adj = clamp(total_adj, -TOTAL_ADJ_MAX, TOTAL_ADJ_MAX)
    
    # Apply adjustment proportionally
    adj_total = raw_total + total_adj
    
    if raw_total > 0:
        adj_home = raw_home + total_adj * (raw_home / raw_total)
        adj_away = raw_away + total_adj * (raw_away / raw_total)
    else:
        adj_home = raw_home
        adj_away = raw_away
    
    return adj_home, adj_away, adj_total, total_adj


# ============================================================================
# PART 5: VARIANCE SCORE -> RANGE BAND
# ============================================================================

def compute_variance_band(
    home_stats: dict,
    away_stats: dict,
    expected_possessions: float,
    home_team: str = "",
    away_team: str = "",
    fallbacks: list = None,
) -> Tuple[float, int]:
    """
    Compute variance score and determine margin band width.
    
    Higher variance = wider prediction range.
    
    Args:
        home_stats: Home team stats
        away_stats: Away team stats
        expected_possessions: Predicted possessions
        home_team: Home team name for logging
        away_team: Away team name for logging
        fallbacks: List to track fallback usage
    
    Returns:
        Tuple of (variance_score, band_width)
    """
    if fallbacks is None:
        fallbacks = []
    
    # League averages for z-score calculation
    AVG_3PA_RATE = 0.40
    STD_3PA_RATE = 0.05
    AVG_TOV_RATE = 14.0
    STD_TOV_RATE = 2.0
    AVG_FT_RATE = 0.25
    STD_FT_RATE = 0.04
    
    # Get stats
    home_3pa = safe_get(home_stats, 'fg3a_rate', AVG_3PA_RATE, home_team, fallbacks)
    away_3pa = safe_get(away_stats, 'fg3a_rate', AVG_3PA_RATE, away_team, fallbacks)
    home_tov = safe_get(home_stats, 'tov_pct', AVG_TOV_RATE, home_team, fallbacks)
    away_tov = safe_get(away_stats, 'tov_pct', AVG_TOV_RATE, away_team, fallbacks)
    home_ft = safe_get(home_stats, 'ft_rate', AVG_FT_RATE, home_team, fallbacks)
    away_ft = safe_get(away_stats, 'ft_rate', AVG_FT_RATE, away_team, fallbacks)
    
    # Calculate z-scores
    z_home_3pa = z_score(home_3pa, AVG_3PA_RATE, STD_3PA_RATE)
    z_away_3pa = z_score(away_3pa, AVG_3PA_RATE, STD_3PA_RATE)
    z_home_tov = z_score(home_tov, AVG_TOV_RATE, STD_TOV_RATE)
    z_away_tov = z_score(away_tov, AVG_TOV_RATE, STD_TOV_RATE)
    z_home_ft = z_score(home_ft, AVG_FT_RATE, STD_FT_RATE)
    z_away_ft = z_score(away_ft, AVG_FT_RATE, STD_FT_RATE)
    z_pace = z_score(abs(expected_possessions - LEAGUE_AVG_PACE), 0, 3.0)
    
    # Compute variance score
    # Higher 3PA rate increases variance (more volatile)
    # Higher TOV rate increases variance
    # Higher FT rate slightly decreases variance (more predictable)
    # Unusual pace increases variance
    variance_score = (
        0.40 * z_home_3pa + 0.40 * z_away_3pa +
        0.25 * z_home_tov + 0.25 * z_away_tov +
        0.20 * z_pace -
        0.15 * z_home_ft - 0.15 * z_away_ft
    )
    
    # Map to band width
    if variance_score <= -0.5:
        band = BAND_LOW
    elif variance_score >= 0.5:
        band = BAND_HIGH
    else:
        band = BAND_MED
    
    return variance_score, band


# ============================================================================
# MAIN PREDICTION FUNCTION
# ============================================================================

def predict_game_totals(
    home_team: str,
    away_team: str,
    home_stats: dict,
    away_stats: dict,
    predicted_margin: float = 0.0,
    win_prob: float = 0.5,
    home_rest_days: int = 1,
    away_rest_days: int = 1,
) -> TotalsPrediction:
    """
    Generate complete totals prediction for a game.
    
    Args:
        home_team: Home team identifier
        away_team: Away team identifier
        home_stats: Home team stats dict
        away_stats: Away team stats dict
        predicted_margin: Predicted point margin (positive = home favored)
        win_prob: Win probability for predicted winner
        home_rest_days: Days since home team's last game
        away_rest_days: Days since away team's last game
    
    Returns:
        TotalsPrediction object with all prediction data
    """
    fallbacks = []
    
    # Build context
    context = TotalsContext(
        is_back_to_back_home=(home_rest_days == 0),
        is_back_to_back_away=(away_rest_days == 0),
        is_3_in_4_home=(home_rest_days <= 1),  # Approximation
        is_3_in_4_away=(away_rest_days <= 1),
        is_altitude_game=(home_team == "DEN"),
        predicted_margin=predicted_margin,
        win_prob=win_prob,
    )
    
    # Part 1: Expected possessions
    expected_poss, pace_adj = predict_possessions(
        home_stats, away_stats, context, home_team, away_team, fallbacks
    )
    
    # Part 2: PPP for each team
    ppp_home, ppp_adj_home = predict_ppp(
        home_stats, away_stats, home_team, away_team, fallbacks
    )
    ppp_away, ppp_adj_away = predict_ppp(
        away_stats, home_stats, away_team, home_team, fallbacks
    )
    
    # Part 3 & 4: Convert to points with adjustments
    raw_home = expected_poss * ppp_home
    raw_away = expected_poss * ppp_away
    raw_total = raw_home + raw_away
    
    adj_home, adj_away, adj_total, game_adj = predict_points(
        expected_poss, ppp_home, ppp_away, context
    )
    
    # Part 5: Variance band
    variance_score, band_width = compute_variance_band(
        home_stats, away_stats, expected_poss, home_team, away_team, fallbacks
    )
    
    # Calculate ranges
    total_low = adj_total - band_width
    total_high = adj_total + band_width
    
    # Team-specific ranges (proportional to their share of total)
    if adj_total > 0:
        home_share = adj_home / adj_total
        away_share = adj_away / adj_total
    else:
        home_share = away_share = 0.5
    
    home_band = band_width * home_share
    away_band = band_width * away_share
    
    return TotalsPrediction(
        expected_possessions=expected_poss,
        ppp_home=ppp_home,
        ppp_away=ppp_away,
        raw_home_points=raw_home,
        raw_away_points=raw_away,
        raw_total=raw_total,
        predicted_home_points=adj_home,
        predicted_away_points=adj_away,
        predicted_total=adj_total,
        variance_score=variance_score,
        band_width=band_width,
        total_range_low=total_low,
        total_range_high=total_high,
        home_range_low=adj_home - home_band,
        home_range_high=adj_home + home_band,
        away_range_low=adj_away - away_band,
        away_range_high=adj_away + away_band,
        pace_adjustment=pace_adj,
        ppp_adj_home=ppp_adj_home,
        ppp_adj_away=ppp_adj_away,
        game_state_adjustment=game_adj,
        fallbacks_used=fallbacks,
    )


# ============================================================================
# BACKTEST / EVALUATION
# ============================================================================

@dataclass
class TotalsEvaluation:
    """Evaluation metrics for totals predictions."""
    n_games: int = 0
    mae_total: float = 0.0
    mae_home: float = 0.0
    mae_away: float = 0.0
    bias_total: float = 0.0
    pct_within_range: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'n_games': self.n_games,
            'mae_total': round(self.mae_total, 2),
            'mae_home': round(self.mae_home, 2),
            'mae_away': round(self.mae_away, 2),
            'bias_total': round(self.bias_total, 2),
            'pct_within_range': round(self.pct_within_range, 1),
        }
    
    def __str__(self) -> str:
        return (
            f"Totals Evaluation ({self.n_games} games):\n"
            f"  MAE Total: {self.mae_total:.2f}\n"
            f"  MAE Home: {self.mae_home:.2f}\n"
            f"  MAE Away: {self.mae_away:.2f}\n"
            f"  Bias Total: {self.bias_total:+.2f}\n"
            f"  % Within Range: {self.pct_within_range:.1f}%"
        )


def evaluate_totals(predictions_with_actuals: List[dict]) -> TotalsEvaluation:
    """
    Evaluate totals predictions against actual results.
    
    Args:
        predictions_with_actuals: List of dicts with:
            - predicted_home_points
            - predicted_away_points
            - predicted_total
            - total_range_low
            - total_range_high
            - actual_home_points
            - actual_away_points
            - actual_total
    
    Returns:
        TotalsEvaluation with computed metrics
    """
    if not predictions_with_actuals:
        return TotalsEvaluation()
    
    n = 0
    sum_abs_error_total = 0.0
    sum_abs_error_home = 0.0
    sum_abs_error_away = 0.0
    sum_error_total = 0.0
    within_range = 0
    
    for p in predictions_with_actuals:
        # Skip if missing required fields
        required = ['predicted_total', 'actual_total', 'total_range_low', 'total_range_high',
                    'predicted_home_points', 'actual_home_points',
                    'predicted_away_points', 'actual_away_points']
        
        if not all(k in p and p[k] is not None for k in required):
            continue
        
        n += 1
        
        pred_total = float(p['predicted_total'])
        actual_total = float(p['actual_total'])
        pred_home = float(p['predicted_home_points'])
        actual_home = float(p['actual_home_points'])
        pred_away = float(p['predicted_away_points'])
        actual_away = float(p['actual_away_points'])
        range_low = float(p['total_range_low'])
        range_high = float(p['total_range_high'])
        
        # Absolute errors
        sum_abs_error_total += abs(pred_total - actual_total)
        sum_abs_error_home += abs(pred_home - actual_home)
        sum_abs_error_away += abs(pred_away - actual_away)
        
        # Bias (directional error)
        sum_error_total += (pred_total - actual_total)
        
        # Within range check
        if range_low <= actual_total <= range_high:
            within_range += 1
    
    if n == 0:
        return TotalsEvaluation()
    
    return TotalsEvaluation(
        n_games=n,
        mae_total=sum_abs_error_total / n,
        mae_home=sum_abs_error_home / n,
        mae_away=sum_abs_error_away / n,
        bias_total=sum_error_total / n,
        pct_within_range=(within_range / n) * 100,
    )


def format_totals_summary(prediction: TotalsPrediction, away_team: str, home_team: str) -> str:
    """
    Format a human-readable summary of totals prediction.
    
    Args:
        prediction: TotalsPrediction object
        away_team: Away team name
        home_team: Home team name
    
    Returns:
        Formatted string summary
    """
    return (
        f"Predicted Score: {away_team} {prediction.display_away_points} - "
        f"{home_team} {prediction.display_home_points}\n"
        f"Total: {prediction.display_total} (range: {prediction.display_range})\n"
        f"Expected Possessions: {prediction.expected_possessions:.1f}\n"
        f"PPP: {away_team} {prediction.ppp_away:.3f}, {home_team} {prediction.ppp_home:.3f}\n"
        f"Variance: {prediction.variance_score:+.2f} (band: ±{prediction.band_width})"
    )
