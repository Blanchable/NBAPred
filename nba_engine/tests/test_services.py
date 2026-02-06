"""
Tests for the score fetching and grading services.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import services
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.scores import (
    GameScoreUpdate,
    NBALiveScoreProvider,
    fetch_scores_for_date,
    get_today_date_et,
)
from services.grading import (
    update_games_from_scores,
    grade_picks_for_date,
)


class TestGameScoreUpdate:
    """Tests for GameScoreUpdate dataclass."""
    
    def test_is_final_true(self):
        """is_final should return True for final games."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="final",
            away_score=105,
            home_score=112
        )
        assert update.is_final is True
    
    def test_is_final_false_for_scheduled(self):
        """is_final should return False for scheduled games."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="scheduled"
        )
        assert update.is_final is False
    
    def test_is_in_progress(self):
        """is_in_progress should return True for live games."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="in_progress",
            away_score=52,
            home_score=48
        )
        assert update.is_in_progress is True
    
    def test_get_winner_side_home_wins(self):
        """get_winner_side should return HOME when home team wins."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="final",
            away_score=105,
            home_score=112
        )
        assert update.get_winner_side() == "HOME"
    
    def test_get_winner_side_away_wins(self):
        """get_winner_side should return AWAY when away team wins."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="final",
            away_score=115,
            home_score=108
        )
        assert update.get_winner_side() == "AWAY"
    
    def test_get_winner_side_none_if_not_final(self):
        """get_winner_side should return None if game not final."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="in_progress",
            away_score=52,
            home_score=48
        )
        assert update.get_winner_side() is None
    
    def test_get_winner_side_none_if_no_scores(self):
        """get_winner_side should return None if scores missing."""
        update = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="final",
            away_score=None,
            home_score=None
        )
        assert update.get_winner_side() is None


class TestNBALiveScoreProvider:
    """Tests for NBA Live Score Provider."""
    
    def test_provider_initializes(self):
        """Provider should initialize without errors."""
        provider = NBALiveScoreProvider()
        assert provider.timeout == 15
    
    def test_provider_custom_timeout(self):
        """Provider should accept custom timeout."""
        provider = NBALiveScoreProvider(timeout=30)
        assert provider.timeout == 30
    
    @patch('services.scores.requests.get')
    def test_get_games_handles_error(self, mock_get):
        """Provider should handle request errors gracefully."""
        import requests
        mock_get.side_effect = requests.RequestException("Network error")
        
        provider = NBALiveScoreProvider()
        games = provider.get_games_for_date("2026-02-04")
        
        assert games == []
    
    @patch('services.scores.requests.get')
    def test_get_games_parses_response(self, mock_get):
        """Provider should parse API response correctly."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "scoreboard": {
                "gameDate": "2026-02-04",
                "games": [
                    {
                        "gameId": "0022500712",
                        "gameStatus": 3,  # Final
                        "awayTeam": {
                            "teamTricode": "BOS",
                            "score": "105"
                        },
                        "homeTeam": {
                            "teamTricode": "NYK",
                            "score": "112"
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        provider = NBALiveScoreProvider()
        games = provider.get_games_for_date("2026-02-04")
        
        assert len(games) == 1
        assert games[0].game_id == "0022500712"
        assert games[0].away_team == "BOS"
        assert games[0].home_team == "NYK"
        assert games[0].status == "final"
        assert games[0].away_score == 105
        assert games[0].home_score == 112


class TestFetchScores:
    """Tests for fetch_scores_for_date convenience function."""
    
    @patch('services.scores.NBALiveScoreProvider.get_games_for_date')
    def test_fetch_uses_default_provider(self, mock_get):
        """fetch_scores_for_date should use default provider."""
        mock_get.return_value = []
        
        fetch_scores_for_date("2026-02-04")
        
        mock_get.assert_called_once_with("2026-02-04")
    
    @patch('services.scores.NBALiveScoreProvider.get_games_for_date')
    def test_fetch_returns_games(self, mock_get):
        """fetch_scores_for_date should return games from provider."""
        test_game = GameScoreUpdate(
            game_id="123",
            away_team="BOS",
            home_team="NYK",
            game_date="2026-02-04",
            status="final"
        )
        mock_get.return_value = [test_game]
        
        games = fetch_scores_for_date("2026-02-04")
        
        assert len(games) == 1
        assert games[0] == test_game


class TestGetTodayDateET:
    """Tests for get_today_date_et function."""
    
    def test_returns_string(self):
        """Should return a date string."""
        date = get_today_date_et()
        assert isinstance(date, str)
    
    def test_returns_valid_date_format(self):
        """Should return date in YYYY-MM-DD format."""
        date = get_today_date_et()
        
        # Should be parseable
        parsed = datetime.strptime(date, "%Y-%m-%d")
        assert parsed is not None


class TestGrading:
    """Tests for grading service."""
    
    def test_update_games_from_scores_empty(self):
        """Should handle empty score list."""
        updated = update_games_from_scores([])
        assert updated == 0
    
    def test_update_games_from_scores(self):
        """Should update games from score list."""
        from storage.db import upsert_game, get_games_for_date
        
        # Create a game first
        game_id = f"grading-test-{datetime.now().timestamp()}"
        upsert_game(game_id, "2026-01-25", "MIA", "ATL", status="scheduled")
        
        # Create score update
        score = GameScoreUpdate(
            game_id=game_id,
            away_team="MIA",
            home_team="ATL",
            game_date="2026-01-25",
            status="final",
            away_score=118,
            home_score=105
        )
        
        updated = update_games_from_scores([score])
        
        assert updated == 1
