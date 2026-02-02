"""Model module for NBA pregame predictions."""

from .pregame import predict_games, GamePrediction

__all__ = [
    "predict_games",
    "GamePrediction",
]
