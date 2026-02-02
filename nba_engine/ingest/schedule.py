"""
Schedule module for fetching today's NBA games and team statistics.

Uses nba_api to fetch:
- Today's game slate from live scoreboard
- Team ratings (offensive, defensive, net) from league stats
"""

from dataclasses import dataclass
from typing import Optional
import time

import pandas as pd
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import leaguedashteamstats


@dataclass
class Game:
    """Represents a single NBA game."""
    game_id: str
    away_team: str
    home_team: str
    start_time_utc: Optional[str] = None


@dataclass
class TeamRating:
    """Team offensive/defensive/net ratings and pace."""
    team_abbrev: str
    off_rating: float
    def_rating: float
    net_rating: float
    pace: float


def get_todays_games(max_retries: int = 3, retry_delay: float = 2.0) -> list[Game]:
    """
    Fetch today's NBA games from the live scoreboard.
    
    Args:
        max_retries: Maximum number of retry attempts on failure.
        retry_delay: Delay between retries in seconds.
    
    Returns:
        List of Game objects for today's slate.
    """
    games = []
    
    for attempt in range(max_retries):
        try:
            sb = scoreboard.ScoreBoard()
            data = sb.get_dict()
            
            scoreboard_data = data.get("scoreboard", {})
            game_list = scoreboard_data.get("games", [])
            
            for game_data in game_list:
                game = Game(
                    game_id=game_data.get("gameId", ""),
                    away_team=game_data.get("awayTeam", {}).get("teamTricode", ""),
                    home_team=game_data.get("homeTeam", {}).get("teamTricode", ""),
                    start_time_utc=game_data.get("gameTimeUTC", None),
                )
                games.append(game)
            
            return games
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(retry_delay)
            else:
                print(f"  Failed to fetch games after {max_retries} attempts: {e}")
                return []
    
    return games


def get_team_ratings(
    season: str = "2025-26",
    season_type: str = "Regular Season",
    max_retries: int = 3,
    retry_delay: float = 4.0,
    timeout: int = 60,
) -> dict[str, TeamRating]:
    """
    Fetch team ratings (per 100 possessions) from NBA stats API.
    
    Args:
        season: NBA season string (e.g., "2025-26").
        season_type: "Regular Season" or "Playoffs".
        max_retries: Maximum number of retry attempts on failure.
        retry_delay: Initial delay between retries in seconds (doubles each retry).
        timeout: Request timeout in seconds.
    
    Returns:
        Dictionary mapping team abbreviation to TeamRating object.
    """
    ratings = {}
    current_delay = retry_delay
    
    for attempt in range(max_retries):
        try:
            # Per100Possessions gives us proper offensive/defensive ratings
            stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star=season_type,
                per_mode_detailed="Per100Possessions",
                timeout=timeout,
            )
            
            df = stats.get_data_frames()[0]
            
            for _, row in df.iterrows():
                team_abbrev = row["TEAM_ABBREVIATION"]
                rating = TeamRating(
                    team_abbrev=team_abbrev,
                    off_rating=float(row.get("OFF_RATING", 0.0) or 0.0),
                    def_rating=float(row.get("DEF_RATING", 0.0) or 0.0),
                    net_rating=float(row.get("NET_RATING", 0.0) or 0.0),
                    pace=float(row.get("PACE", 100.0) or 100.0),
                )
                ratings[team_abbrev] = rating
            
            return ratings
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(current_delay)
                current_delay *= 2  # Exponential backoff
            else:
                print(f"  Failed to fetch team ratings after {max_retries} attempts: {e}")
                return {}
    
    return ratings


def get_current_season() -> str:
    """
    Determine the current NBA season string based on today's date.
    
    The NBA season spans two calendar years (e.g., 2025-26 season runs from
    October 2025 to June 2026).
    
    Returns:
        Season string in format "YYYY-YY" (e.g., "2025-26").
    """
    from datetime import datetime
    
    today = datetime.now()
    year = today.year
    month = today.month
    
    # NBA season typically starts in October
    # If we're in Jan-Sep, we're in the season that started the previous year
    if month < 10:
        start_year = year - 1
    else:
        start_year = year
    
    end_year = (start_year + 1) % 100  # Get last two digits
    return f"{start_year}-{end_year:02d}"
