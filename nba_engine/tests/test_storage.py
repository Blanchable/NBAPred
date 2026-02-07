"""
Tests for the SQLite storage module with daily slate and per-game locking.
"""

import os
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

# Import storage module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import (
    get_db_path,
    connect,
    init_db,
    upsert_game,
    get_game,
    upsert_daily_slate,
    get_daily_slate,
    upsert_daily_pick_if_unlocked,
    get_daily_picks,
    get_daily_pick,
    grade_daily_pick,
    is_game_locked,
    lock_game_if_started,
    lock_all_started_games,
    compute_stats,
    generate_game_id,
    get_now_local,
    get_today_date_local,
    WinrateStats,
)


class TestDatabasePath:
    """Tests for database path handling."""
    
    def test_get_db_path_returns_path(self):
        """Database path should be a Path object."""
        db_path = get_db_path()
        assert isinstance(db_path, Path)
    
    def test_get_db_path_has_db_extension(self):
        """Database path should have .db extension."""
        db_path = get_db_path()
        assert db_path.suffix == '.db'
    
    def test_get_db_path_is_absolute(self):
        """Database path should be absolute."""
        db_path = get_db_path()
        assert db_path.is_absolute()


class TestConnection:
    """Tests for database connection."""
    
    def test_connect_returns_connection(self):
        """connect() should return a connection object."""
        conn = connect()
        assert conn is not None
        conn.close()
    
    def test_connection_has_row_factory(self):
        """Connection should have row_factory set for dict access."""
        conn = connect()
        assert conn.row_factory is not None
        conn.close()


class TestGameIdGeneration:
    """Tests for game ID generation."""
    
    def test_generate_game_id_format(self):
        """Generated ID should follow expected format."""
        game_id = generate_game_id("2026-02-04", "BOS", "NYK")
        assert game_id == "2026-02-04:BOS@NYK"
    
    def test_generate_game_id_unique(self):
        """Different games should have different IDs."""
        id1 = generate_game_id("2026-02-04", "BOS", "NYK")
        id2 = generate_game_id("2026-02-04", "LAL", "GSW")
        id3 = generate_game_id("2026-02-05", "BOS", "NYK")
        
        assert id1 != id2
        assert id1 != id3
        assert id2 != id3


class TestDailySlate:
    """Tests for daily slate operations."""
    
    def test_upsert_daily_slate_creates(self):
        """Creating a new daily slate should work."""
        slate_date = "2026-01-01"
        last_run_at = "2026-01-01T15:00:00"
        
        upsert_daily_slate(slate_date, last_run_at, model_version="test")
        
        slate = get_daily_slate(slate_date)
        assert slate is not None
        assert slate['slate_date'] == slate_date
        assert slate['last_run_at'] == last_run_at
        assert slate['model_version'] == "test"
    
    def test_upsert_daily_slate_updates(self):
        """Updating a daily slate should update last_run_at."""
        slate_date = "2026-01-02"
        
        upsert_daily_slate(slate_date, "2026-01-02T14:00:00", model_version="v1")
        upsert_daily_slate(slate_date, "2026-01-02T16:00:00", model_version="v2")
        
        slate = get_daily_slate(slate_date)
        assert slate['last_run_at'] == "2026-01-02T16:00:00"
        assert slate['model_version'] == "v2"


class TestGameOperations:
    """Tests for game CRUD operations."""
    
    def test_upsert_game_new(self):
        """Upserting a new game should succeed."""
        game_id = f"test-game-{datetime.now().timestamp()}"
        
        result = upsert_game(
            game_id=game_id,
            game_date="2026-02-04",
            away_team="BOS",
            home_team="NYK",
            status="scheduled"
        )
        
        assert result == game_id
    
    def test_upsert_game_with_start_time(self):
        """Game should store start time in local format."""
        game_id = f"test-start-time-{datetime.now().timestamp()}"
        
        upsert_game(
            game_id=game_id,
            game_date="2026-02-04",
            away_team="BOS",
            home_team="NYK",
            start_time_local="2026-02-04T19:00:00",
            status="scheduled"
        )
        
        game = get_game(game_id)
        assert game is not None
        assert game['start_time_local'] == "2026-02-04T19:00:00"
    
    def test_upsert_game_updates_existing(self):
        """Upserting an existing game should update it."""
        game_id = f"test-game-update-{datetime.now().timestamp()}"
        
        # Insert
        upsert_game(
            game_id=game_id,
            game_date="2026-02-04",
            away_team="BOS",
            home_team="NYK",
            status="scheduled"
        )
        
        # Update
        upsert_game(
            game_id=game_id,
            game_date="2026-02-04",
            away_team="BOS",
            home_team="NYK",
            status="final",
            away_score=105,
            home_score=112
        )
        
        game = get_game(game_id)
        assert game['status'] == "final"
        assert game['away_score'] == 105
        assert game['home_score'] == 112


