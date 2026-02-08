"""
Score fetching service for NBA Prediction Engine.

Provides adapters to fetch game scores from various APIs.
Uses NBA's live scoreboard API (same as schedule.py) as the primary source.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import time

import requests


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class GameScoreUpdate:
    """Represents a game score update from the API."""
    game_id: str
    away_team: str
    home_team: str
    game_date: str
    status: str  # scheduled, in_progress, final
    away_score: Optional[int] = None
    home_score: Optional[int] = None
    start_time_utc: Optional[str] = None
    
    @property
    def is_final(self) -> bool:
        return self.status.lower() == "final"
    
    @property
    def is_in_progress(self) -> bool:
        return self.status.lower() in ("in_progress", "live", "halftime")
    
    def get_winner_side(self) -> Optional[str]:
        """
        Determine which side won.
        
        Returns:
            "HOME" if home won, "AWAY" if away won, None if tie or not final
        """
        if not self.is_final or self.away_score is None or self.home_score is None:
            return None
        
        if self.home_score > self.away_score:
            return "HOME"
        elif self.away_score > self.home_score:
            return "AWAY"
        else:
            return None  # Tie (shouldn't happen in NBA)


# ============================================================================
# SCORE PROVIDER INTERFACE
# ============================================================================

class ScoreProvider(ABC):
    """Abstract base class for score providers."""
    
    @abstractmethod
    def get_games_for_date(self, date_str: str) -> List[GameScoreUpdate]:
        """
        Fetch all games for a specific date.
        
        Args:
            date_str: Date in YYYY-MM-DD format
        
        Returns:
            List of GameScoreUpdate objects
        """
        pass


# ============================================================================
# NBA LIVE API PROVIDER
# ============================================================================

class NBALiveScoreProvider(ScoreProvider):
    """
    Score provider using NBA's live scoreboard API.
    
    This is the same API used in ingest/schedule.py for fetching today's games.
    """
    
    SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
    
    def _parse_status(self, game_data: dict) -> str:
        """Parse game status from API response."""
        status_code = game_data.get("gameStatus", 1)
        status_text = game_data.get("gameStatusText", "")
        
        # Status codes: 1=scheduled, 2=in_progress, 3=final
        if status_code == 3 or "final" in status_text.lower():
            return "final"
        elif status_code == 2 or any(x in status_text.lower() for x in ["qtr", "ot", "half"]):
            return "in_progress"
        else:
            return "scheduled"
    
    def get_games_for_date(self, date_str: str) -> List[GameScoreUpdate]:
        """
        Fetch games from NBA live scoreboard.
        
        Note: The live scoreboard only shows today's games. For historical
        dates, this will return an empty list.
        
        Args:
            date_str: Date in YYYY-MM-DD format
        
        Returns:
            List of GameScoreUpdate objects
        """
        games = []
        
        try:
            response = requests.get(self.SCOREBOARD_URL, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            scoreboard_data = data.get("scoreboard", {})
            api_date = scoreboard_data.get("gameDate", "")
            game_list = scoreboard_data.get("games", [])
            
            # Only process if date matches
            if api_date != date_str:
                print(f"  Scoreboard date {api_date} doesn't match requested {date_str}")
                return games
            
            for game_data in game_list:
                away_team = game_data.get("awayTeam", {})
                home_team = game_data.get("homeTeam", {})
                
                status = self._parse_status(game_data)
                
                game = GameScoreUpdate(
                    game_id=game_data.get("gameId", ""),
                    away_team=away_team.get("teamTricode", ""),
                    home_team=home_team.get("teamTricode", ""),
                    game_date=api_date,
                    status=status,
                    away_score=away_team.get("score"),
                    home_score=home_team.get("score"),
                    start_time_utc=game_data.get("gameTimeUTC"),
                )
                
                # Convert score strings to ints if needed
                if isinstance(game.away_score, str) and game.away_score.isdigit():
                    game.away_score = int(game.away_score)
                if isinstance(game.home_score, str) and game.home_score.isdigit():
                    game.home_score = int(game.home_score)
                
                games.append(game)
                
        except requests.RequestException as e:
            print(f"  Error fetching scores: {e}")
        except (KeyError, ValueError) as e:
            print(f"  Error parsing score data: {e}")
        
        return games


# ============================================================================
# NBA API PROVIDER (using nba_api library)
# ============================================================================

class NBAApiScoreProvider(ScoreProvider):
    """
    Score provider using the nba_api library.
    
    Uses the same library as the rest of the codebase.
    """
    
    def get_games_for_date(self, date_str: str) -> List[GameScoreUpdate]:
        """
        Fetch games using nba_api scoreboard.
        
        Args:
            date_str: Date in YYYY-MM-DD format
        
        Returns:
            List of GameScoreUpdate objects
        """
        games = []
        
        try:
            from nba_api.live.nba.endpoints import scoreboard
            
            sb = scoreboard.ScoreBoard()
            data = sb.get_dict()
            
            scoreboard_data = data.get("scoreboard", {})
            api_date = scoreboard_data.get("gameDate", "")
            game_list = scoreboard_data.get("games", [])
            
            # Only process if date matches
            if api_date != date_str:
                print(f"  nba_api date {api_date} doesn't match requested {date_str}")
                return games
            
            for game_data in game_list:
                away_team = game_data.get("awayTeam", {})
                home_team = game_data.get("homeTeam", {})
                
                # Determine status
                status_code = game_data.get("gameStatus", 1)
                if status_code == 3:
                    status = "final"
                elif status_code == 2:
                    status = "in_progress"
                else:
                    status = "scheduled"
                
                away_score = away_team.get("score")
                home_score = home_team.get("score")
                
                # Convert to int if string
                if isinstance(away_score, str) and away_score.isdigit():
                    away_score = int(away_score)
                if isinstance(home_score, str) and home_score.isdigit():
                    home_score = int(home_score)
                
                game = GameScoreUpdate(
                    game_id=game_data.get("gameId", ""),
                    away_team=away_team.get("teamTricode", ""),
                    home_team=home_team.get("teamTricode", ""),
                    game_date=api_date,
                    status=status,
                    away_score=away_score,
                    home_score=home_score,
                    start_time_utc=game_data.get("gameTimeUTC"),
                )
                games.append(game)
                
        except ImportError:
            print("  nba_api not available, using fallback")
        except Exception as e:
            print(f"  Error with nba_api: {e}")
        
        return games


# ============================================================================
# HISTORICAL SCORE PROVIDER (for backfill grading)
# ============================================================================

class NBAStatsScoreProvider(ScoreProvider):
    """
    Score provider using nba_api.stats ScoreboardV2 endpoint.

    Unlike the live scoreboard (today only), this supports **any date**
    and is used to backfill scores for games from previous days.
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.nba.com',
        'Referer': 'https://www.nba.com/',
    }

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def get_games_for_date(self, date_str: str) -> List[GameScoreUpdate]:
        """
        Fetch games from ScoreboardV2 for an arbitrary date.

        Args:
            date_str: Date in YYYY-MM-DD format (e.g. "2026-02-05")

        Returns:
            List of GameScoreUpdate objects
        """
        games: List[GameScoreUpdate] = []
        try:
            from nba_api.stats.endpoints import scoreboardv2

            # ScoreboardV2 wants MM/DD/YYYY
            parts = date_str.split("-")
            api_date = f"{parts[1]}/{parts[2]}/{parts[0]}"

            sb = scoreboardv2.ScoreboardV2(
                game_date=api_date,
                timeout=self.timeout,
                headers=self.HEADERS,
            )
            dfs = sb.get_data_frames()
            if not dfs:
                return games

            # First DataFrame is GameHeader
            header_df = dfs[0]
            # Fifth DataFrame is LineScore (team-level scores)
            line_df = dfs[1] if len(dfs) > 1 else None

            # Build team-score lookup from LineScore
            team_scores: dict = {}  # game_id -> {team_id: score}
            if line_df is not None and len(line_df) > 0:
                for _, row in line_df.iterrows():
                    gid = str(row.get("GAME_ID", ""))
                    tid = row.get("TEAM_ID")
                    pts = row.get("PTS")
                    if gid and tid is not None:
                        team_scores.setdefault(gid, {})[tid] = int(pts) if pts is not None else None

            for _, row in header_df.iterrows():
                game_id = str(row.get("GAME_ID", ""))
                game_status = int(row.get("GAME_STATUS_ID", 1))
                home_tid = row.get("HOME_TEAM_ID")
                away_tid = row.get("VISITOR_TEAM_ID")

                if game_status == 3:
                    status = "final"
                elif game_status == 2:
                    status = "in_progress"
                else:
                    status = "scheduled"

                scores_for_game = team_scores.get(game_id, {})
                home_score = scores_for_game.get(home_tid)
                away_score = scores_for_game.get(away_tid)

                # Team abbreviations from the header columns
                home_abbrev = str(row.get("HOME_TEAM_ABBREVIATION", "") or "")
                away_abbrev = str(row.get("VISITOR_TEAM_ABBREVIATION", "") or "")

                # Fallback: try GAMECODE which is "YYYYMMDD/AWYHOM"
                if (not home_abbrev or not away_abbrev) and row.get("GAMECODE"):
                    gc = str(row["GAMECODE"])
                    if "/" in gc:
                        teams_part = gc.split("/")[1]
                        if len(teams_part) == 6:
                            away_abbrev = away_abbrev or teams_part[:3]
                            home_abbrev = home_abbrev or teams_part[3:]

                games.append(GameScoreUpdate(
                    game_id=game_id,
                    away_team=away_abbrev,
                    home_team=home_abbrev,
                    game_date=date_str,
                    status=status,
                    away_score=away_score,
                    home_score=home_score,
                ))

        except ImportError:
            print(f"  ScoreboardV2 not available for {date_str}")
        except Exception as e:
            print(f"  ScoreboardV2 fetch failed for {date_str}: {e}")

        return games


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# Backfill window (days) for grading past games
SCORE_BACKFILL_DAYS = 7


