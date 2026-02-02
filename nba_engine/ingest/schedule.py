"""
Schedule module for fetching today's NBA games and team statistics.

Uses nba_api to fetch:
- Today's game slate from live scoreboard
- Team ratings (offensive, defensive, net) from league stats
- Advanced team stats for the point system
- Schedule history for rest day calculations
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import time

import requests
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import leaguedashteamstats, teamgamelog
from nba_api.stats.static import teams as nba_teams


# Custom headers to avoid NBA API blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
}

# Team abbreviation to ID mapping
TEAM_IDS = {team['abbreviation']: team['id'] for team in nba_teams.get_teams()}


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


@dataclass
class TeamAdvancedStats:
    """Advanced team statistics for the point system."""
    team_abbrev: str
    # Basic ratings
    off_rating: float = 110.0
    def_rating: float = 110.0
    net_rating: float = 0.0
    pace: float = 100.0
    # Shooting
    efg_pct: float = 0.52
    fg3_pct: float = 0.36
    fg3a_rate: float = 0.40
    ft_rate: float = 0.25
    # Ball movement
    tov_pct: float = 14.0
    # Rebounding
    oreb_pct: float = 25.0
    dreb_pct: float = 75.0
    reb_pct: float = 50.0
    # Defense
    opp_fg3_pct: float = 0.36
    # Fouls
    pf_per_game: float = 20.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for point system."""
        return {
            'off_rating': self.off_rating,
            'def_rating': self.def_rating,
            'net_rating': self.net_rating,
            'pace': self.pace,
            'efg_pct': self.efg_pct,
            'fg3_pct': self.fg3_pct,
            'fg3a_rate': self.fg3a_rate,
            'ft_rate': self.ft_rate,
            'tov_pct': self.tov_pct,
            'oreb_pct': self.oreb_pct,
            'dreb_pct': self.dreb_pct,
            'reb_pct': self.reb_pct,
            'opp_fg3_pct': self.opp_fg3_pct,
            'pf_per_game': self.pf_per_game,
        }


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


