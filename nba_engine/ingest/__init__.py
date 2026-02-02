"""Ingest module for fetching NBA data (schedule, team stats, player stats, injuries)."""

from .schedule import (
    get_todays_games,
    get_current_season,
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
)
from .injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
    InjuryRow,
)

__all__ = [
    # Schedule
    "get_todays_games",
    "get_current_season",
    "Game",
    # Team stats
    "get_comprehensive_team_stats",
    "get_team_rest_days",
    "get_fallback_team_strength",
    "TeamStrength",
    # Player stats
    "get_player_stats",
    "calculate_team_availability",
    "PlayerImpact",
    # Injuries
    "find_latest_injury_pdf",
    "download_injury_pdf",
    "parse_injury_pdf",
    "InjuryRow",
]
