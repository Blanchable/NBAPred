"""Ingest module for fetching NBA data (schedule, team stats, player stats, injuries, availability)."""

from .schedule import (
    get_todays_games,
    get_current_season,
    get_eastern_date,
    Game,
)
from .team_stats import (
    get_comprehensive_team_stats,
    get_team_rest_days,
    get_fallback_team_strength,
    TeamStrength,
)
from .player_stats import (
    get_player_stats,
    calculate_team_availability,
    PlayerImpact,
    get_fallback_player_stats,
)
from .injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
    InjuryRow,
)
from .availability import (
    CanonicalStatus,
    STATUS_MULTIPLIERS,
    normalize_availability,
    normalize_player_name,
    names_match,
    PlayerAvailability,
    AvailabilityConfidence,
    TeamAvailabilityResult,
)
from .inactives import (
    fetch_game_inactives,
    fetch_all_game_inactives,
    merge_inactives_with_injuries,
    is_player_inactive,
    InactivePlayer,
)

__all__ = [
    # Schedule
    "get_todays_games",
    "get_current_season",
    "get_eastern_date",
    "Game",
    # Team stats
    "get_comprehensive_team_stats",
    "get_team_rest_days",
    "get_fallback_team_strength",
    "TeamStrength",
    # Player stats
    "get_player_stats",
    "calculate_team_availability",
    "get_fallback_player_stats",
    "PlayerImpact",
    # Injuries
    "find_latest_injury_pdf",
    "download_injury_pdf",
    "parse_injury_pdf",
    "InjuryRow",
    # Availability
    "CanonicalStatus",
    "STATUS_MULTIPLIERS",
    "normalize_availability",
    "normalize_player_name",
    "names_match",
    "PlayerAvailability",
    "AvailabilityConfidence",
    "TeamAvailabilityResult",
    # Inactives
    "fetch_game_inactives",
    "fetch_all_game_inactives",
    "merge_inactives_with_injuries",
    "is_player_inactive",
    "InactivePlayer",
]
