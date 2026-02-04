"""Model module for NBA pregame predictions."""

from .point_system import (
    score_game,
    score_game_v3,
    GameScore,
    FactorResult,
    validate_system,
    validate_probability_calibration,
    print_calibration_table,
    margin_to_win_prob,
    edge_to_margin,
    FACTOR_WEIGHTS,
    FACTOR_NAMES,
    EDGE_TO_MARGIN,
    MARGIN_PROB_SCALE,
)
from .lineup_adjustment import (
    calculate_lineup_adjusted_strength,
    calculate_game_confidence,
    get_availability_debug_rows,
    LineupAdjustedStrength,
)
from .calibration import (
    PredictionLogger,
    PredictionRecord,
    edge_to_win_prob,
    edge_to_margin,
    margin_to_win_prob,
)
from .star_impact import (
    compute_star_factor,
    select_star_tiers,
    status_multiplier,
    team_star_points,
    star_edge_points,
    dampened_star_edge,
    TIER_A_POINTS,
    TIER_B_POINTS,
    STAR_EDGE_CLAMP,
)
from .rotation_replacement import (
    compute_rotation_replacement,
    star_absent,
    get_absent_stars,
    get_replacement_candidates,
    REPLACEMENT_EDGE_CLAMP,
)
from .totals_prediction import (
    predict_game_totals,
    predict_possessions,
    predict_ppp,
    predict_points,
    compute_variance_band,
    evaluate_totals,
    TotalsPrediction,
    TotalsContext,
    TotalsEvaluation,
    LEAGUE_AVG_PACE,
    LEAGUE_AVG_PPP,
)

__all__ = [
    # Point system
    "score_game",
    "score_game_v3",
    "GameScore",
    "FactorResult",
    "validate_system",
    "validate_probability_calibration",
    "print_calibration_table",
    "margin_to_win_prob",
    "edge_to_margin",
    "FACTOR_WEIGHTS",
    "FACTOR_NAMES",
    "EDGE_TO_MARGIN",
    "MARGIN_PROB_SCALE",
    # Lineup adjustment
    "calculate_lineup_adjusted_strength",
    "calculate_game_confidence",
    "get_availability_debug_rows",
    "LineupAdjustedStrength",
    # Calibration
    "PredictionLogger",
    "PredictionRecord",
    "edge_to_win_prob",
    # Star impact
    "compute_star_factor",
    "select_star_tiers",
    "status_multiplier",
    "team_star_points",
    "star_edge_points",
    "dampened_star_edge",
    "TIER_A_POINTS",
    "TIER_B_POINTS",
    "STAR_EDGE_CLAMP",
    # Rotation replacement
    "compute_rotation_replacement",
    "star_absent",
    "get_absent_stars",
    "get_replacement_candidates",
    "REPLACEMENT_EDGE_CLAMP",
    # Totals prediction
    "predict_game_totals",
    "predict_possessions",
    "predict_ppp",
    "predict_points",
    "compute_variance_band",
    "evaluate_totals",
    "TotalsPrediction",
    "TotalsContext",
    "TotalsEvaluation",
    "LEAGUE_AVG_PACE",
    "LEAGUE_AVG_PPP",
]
