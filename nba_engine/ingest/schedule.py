"""
Schedule module for fetching today's NBA games.

Uses nba_api to fetch today's game slate from live scoreboard.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple
import time

from nba_api.live.nba.endpoints import scoreboard


@dataclass
class Game:
    """Represents a single NBA game."""
    game_id: str
    away_team: str
    home_team: str
    start_time_utc: Optional[str] = None


def get_eastern_date() -> str:
    """
    Get today's date in Eastern Time (what NBA uses).
    
    Returns:
        Date string in YYYY-MM-DD format.
    """
    from datetime import timezone
    
    # UTC now
    utc_now = datetime.now(timezone.utc)
    
    # Approximate Eastern Time (UTC-5 in winter, UTC-4 in summer)
    # Simple DST check: March-November is EDT (UTC-4), else EST (UTC-5)
    month = utc_now.month
    if 3 <= month <= 11:
        offset = -4  # EDT
    else:
        offset = -5  # EST
    
    eastern_now = utc_now + timedelta(hours=offset)
    return eastern_now.strftime("%Y-%m-%d")


def get_todays_games(
    max_retries: int = 3, 
    retry_delay: float = 2.0,
    require_current_date: bool = True,
) -> Tuple[list[Game], str, bool]:
    """
    Fetch today's NBA games from the live scoreboard.
    
    Args:
        max_retries: Maximum number of retry attempts on failure.
        retry_delay: Delay between retries in seconds.
        require_current_date: If True, validates that API date matches today.
    
    Returns:
        Tuple of (games_list, api_date, is_current_date)
    """
    games = []
    api_date = "Unknown"
    is_current = False
    
    for attempt in range(max_retries):
        try:
            sb = scoreboard.ScoreBoard()
            data = sb.get_dict()
            
            scoreboard_data = data.get("scoreboard", {})
            api_date = scoreboard_data.get("gameDate", "Unknown")
            game_list = scoreboard_data.get("games", [])
            
            # Check if API date matches today (Eastern Time)
            expected_date = get_eastern_date()
            is_current = (api_date == expected_date)
            
            print(f"  NBA API game date: {api_date}")
            print(f"  Expected date (ET): {expected_date}")
            
            if is_current:
                print(f"  ✓ Date matches - showing today's games")
            else:
                print(f"  ⚠ DATE MISMATCH - API is showing {api_date}, not {expected_date}")
                print(f"    This usually means:")
                print(f"    - It's early morning and the API hasn't updated yet")
                print(f"    - Try again after 10 AM Eastern Time")
            
            for game_data in game_list:
                game = Game(
                    game_id=game_data.get("gameId", ""),
                    away_team=game_data.get("awayTeam", {}).get("teamTricode", ""),
                    home_team=game_data.get("homeTeam", {}).get("teamTricode", ""),
                    start_time_utc=game_data.get("gameTimeUTC", None),
                )
                games.append(game)
            
            return games, api_date, is_current
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(retry_delay)
            else:
                print(f"  Failed to fetch games after {max_retries} attempts: {e}")
                return [], api_date, False
    
    return games, api_date, is_current


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