class TestLocking:
    """Tests for game locking functionality."""
    
    def test_game_not_locked_before_start(self):
        """Game should not be locked before start time."""
        game_id = f"lock-test-1-{datetime.now().timestamp()}"
        slate_date = "2026-03-01"
        
        # Set game start time in the future
        future_time = "2026-03-01T23:00:00"
        now_time = "2026-03-01T18:00:00"
        
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="BOS",
            home_team="NYK",
            start_time_local=future_time,
            status="scheduled"
        )
        
        assert is_game_locked(slate_date, game_id, now_time) is False
    
    def test_game_locked_after_start(self):
        """Game should be locked after start time passes."""
        game_id = f"lock-test-2-{datetime.now().timestamp()}"
        slate_date = "2026-03-02"
        
        # Set game start time in the past
        start_time = "2026-03-02T18:00:00"
        now_time = "2026-03-02T18:30:00"
        
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="LAL",
            home_team="GSW",
            start_time_local=start_time,
            status="scheduled"
        )
        
        # Create a pick first
        pick_data = {
            'matchup': 'LAL @ GSW',
            'pick_team': 'GSW',
            'pick_side': 'HOME',
            'conf_pct': 65.0,
            'bucket': 'MEDIUM',
        }
        
        # Save at 17:59 (before start)
        upsert_daily_pick_if_unlocked(slate_date, game_id, pick_data, "2026-03-02T17:59:00")
        
        # Check locked status after start
        assert is_game_locked(slate_date, game_id, now_time) is True
    
    def test_game_locked_when_in_progress(self):
        """Game should be locked when status is in_progress."""
        game_id = f"lock-test-3-{datetime.now().timestamp()}"
        slate_date = "2026-03-03"
        
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="MIA",
            home_team="CHI",
            status="in_progress"
        )
        
        assert is_game_locked(slate_date, game_id) is True
    
    def test_lock_game_if_started(self):
        """lock_game_if_started should set locked=1."""
        game_id = f"lock-test-4-{datetime.now().timestamp()}"
        slate_date = "2026-03-04"
        start_time = "2026-03-04T19:00:00"
        
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="PHX",
            home_team="DEN",
            start_time_local=start_time,
            status="scheduled"
        )
        
        # Create pick before start
        pick_data = {
            'matchup': 'PHX @ DEN',
            'pick_team': 'DEN',
            'pick_side': 'HOME',
            'conf_pct': 70.0,
            'bucket': 'MEDIUM',
        }
        upsert_daily_pick_if_unlocked(slate_date, game_id, pick_data, "2026-03-04T18:55:00")
        
        # Lock game after start
        locked = lock_game_if_started(slate_date, game_id, "2026-03-04T19:05:00")
        assert locked is True
        
        # Verify pick is now locked
        pick = get_daily_pick(slate_date, game_id)
        assert pick is not None
        assert pick['locked'] == 1