def get_advanced_team_stats(
    season: str = "2024-25",
    max_retries: int = 2,
    timeout: int = 60,
) -> dict[str, dict]:
    """
    Fetch advanced team statistics for the point system.
    
    Returns a dict mapping team abbreviation to stats dict.
    """
    print("  Fetching advanced team stats...")
    
    for attempt in range(max_retries):
        try:
            # Get base stats
            base_stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star="Regular Season",
                per_mode_detailed="PerGame",
                timeout=timeout,
                headers=HEADERS,
            )
            base_df = base_stats.get_data_frames()[0]
            
            # Get per 100 possessions for ratings
            per100_stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star="Regular Season",
                per_mode_detailed="Per100Possessions",
                timeout=timeout,
                headers=HEADERS,
            )
            per100_df = per100_stats.get_data_frames()[0]
            
            team_stats = {}
            
            for _, row in base_df.iterrows():
                abbrev = row["TEAM_ABBREVIATION"]
                
                # Get per 100 row for this team
                per100_row = per100_df[per100_df["TEAM_ABBREVIATION"] == abbrev]
                if len(per100_row) > 0:
                    per100_row = per100_row.iloc[0]
                else:
                    per100_row = row
                
                # Calculate derived stats
                fga = float(row.get("FGA", 80) or 80)
                fg3a = float(row.get("FG3A", 35) or 35)
                fta = float(row.get("FTA", 20) or 20)
                
                fg3a_rate = fg3a / fga if fga > 0 else 0.40
                ft_rate = fta / fga if fga > 0 else 0.25
                
                # Estimate turnover percentage
                tov = float(row.get("TOV", 14) or 14)
                poss_est = fga + 0.44 * fta + tov
                tov_pct = (tov / poss_est * 100) if poss_est > 0 else 14.0
                
                # Rebounding
                oreb = float(row.get("OREB", 10) or 10)
                dreb = float(row.get("DREB", 35) or 35)
                total_reb = oreb + dreb
                
                stats = TeamAdvancedStats(
                    team_abbrev=abbrev,
                    off_rating=float(per100_row.get("OFF_RATING", 110) or 110),
                    def_rating=float(per100_row.get("DEF_RATING", 110) or 110),
                    net_rating=float(per100_row.get("NET_RATING", 0) or 0),
                    pace=float(per100_row.get("PACE", 100) or 100),
                    efg_pct=float(row.get("EFG_PCT", 0.52) or 0.52),
                    fg3_pct=float(row.get("FG3_PCT", 0.36) or 0.36),
                    fg3a_rate=fg3a_rate,
                    ft_rate=ft_rate,
                    tov_pct=tov_pct,
                    oreb_pct=oreb / total_reb * 100 if total_reb > 0 else 25.0,
                    dreb_pct=dreb / total_reb * 100 if total_reb > 0 else 75.0,
                    reb_pct=50.0,  # Need opponent rebounds to calculate properly
                    opp_fg3_pct=0.36,  # Would need opponent stats
                    pf_per_game=float(row.get("PF", 20) or 20),
                )
                
                team_stats[abbrev] = stats.to_dict()
            
            print(f"  Loaded advanced stats for {len(team_stats)} teams.")
            return team_stats
            
        except Exception as e:
            print(f"  Advanced stats attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    # Return fallback stats
    print("  Using fallback advanced stats...")
    return get_fallback_advanced_stats()


def get_team_rest_days(
    teams: list[str],
    season: str = "2024-25",
    timeout: int = 30,
) -> dict[str, int]:
    """
    Get days since last game for each team.
    
    Args:
        teams: List of team abbreviations.
        season: NBA season string.
        timeout: Request timeout in seconds.
    
    Returns:
        Dict mapping team abbreviation to days since last game.
    """
    rest_days = {team: 1 for team in teams}  # Default to 1 day rest
    today = datetime.now().date()
    
    for team in teams:
        try:
            team_id = TEAM_IDS.get(team)
            if not team_id:
                continue
            
            # Get recent games
            game_log = teamgamelog.TeamGameLog(
                team_id=team_id,
                season=season,
                timeout=timeout,
                headers=HEADERS,
            )
            
            df = game_log.get_data_frames()[0]
            
            if len(df) > 0:
                # Most recent game date
                last_game_str = df.iloc[0]["GAME_DATE"]
                # Parse date (format: "MMM DD, YYYY" or similar)
                try:
                    last_game = datetime.strptime(last_game_str, "%b %d, %Y").date()
                    days = (today - last_game).days
                    rest_days[team] = max(0, days)
                except:
                    pass
                    
        except Exception as e:
            # Silently use default
            pass
    
    return rest_days


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


def get_fallback_advanced_stats() -> dict[str, dict]:
    """
    Return fallback advanced stats when API fails.
    """
    # Use basic ratings and estimate other stats
    ratings = get_fallback_ratings()
    stats = {}
    
    for abbrev, rating in ratings.items():
        # Estimate other stats based on team strength
        strength = (rating.net_rating + 12) / 24  # Normalize to 0-1
        
        stats[abbrev] = {
            'off_rating': rating.off_rating,
            'def_rating': rating.def_rating,
            'net_rating': rating.net_rating,
            'pace': rating.pace,
            'efg_pct': 0.50 + strength * 0.06,  # 50-56%
            'fg3_pct': 0.34 + strength * 0.04,  # 34-38%
            'fg3a_rate': 0.38 + strength * 0.06,  # 38-44%
            'ft_rate': 0.22 + strength * 0.06,  # 22-28%
            'tov_pct': 15.0 - strength * 3.0,  # 12-15%
            'oreb_pct': 24.0 + strength * 4.0,  # 24-28%
            'dreb_pct': 74.0 + strength * 4.0,  # 74-78%
            'reb_pct': 49.0 + strength * 4.0,  # 49-53%
            'opp_fg3_pct': 0.38 - strength * 0.04,  # 34-38%
            'pf_per_game': 21.0 - strength * 3.0,  # 18-21
        }
    
    return stats


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
