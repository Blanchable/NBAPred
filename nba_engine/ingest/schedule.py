"""
Schedule module for fetching today's NBA games.

Uses nba_api live scoreboard, with fallback to NBA's static schedule API
when the live scoreboard hasn't updated yet (common before games start).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import time
import requests

# Import nba_api with clear error if missing (common issue in PyInstaller builds)
try:
    from nba_api.live.nba.endpoints import scoreboard
    NBA_API_AVAILABLE = True
except ImportError as e:
    NBA_API_AVAILABLE = False
    _NBA_API_ERROR = f"nba_api.live not available: {e}"
    scoreboard = None


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


def _fetch_from_static_schedule(target_date: str) -> list[Game]:
    """
    Fetch games from NBA's static season schedule API.
    
    This is a fallback when the live scoreboard hasn't updated yet.
    The schedule uses MM/DD/YYYY format for dates.
    
    Args:
        target_date: Date in YYYY-MM-DD format (e.g., "2026-02-03")
        
    Returns:
        List of Game objects for the target date.
    """
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    
    # Convert target_date (YYYY-MM-DD) to MM/DD/YYYY format (NBA's format)
    year, month, day = target_date.split("-")
    target_formatted = f"{month}/{day}/{year}"
    
    try:
        print(f"  Fetching from static schedule for {target_formatted}...")
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Cache-Control": "no-cache",
            }
        )
        response.raise_for_status()
        data = response.json()
        
        game_dates = data.get("leagueSchedule", {}).get("gameDates", [])
        games = []
        
        for game_date in game_dates:
            date_str = game_date.get("gameDate", "")
            # Check if this is our target date (format: "DD/MM/YYYY HH:MM:SS")
            if target_formatted in date_str:
                for g in game_date.get("games", []):
                    away = g.get("awayTeam", {})
                    home = g.get("homeTeam", {})
                    
                    game = Game(
                        game_id=g.get("gameId", ""),
                        away_team=away.get("teamTricode", ""),
                        home_team=home.get("teamTricode", ""),
                        start_time_utc=g.get("gameDateTimeUTC", None),
                    )
                    games.append(game)
                
                print(f"  ✓ Found {len(games)} games from static schedule")
                return games
        
        print(f"  No games found for {target_formatted} in static schedule")
        return []
        
    except Exception as e:
        print(f"  Failed to fetch static schedule: {e}")
        return []


def get_todays_games(
    max_retries: int = 3, 
    retry_delay: float = 2.0,
    require_current_date: bool = True,
) -> Tuple[list[Game], str, bool]:
    """
    Fetch today's NBA games from the live scoreboard or static schedule.
    
    First tries the live scoreboard. If the date doesn't match today's date
    (common before games start), falls back to the static season schedule.
    
    Args:
        max_retries: Maximum number of retry attempts on failure.
        retry_delay: Delay between retries in seconds.
        require_current_date: If True, validates that API date matches today.
    
    Returns:
        Tuple of (games_list, api_date, is_current_date)
    
    Raises:
        RuntimeError: If schedule fetch fails completely (for clear UI error messages)
    """
    expected_date = get_eastern_date()
    api_date = "Unknown"
    is_current = False
    
    # Check if nba_api is available
    if not NBA_API_AVAILABLE:
        print(f"  ERROR: {_NBA_API_ERROR}")
        # Try static schedule as fallback
        print(f"  Attempting static schedule fallback...")
        static_games = _fetch_from_static_schedule(expected_date)
        if static_games:
            return static_games, expected_date, True
        raise RuntimeError(f"Schedule fetch failed: {_NBA_API_ERROR}")
    
    # First, try the live scoreboard
    for attempt in range(max_retries):
        try:
            sb = scoreboard.ScoreBoard()
            data = sb.get_dict()
            
            scoreboard_data = data.get("scoreboard", {})
            api_date = scoreboard_data.get("gameDate", "Unknown")
            game_list = scoreboard_data.get("games", [])
            
            is_current = (api_date == expected_date)
            
            print(f"  NBA Live Scoreboard date: {api_date}")
            print(f"  Expected date (ET): {expected_date}")
            
            if is_current:
                print(f"  ✓ Date matches - using live scoreboard data")
                games = []
                for game_data in game_list:
                    game = Game(
                        game_id=game_data.get("gameId", ""),
                        away_team=game_data.get("awayTeam", {}).get("teamTricode", ""),
                        home_team=game_data.get("homeTeam", {}).get("teamTricode", ""),
                        start_time_utc=game_data.get("gameTimeUTC", None),
                    )
                    games.append(game)
                return games, api_date, is_current
            else:
                # Date mismatch - try static schedule as fallback
                print(f"  ⚠ Live scoreboard shows {api_date} (yesterday's games)")
                print(f"    Falling back to static schedule for {expected_date}...")
                
                static_games = _fetch_from_static_schedule(expected_date)
                if static_games:
                    return static_games, expected_date, True
                
                # If static schedule also fails, return what we have with warning
                print(f"  ⚠ WARNING: Could not find games for {expected_date}")
                print(f"    Returning yesterday's games from live scoreboard")
                
                games = []
                for game_data in game_list:
                    game = Game(
                        game_id=game_data.get("gameId", ""),
                        away_team=game_data.get("awayTeam", {}).get("teamTricode", ""),
                        home_team=game_data.get("homeTeam", {}).get("teamTricode", ""),
                        start_time_utc=game_data.get("gameTimeUTC", None),
                    )
                    games.append(game)
                return games, api_date, False
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(retry_delay)
            else:
                print(f"  Failed to fetch from live scoreboard: {e}")
                # Try static schedule as last resort
                print(f"  Attempting static schedule fallback...")
                static_games = _fetch_from_static_schedule(expected_date)
                if static_games:
                    return static_games, expected_date, True
                return [], api_date, False
    
    return [], api_date, False


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