class TestDailyPickOperations:
    """Tests for daily pick operations with locking."""
    
    def test_upsert_pick_saves_when_unlocked(self):
        """Pick should be saved when game hasn't started."""
        game_id = f"pick-test-1-{datetime.now().timestamp()}"
        slate_date = "2026-03-10"
        
        # Game starts in future
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="BOS",
            home_team="NYK",
            start_time_local="2026-03-10T20:00:00",
            status="scheduled"
        )
        
        pick_data = {
            'matchup': 'BOS @ NYK',
            'pick_team': 'NYK',
            'pick_side': 'HOME',
            'conf_pct': 68.5,
            'bucket': 'MEDIUM',
        }
        
        was_saved, is_locked = upsert_daily_pick_if_unlocked(
            slate_date, game_id, pick_data, "2026-03-10T17:00:00"
        )
        
        assert was_saved is True
        assert is_locked is False
        
        pick = get_daily_pick(slate_date, game_id)
        assert pick is not None
        assert pick['pick_team'] == 'NYK'
    
    def test_upsert_pick_blocked_when_locked(self):
        """Pick should not be saved when game has started."""
        game_id = f"pick-test-2-{datetime.now().timestamp()}"
        slate_date = "2026-03-11"
        
        # Game starts at 19:00, status is scheduled initially
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="LAL",
            home_team="GSW",
            start_time_local="2026-03-11T19:00:00",
            status="scheduled"
        )
        
        # First pick at 18:55 (before start)
        pick_data_1 = {
            'matchup': 'LAL @ GSW',
            'pick_team': 'GSW',
            'pick_side': 'HOME',
            'conf_pct': 72.0,
            'bucket': 'HIGH',
        }
        was_saved, _ = upsert_daily_pick_if_unlocked(
            slate_date, game_id, pick_data_1, "2026-03-11T18:55:00"
        )
        assert was_saved is True
        
        # Second pick at 19:05 (after start time passed) - should be blocked
        pick_data_2 = {
            'matchup': 'LAL @ GSW',
            'pick_team': 'LAL',  # Different pick
            'pick_side': 'AWAY',
            'conf_pct': 55.0,
            'bucket': 'LOW',
        }
        was_saved, is_locked = upsert_daily_pick_if_unlocked(
            slate_date, game_id, pick_data_2, "2026-03-11T19:05:00"
        )
        
        assert was_saved is False
        assert is_locked is True
        
        # Verify original pick is still there
        pick = get_daily_pick(slate_date, game_id)
        assert pick['pick_team'] == 'GSW'
        assert pick['conf_pct'] == 72.0
    
    def test_pick_overwritten_before_start(self):
        """Pick should be overwritten if game hasn't started."""
        game_id = f"pick-test-3-{datetime.now().timestamp()}"
        slate_date = "2026-03-12"
        
        # Game starts at 20:00
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="MIA",
            home_team="ATL",
            start_time_local="2026-03-12T20:00:00",
            status="scheduled"
        )
        
        # First pick at 16:00
        pick_data_1 = {
            'matchup': 'MIA @ ATL',
            'pick_team': 'MIA',
            'pick_side': 'AWAY',
            'conf_pct': 60.0,
            'bucket': 'MEDIUM',
        }
        upsert_daily_pick_if_unlocked(slate_date, game_id, pick_data_1, "2026-03-12T16:00:00")
        
        # Second pick at 17:00 - should overwrite
        pick_data_2 = {
            'matchup': 'MIA @ ATL',
            'pick_team': 'ATL',
            'pick_side': 'HOME',
            'conf_pct': 65.0,
            'bucket': 'MEDIUM',
        }
        was_saved, _ = upsert_daily_pick_if_unlocked(
            slate_date, game_id, pick_data_2, "2026-03-12T17:00:00"
        )
        
        assert was_saved is True
        
        # Verify pick was updated
        pick = get_daily_pick(slate_date, game_id)
        assert pick['pick_team'] == 'ATL'
        assert pick['conf_pct'] == 65.0


