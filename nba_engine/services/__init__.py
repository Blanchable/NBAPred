"""Services module for score fetching, grading, projections, and instability."""

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
from .instability import (
    compute_instability_map,
    build_rotation_signature,
    compute_instability,
    save_signatures,
    load_previous_signatures,
    instability_to_recency_weight,
    instability_bucket,
    instability_conf_mult,
    instability_netrating_mult,
    instability_score_penalty,
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
    'compute_instability_map',
    'build_rotation_signature',
    'compute_instability',
    'save_signatures',
    'load_previous_signatures',
    'instability_to_recency_weight',
    'instability_bucket',
    'instability_conf_mult',
    'instability_netrating_mult',
    'instability_score_penalty',
]
