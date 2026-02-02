"""
Schedule module for fetching today's NBA games and team statistics.

Uses nba_api to fetch:
- Today's game slate from live scoreboard
- Team ratings (offensive, defensive, net) from league stats
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import time

import requests
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import leaguedashteamstats


# Custom headers to avoid NBA API blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
}


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


def get_team_ratings(
    season: str = "2024-25",
    season_type: str = "Regular Season",
    max_retries: int = 3,
    retry_delay: float = 2.0,
    timeout: int = 120,
) -> dict[str, TeamRating]:
    """
    Fetch team ratings (per 100 possessions) from NBA stats API.
    
    Args:
        season: NBA season string (e.g., "2024-25").
        season_type: "Regular Season" or "Playoffs".
        max_retries: Maximum number of retry attempts on failure.
        retry_delay: Initial delay between retries in seconds.
        timeout: Request timeout in seconds.
    
    Returns:
        Dictionary mapping team abbreviation to TeamRating object.
    """
    ratings = {}
    
    # Try the direct API first with custom headers
    for attempt in range(max_retries):
        try:
            print(f"  Attempting to fetch ratings (attempt {attempt + 1}/{max_retries})...")
            
            # Use nba_api with longer timeout
            stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star=season_type,
                per_mode_detailed="Per100Possessions",
                timeout=timeout,
                headers=HEADERS,
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
            
            if ratings:
                print(f"  Successfully loaded {len(ratings)} team ratings.")
                return ratings
            
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
    
    # If API fails, use fallback ratings
    print("  Using fallback team ratings (approximate 2024-25 season data)...")
    return get_fallback_ratings()


def get_fallback_ratings() -> dict[str, TeamRating]:
    """
    Return fallback team ratings based on approximate 2024-25 season data.
    These are used when the NBA API is unavailable.
    
    Returns:
        Dictionary mapping team abbreviation to TeamRating object.
    """
    # Approximate net ratings based on 2024-25 season standings
    # Format: (off_rating, def_rating, net_rating, pace)
    fallback_data = {
        # Top tier teams
        "OKC": (118.5, 107.5, 11.0, 100.5),
        "CLE": (117.8, 108.2, 9.6, 98.2),
        "BOS": (120.2, 110.8, 9.4, 99.8),
        "HOU": (113.5, 106.2, 7.3, 98.5),
        "MEM": (115.8, 109.5, 6.3, 101.2),
        "NYK": (116.2, 110.5, 5.7, 97.8),
        "DEN": (116.8, 111.5, 5.3, 99.2),
        "LAL": (114.5, 109.8, 4.7, 100.8),
        "MIN": (112.8, 108.5, 4.3, 97.5),
        "GSW": (115.2, 111.2, 4.0, 101.5),
        
        # Middle tier teams
        "MIL": (114.8, 111.2, 3.6, 99.8),
        "DAL": (116.5, 113.2, 3.3, 98.5),
        "LAC": (113.2, 110.5, 2.7, 97.2),
        "DET": (112.5, 110.2, 2.3, 98.8),
        "MIA": (111.8, 110.0, 1.8, 97.5),
        "SAC": (114.2, 112.8, 1.4, 100.2),
        "IND": (116.8, 115.5, 1.3, 102.5),
        "PHX": (113.5, 112.5, 1.0, 98.2),
        "ATL": (115.0, 114.2, 0.8, 100.5),
        "ORL": (108.5, 108.0, 0.5, 96.8),
        
        # Lower tier teams
        "SAS": (111.2, 111.5, -0.3, 99.5),
        "CHI": (111.8, 112.5, -0.7, 98.2),
        "BKN": (110.5, 111.8, -1.3, 98.8),
        "POR": (109.2, 111.2, -2.0, 99.2),
        "TOR": (110.8, 113.2, -2.4, 98.5),
        "PHI": (109.5, 112.5, -3.0, 97.8),
        "NOP": (109.2, 113.5, -4.3, 99.8),
        "CHA": (107.5, 113.8, -6.3, 100.2),
        "UTA": (108.2, 115.5, -7.3, 99.5),
        "WAS": (106.5, 118.2, -11.7, 100.8),
    }
    
    ratings = {}
    for abbrev, (off, def_, net, pace) in fallback_data.items():
        ratings[abbrev] = TeamRating(
            team_abbrev=abbrev,
            off_rating=off,
            def_rating=def_,
            net_rating=net,
            pace=pace,
        )
    
    return ratings


def get_current_season() -> str:
    """
    Determine the current NBA season string based on today's date.
    
    The NBA season spans two calendar years (e.g., 2024-25 season runs from
    October 2024 to June 2025).
    
    Returns:
        Season string in format "YYYY-YY" (e.g., "2024-25").
    """
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
