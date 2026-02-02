"""
Schedule module for fetching today's NBA games.

Uses nba_api to fetch today's game slate from live scoreboard.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import time

from nba_api.live.nba.endpoints import scoreboard


@dataclass
class Game:
    """Represents a single NBA game."""
    game_id: str
    away_team: str
    home_team: str
    start_time_utc: Optional[str] = None


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
            game_date = scoreboard_data.get("gameDate", "Unknown")
            game_list = scoreboard_data.get("games", [])
            
            print(f"  NBA API game date: {game_date}")
            
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


def get_current_season() -> str:
    """
    Determine the current NBA season string based on today's date.
    
    Returns:
        Season string in format "YYYY-YY" (e.g., "2024-25").
    """
    today = datetime.now()
    year = today.year
    month = today.month
    
    if month < 10:
        start_year = year - 1
    else:
        start_year = year
    
    end_year = (start_year + 1) % 100
    return f"{start_year}-{end_year:02d}"
