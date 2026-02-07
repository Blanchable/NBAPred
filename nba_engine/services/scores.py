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
# CONVENIENCE FUNCTION
# ============================================================================

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


def get_today_date_et() -> str:
    """Get today's date in Eastern Time as YYYY-MM-DD."""
    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-5)  # EST (simplification)
    now_et = now_utc + et_offset
    return now_et.strftime("%Y-%m-%d")
