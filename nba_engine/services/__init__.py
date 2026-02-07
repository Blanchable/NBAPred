"""Services module for score fetching, grading, and projections."""

from .scores import (
    ScoreProvider,
    NBALiveScoreProvider,
    fetch_scores_for_date,
    GameScoreUpdate,
)
from .grading import (
    grade_picks_for_date,
    grade_all_pending,
)
from .projections import (
    ProjectedPlayerLine,
    ProjectionMode,
    project_team_players,
    project_game,
    project_slate,
    status_to_multiplier,
    uncertainty_from_status,
)

__all__ = [
    'ScoreProvider',
    'NBALiveScoreProvider',
    'fetch_scores_for_date',
    'GameScoreUpdate',
    'grade_picks_for_date',
    'grade_all_pending',
    'ProjectedPlayerLine',
    'ProjectionMode',
    'project_team_players',
    'project_game',
    'project_slate',
    'status_to_multiplier',
    'uncertainty_from_status',
]