def fetch_scores_for_date(
    date_str: Optional[str] = None,
    provider: Optional[ScoreProvider] = None,
) -> List[GameScoreUpdate]:
    """
    Fetch game scores for a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
        provider: Score provider to use (defaults to NBALiveScoreProvider)
    
    Returns:
        List of GameScoreUpdate objects
    """
    if date_str is None:
        # Get today's date in Eastern Time (NBA uses ET)
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        et_offset = timedelta(hours=-5)  # EST (simplification)
        now_et = now_utc + et_offset
        date_str = now_et.strftime("%Y-%m-%d")
    
    if provider is None:
        provider = NBALiveScoreProvider()
    
    return provider.get_games_for_date(date_str)


def fetch_scores_for_past_date(date_str: str) -> List[GameScoreUpdate]:
    """
    Fetch scores for a *past* date using the ScoreboardV2 stats endpoint.

    Falls back to NBALiveScoreProvider if the date happens to be today.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        List of GameScoreUpdate objects
    """
    today = get_today_date_et()
    if date_str == today:
        return fetch_scores_for_date(date_str)
    return NBAStatsScoreProvider().get_games_for_date(date_str)


def get_today_date_et() -> str:
    """Get today's date in Eastern Time as YYYY-MM-DD."""
    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-5)  # EST (simplification)
    now_et = now_utc + et_offset
    return now_et.strftime("%Y-%m-%d")
