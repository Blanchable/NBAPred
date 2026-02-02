"""Model module for NBA pregame predictions."""

from .point_system import (
    score_game,
    score_game_v3,
    GameScore,
    FactorResult,
    validate_system,
    FACTOR_WEIGHTS,
    FACTOR_NAMES,
)
from .lineup_adjustment import (
    calculate_lineup_adjusted_strength,
    calculate_game_confidence,
    LineupAdjustedStrength,
)
from .calibration import (
    PredictionLogger,
    PredictionRecord,
    edge_to_win_prob,
    edge_to_margin,
)

__all__ = [
    # Point system
    "score_game",
    "score_game_v3",
    "GameScore",
    "FactorResult",
    "validate_system",
    "FACTOR_WEIGHTS",
    "FACTOR_NAMES",
    # Lineup adjustment
    "calculate_lineup_adjusted_strength",
    "calculate_game_confidence",
    "LineupAdjustedStrength",
    # Calibration
    "PredictionLogger",
    "PredictionRecord",
    "edge_to_win_prob",
    "edge_to_margin",
]
