"""
Pregame prediction model for NBA games.

V1 uses a simple model based on team net ratings and home court advantage.
This module is structured to be easily extended with more sophisticated
prediction methods in future versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Any, Optional


# Model constants (v1 placeholders)
NET_SCALE = 0.5  # Maps per-100 possession rating to expected game margin
HOME_COURT_POINTS = 2.0  # Fixed home court advantage in points
PROB_SCALE = 7.0  # Controls steepness of win probability sigmoid


@dataclass
class GamePrediction:
    """Prediction output for a single game."""
    away_team: str
    home_team: str
    projected_margin_home: float
    home_win_prob: float
    away_win_prob: float
    start_time_utc: Optional[str] = None
    
    # Metadata for debugging/analysis
    home_net_rating: Optional[float] = None
    away_net_rating: Optional[float] = None


def predict_margin(
    home_net: float,
    away_net: float,
    net_scale: float = NET_SCALE,
    home_court: float = HOME_COURT_POINTS,
) -> float:
    """
    Calculate projected margin for home team.
    
    This function is the core prediction logic and can be replaced
    in future versions with a more sophisticated point-system scorer.
    
    Args:
        home_net: Home team's net rating (per 100 possessions).
        away_net: Away team's net rating (per 100 possessions).
        net_scale: Scaling factor for net rating difference.
        home_court: Home court advantage in points.
    
    Returns:
        Projected margin for home team (positive = home favored).
    """
    return (home_net - away_net) * net_scale + home_court


def margin_to_win_prob(
    margin: float,
    prob_scale: float = PROB_SCALE,
) -> float:
    """
    Convert projected margin to win probability using logistic function.
    
    Args:
        margin: Projected point margin (positive = favored).
        prob_scale: Controls the steepness of the probability curve.
    
    Returns:
        Win probability between 0 and 1.
    """
    return 1.0 / (1.0 + exp(-margin / prob_scale))


def predict_game(
    game: Any,
    ratings: dict[str, Any],
    default_net_rating: float = 0.0,
) -> GamePrediction:
    """
    Generate prediction for a single game.
    
    Args:
        game: Game object with team info (has home_team, away_team, start_time_utc).
        ratings: Dictionary of team ratings by abbreviation.
        default_net_rating: Default net rating if team not found.
    
    Returns:
        GamePrediction object with all prediction data.
    """
    # Get team ratings, defaulting to 0 if not found
    home_rating = ratings.get(game.home_team)
    away_rating = ratings.get(game.away_team)
    
    home_net = home_rating.net_rating if home_rating else default_net_rating
    away_net = away_rating.net_rating if away_rating else default_net_rating
    
    # Calculate projection
    margin = predict_margin(home_net, away_net)
    home_win_prob = margin_to_win_prob(margin)
    away_win_prob = 1.0 - home_win_prob
    
    return GamePrediction(
        away_team=game.away_team,
        home_team=game.home_team,
        projected_margin_home=round(margin, 2),
        home_win_prob=round(home_win_prob, 4),
        away_win_prob=round(away_win_prob, 4),
        start_time_utc=game.start_time_utc,
        home_net_rating=home_net,
        away_net_rating=away_net,
    )


def predict_games(
    games: list[Any],
    ratings: dict[str, Any],
    sort_by_home_prob: bool = True,
) -> list[GamePrediction]:
    """
    Generate predictions for multiple games.
    
    Args:
        games: List of Game objects.
        ratings: Dictionary of team ratings by abbreviation.
        sort_by_home_prob: If True, sort output by home_win_prob descending.
    
    Returns:
        List of GamePrediction objects.
    """
    predictions = [predict_game(game, ratings) for game in games]
    
    if sort_by_home_prob:
        predictions.sort(key=lambda p: p.home_win_prob, reverse=True)
    
    return predictions


# Future extension hooks

def predict_margin_with_points(
    home_net: float,
    away_net: float,
    home_injuries: list = None,
    away_injuries: list = None,
    # Additional factors for future point system
    **kwargs,
) -> float:
    """
    Future extension point for point-system based predictions.
    
    This function can be expanded to incorporate:
    - Injury impacts
    - Back-to-back adjustments
    - Travel factors
    - Matchup-specific adjustments
    - Historical head-to-head data
    
    Args:
        home_net: Home team's net rating.
        away_net: Away team's net rating.
        home_injuries: List of home team injuries (for future use).
        away_injuries: List of away team injuries (for future use).
        **kwargs: Additional factors for future expansion.
    
    Returns:
        Projected margin for home team.
    """
    # V1: Fall back to simple model
    base_margin = predict_margin(home_net, away_net)
    
    # TODO: Add point adjustments here in future versions
    # point_adjustment = calculate_injury_impact(home_injuries, away_injuries)
    # point_adjustment += calculate_rest_impact(...)
    # point_adjustment += calculate_travel_impact(...)
    
    return base_margin
