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
]
