"""
Tests for the SQLite storage module.
"""

import os
import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

# Import storage module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import (
    get_db_path,
    connect,
    init_db,
    upsert_game,
    insert_run,
    upsert_pick,
    get_ungraded_picks,
    get_games_for_date,
    compute_stats,
    update_game_score,
    grade_pick,
    generate_game_id,
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
        
        # Verify
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == "final"
        assert row['away_score'] == 105
        assert row['home_score'] == 112


class TestRunOperations:
    """Tests for run CRUD operations."""
    
    def test_insert_run_returns_id(self):
        """Inserting a run should return the run_id."""
        run_id = insert_run("2026-02-04")
        assert run_id is not None
        assert len(run_id) > 0
    
    def test_insert_run_creates_record(self):
        """Inserting a run should create a database record."""
        run_id = insert_run("2026-02-04", model_version="test")
        
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row['run_date'] == "2026-02-04"
        assert row['model_version'] == "test"


class TestPickOperations:
    """Tests for pick CRUD operations."""
    
    def test_upsert_pick_new(self):
        """Upserting a new pick should succeed."""
        # Create required run and game first
        run_id = insert_run("2026-02-04")
        game_id = f"test-pick-game-{datetime.now().timestamp()}"
        upsert_game(game_id, "2026-02-04", "BOS", "NYK")
        
        pick_id = f"test-pick-{datetime.now().timestamp()}"
        result = upsert_pick(
            pick_id=pick_id,
            run_id=run_id,
            game_id=game_id,
            matchup="BOS @ NYK",
            pick_team="NYK",
            pick_side="HOME",
            conf_pct=68.5,
            bucket="MEDIUM"
        )
        
        assert result == pick_id
    
    def test_grade_pick_updates_result(self):
        """Grading a pick should update its result."""
        # Create pick
        run_id = insert_run("2026-02-04")
        game_id = f"test-grade-game-{datetime.now().timestamp()}"
        upsert_game(game_id, "2026-02-04", "BOS", "NYK")
        
        pick_id = f"test-grade-pick-{datetime.now().timestamp()}"
        upsert_pick(
            pick_id=pick_id,
            run_id=run_id,
            game_id=game_id,
            matchup="BOS @ NYK",
            pick_team="NYK",
            pick_side="HOME",
            conf_pct=68.5,
            bucket="MEDIUM"
        )
        
        # Grade it
        grade_pick(pick_id, "W")
        
        # Verify
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM picks WHERE pick_id = ?", (pick_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row['result'] == "W"
        assert row['graded_at'] is not None


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
        
        # Check HIGH bucket fields
        assert hasattr(stats, 'high_total')
        assert hasattr(stats, 'high_wins')
        assert hasattr(stats, 'high_win_pct')
        
        # Check MEDIUM bucket fields
        assert hasattr(stats, 'med_total')
        assert hasattr(stats, 'med_wins')
        assert hasattr(stats, 'med_win_pct')
        
        # Check LOW bucket fields
        assert hasattr(stats, 'low_total')
        assert hasattr(stats, 'low_wins')
        assert hasattr(stats, 'low_win_pct')
    
    def test_compute_stats_counts_wins_correctly(self):
        """Stats should correctly count wins and losses."""
        # Create some test picks with known results
        run_id = insert_run("2026-01-15")
        
        # Create HIGH win
        game_id_1 = f"stats-test-1-{datetime.now().timestamp()}"
        upsert_game(game_id_1, "2026-01-15", "BOS", "NYK")
        pick_id_1 = f"stats-pick-1-{datetime.now().timestamp()}"
        upsert_pick(pick_id_1, run_id, game_id_1, "BOS @ NYK", "NYK", "HOME", 75.0, "HIGH")
        grade_pick(pick_id_1, "W")
        
        # Create HIGH loss
        game_id_2 = f"stats-test-2-{datetime.now().timestamp()}"
        upsert_game(game_id_2, "2026-01-15", "LAL", "GSW")
        pick_id_2 = f"stats-pick-2-{datetime.now().timestamp()}"
        upsert_pick(pick_id_2, run_id, game_id_2, "LAL @ GSW", "GSW", "HOME", 73.0, "HIGH")
        grade_pick(pick_id_2, "L")
        
        stats = compute_stats()
        
        # Should have at least our test wins/losses
        assert stats.wins >= 1
        assert stats.losses >= 1
        assert stats.high_wins >= 1
        assert stats.high_losses >= 1


class TestUngraded:
    """Tests for fetching ungraded picks."""
    
    def test_get_ungraded_picks_returns_list(self):
        """get_ungraded_picks() should return a list."""
        ungraded = get_ungraded_picks()
        assert isinstance(ungraded, list)
    
    def test_get_ungraded_picks_filter_by_date(self):
        """Should be able to filter ungraded picks by date."""
        # Create an ungraded pick for a specific date
        run_id = insert_run("2026-01-20")
        game_id = f"ungraded-test-{datetime.now().timestamp()}"
        upsert_game(game_id, "2026-01-20", "MIA", "CHI")
        pick_id = f"ungraded-pick-{datetime.now().timestamp()}"
        upsert_pick(pick_id, run_id, game_id, "MIA @ CHI", "CHI", "HOME", 62.0, "MEDIUM")
        
        # Should find it when querying that date
        ungraded = get_ungraded_picks("2026-01-20")
        
        # At least our test pick should be there
        pick_ids = [p['pick_id'] for p in ungraded]
        assert pick_id in pick_ids