class TestPartialSlateUpdate:
    """Test partial slate updates where some games are locked."""
    
    def test_partial_slate_lock(self):
        """Only started games should be locked."""
        slate_date = "2026-03-15"
        
        # Game 1: started at 18:00
        game_id_1 = f"partial-1-{datetime.now().timestamp()}"
        upsert_game(
            game_id=game_id_1,
            game_date=slate_date,
            away_team="BOS",
            home_team="NYK",
            start_time_local="2026-03-15T18:00:00",
            status="scheduled"
        )
        
        # Game 2: starts at 20:00
        game_id_2 = f"partial-2-{datetime.now().timestamp()}"
        upsert_game(
            game_id=game_id_2,
            game_date=slate_date,
            away_team="LAL",
            home_team="GSW",
            start_time_local="2026-03-15T20:00:00",
            status="scheduled"
        )
        
        # Save picks for both games at 17:30 (before both start)
        pick_1 = {
            'matchup': 'BOS @ NYK',
            'pick_team': 'NYK',
            'pick_side': 'HOME',
            'conf_pct': 68.0,
            'bucket': 'MEDIUM',
        }
        pick_2 = {
            'matchup': 'LAL @ GSW',
            'pick_team': 'GSW',
            'pick_side': 'HOME',
            'conf_pct': 70.0,
            'bucket': 'MEDIUM',
        }
        
        upsert_daily_pick_if_unlocked(slate_date, game_id_1, pick_1, "2026-03-15T17:30:00")
        upsert_daily_pick_if_unlocked(slate_date, game_id_2, pick_2, "2026-03-15T17:30:00")
        
        # Now at 18:30 - game 1 started, game 2 not started
        now_time = "2026-03-15T18:30:00"
        
        # Try to update both games
        pick_1_new = {
            'matchup': 'BOS @ NYK',
            'pick_team': 'BOS',  # Changed
            'pick_side': 'AWAY',
            'conf_pct': 55.0,
            'bucket': 'LOW',
        }
        pick_2_new = {
            'matchup': 'LAL @ GSW',
            'pick_team': 'LAL',  # Changed
            'pick_side': 'AWAY',
            'conf_pct': 62.0,
            'bucket': 'MEDIUM',
        }
        
        saved_1, locked_1 = upsert_daily_pick_if_unlocked(slate_date, game_id_1, pick_1_new, now_time)
        saved_2, locked_2 = upsert_daily_pick_if_unlocked(slate_date, game_id_2, pick_2_new, now_time)
        
        # Game 1 should be locked (started)
        assert saved_1 is False
        assert locked_1 is True
        
        # Game 2 should be updated (not started)
        assert saved_2 is True
        assert locked_2 is False
        
        # Verify game 1 pick unchanged
        p1 = get_daily_pick(slate_date, game_id_1)
        assert p1['pick_team'] == 'NYK'
        
        # Verify game 2 pick changed
        p2 = get_daily_pick(slate_date, game_id_2)
        assert p2['pick_team'] == 'LAL'


class TestGrading:
    """Tests for grading picks."""
    
    def test_grade_daily_pick(self):
        """Grading a pick should update result and lock it."""
        game_id = f"grade-test-{datetime.now().timestamp()}"
        slate_date = "2026-03-20"
        
        upsert_game(
            game_id=game_id,
            game_date=slate_date,
            away_team="PHX",
            home_team="DEN",
            status="scheduled"
        )
        
        pick_data = {
            'matchup': 'PHX @ DEN',
            'pick_team': 'DEN',
            'pick_side': 'HOME',
            'conf_pct': 65.0,
            'bucket': 'MEDIUM',
        }
        upsert_daily_pick_if_unlocked(slate_date, game_id, pick_data, "2026-03-20T17:00:00")
        
        # Grade as win
        grade_daily_pick(slate_date, game_id, "W")
        
        pick = get_daily_pick(slate_date, game_id)
        assert pick['result'] == "W"
        assert pick['graded_at'] is not None
        assert pick['locked'] == 1


class TestStatsComputation:
    """Tests for statistics computation."""
    
    def test_compute_stats_returns_winrate_stats(self):
        """compute_stats() should return a WinrateStats object."""
        stats = compute_stats()
        assert isinstance(stats, WinrateStats)
    
    def test_compute_stats_has_all_fields(self):
        """WinrateStats should have all required fields."""
        stats = compute_stats()
        
        # Check overall fields
        assert hasattr(stats, 'total_picks')
        assert hasattr(stats, 'total_graded')
        assert hasattr(stats, 'wins')
        assert hasattr(stats, 'losses')
        assert hasattr(stats, 'win_pct')
        assert hasattr(stats, 'pending')
        
        # Check bucket fields
        assert hasattr(stats, 'high_total')
        assert hasattr(stats, 'med_total')
        assert hasattr(stats, 'low_total')


class TestTimeHelpers:
    """Tests for time helper functions."""
    
    def test_get_now_local_format(self):
        """get_now_local should return ISO formatted string."""
        now = get_now_local()
        assert isinstance(now, str)
        assert 'T' in now
    
    def test_get_today_date_local_format(self):
        """get_today_date_local should return YYYY-MM-DD format."""
        today = get_today_date_local()
        assert isinstance(today, str)
        assert len(today) == 10
        assert today.count('-') == 2
