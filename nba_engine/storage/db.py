"""
SQLite storage layer for NBA Prediction Engine.

Provides persistent tracking of predictions and results without
requiring Excel or external spreadsheet dependencies.

Tables:
- runs: Prediction run metadata (each run is a snapshot)
- games: NBA game data including scores and status
- picks: Individual pick records tied to runs and games
"""

import sqlite3
import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import uuid4

# Import paths module for persistent storage location
import sys
import os

# Add parent to path if needed
if __name__ != "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from paths import DATA_ROOT
except ImportError:
    # Fallback if paths module not available
    DATA_ROOT = Path.home() / ".nba_engine"


# ============================================================================
# DATABASE PATH
# ============================================================================

DB_FILENAME = "nba_predictions.db"


def get_db_path() -> Path:
    """
    Get the path to the SQLite database file.
    
    Uses the persistent data directory from paths module.
    Creates directory if it doesn't exist.
    
    Returns:
        Path to the database file
    """
    db_dir = DATA_ROOT
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / DB_FILENAME


# ============================================================================
# CONNECTION MANAGEMENT
# ============================================================================

def connect() -> sqlite3.Connection:
    """
    Create a connection to the SQLite database.
    
    Enables foreign keys and sets row_factory for dict-like access.
    
    Returns:
        sqlite3.Connection with row_factory set
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Initialize the database schema.
    
    Creates tables and indexes if they don't exist.
    Safe to call multiple times.
    """
    conn = connect()
    cursor = conn.cursor()
    
    # Create runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            model_version TEXT DEFAULT 'v3.2',
            notes TEXT
        )
    """)
    
    # Create games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            game_date TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_team TEXT NOT NULL,
            start_time_utc TEXT,
            status TEXT DEFAULT 'scheduled',
            away_score INTEGER,
            home_score INTEGER,
            last_checked_at TEXT
        )
    """)
    
    # Create picks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS picks (
            pick_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            game_id TEXT NOT NULL REFERENCES games(game_id),
            matchup TEXT NOT NULL,
            pick_team TEXT NOT NULL,
            pick_side TEXT NOT NULL,
            conf_pct REAL NOT NULL,
            bucket TEXT NOT NULL,
            pred_away_score INTEGER,
            pred_home_score INTEGER,
            pred_total REAL,
            range_low REAL,
            range_high REAL,
            internal_edge REAL,
            internal_margin REAL,
            result TEXT DEFAULT 'PENDING',
            graded_at TEXT
        )
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_run_id ON picks(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_bucket ON picks(bucket)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_result ON picks(result)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_game_id ON picks(game_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)")
    
    conn.commit()
    conn.close()


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class WinrateStats:
    """Statistics computed from prediction history."""
    # Overall
    total_picks: int = 0
    total_graded: int = 0
    wins: int = 0
    losses: int = 0
    win_pct: float = 0.0
    pending: int = 0
    
    # By bucket - HIGH
    high_total: int = 0
    high_graded: int = 0
    high_wins: int = 0
    high_losses: int = 0
    high_win_pct: float = 0.0
    high_pending: int = 0
    
    # By bucket - MEDIUM
    med_total: int = 0
    med_graded: int = 0
    med_wins: int = 0
    med_losses: int = 0
    med_win_pct: float = 0.0
    med_pending: int = 0
    
    # By bucket - LOW
    low_total: int = 0
    low_graded: int = 0
    low_wins: int = 0
    low_losses: int = 0
    low_win_pct: float = 0.0
    low_pending: int = 0


# ============================================================================
# CRUD OPERATIONS
# ============================================================================

def generate_game_id(game_date: str, away_team: str, home_team: str) -> str:
    """
    Generate a stable game ID from date and teams.
    
    Args:
        game_date: Date in YYYY-MM-DD format
        away_team: Away team abbreviation
        home_team: Home team abbreviation
    
    Returns:
        Stable game ID string
    """
    return f"{game_date}:{away_team}@{home_team}"


def upsert_game(
    game_id: str,
    game_date: str,
    away_team: str,
    home_team: str,
    start_time_utc: Optional[str] = None,
    status: str = "scheduled",
    away_score: Optional[int] = None,
    home_score: Optional[int] = None,
) -> str:
    """
    Insert or update a game record.
    
    Args:
        game_id: Unique game identifier (from API or generated)
        game_date: Date in YYYY-MM-DD format
        away_team: Away team abbreviation
        home_team: Home team abbreviation
        start_time_utc: Game start time (optional)
        status: Game status (scheduled, in_progress, final)
        away_score: Away team final score (optional)
        home_score: Home team final score (optional)
    
    Returns:
        The game_id
    """
    conn = connect()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT INTO games (game_id, game_date, away_team, home_team, start_time_utc, 
                          status, away_score, home_score, last_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(game_id) DO UPDATE SET
            status = COALESCE(excluded.status, status),
            away_score = COALESCE(excluded.away_score, away_score),
            home_score = COALESCE(excluded.home_score, home_score),
            last_checked_at = excluded.last_checked_at
    """, (game_id, game_date, away_team, home_team, start_time_utc,
          status, away_score, home_score, now))
    
    conn.commit()
    conn.close()
    
    return game_id


def insert_run(
    run_date: str,
    model_version: str = "v3.2",
    notes: Optional[str] = None,
) -> str:
    """
    Insert a new prediction run record.
    
    Args:
        run_date: Date of the run in YYYY-MM-DD format
        model_version: Version string for the model
        notes: Optional notes about the run
    
    Returns:
        The generated run_id
    """
    conn = connect()
    cursor = conn.cursor()
    
    run_id = str(uuid4())
    created_at = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT INTO runs (run_id, run_date, created_at, model_version, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, run_date, created_at, model_version, notes))
    
    conn.commit()
    conn.close()
    
    return run_id


def upsert_pick(
    pick_id: str,
    run_id: str,
    game_id: str,
    matchup: str,
    pick_team: str,
    pick_side: str,
    conf_pct: float,
    bucket: str,
    pred_away_score: Optional[int] = None,
    pred_home_score: Optional[int] = None,
    pred_total: Optional[float] = None,
    range_low: Optional[float] = None,
    range_high: Optional[float] = None,
    internal_edge: Optional[float] = None,
    internal_margin: Optional[float] = None,
    result: str = "PENDING",
) -> str:
    """
    Insert or update a pick record.
    
    Args:
        pick_id: Unique pick identifier
        run_id: Reference to the prediction run
        game_id: Reference to the game
        matchup: Matchup string (e.g., "BOS @ NYK")
        pick_team: Picked team abbreviation
        pick_side: "HOME" or "AWAY"
        conf_pct: Confidence percentage (0-100)
        bucket: Confidence bucket (HIGH, MEDIUM, LOW)
        pred_away_score: Predicted away score
        pred_home_score: Predicted home score
        pred_total: Predicted total
        range_low: Low end of predicted range
        range_high: High end of predicted range
        internal_edge: Internal edge score
        internal_margin: Internal margin
        result: W, L, or PENDING
    
    Returns:
        The pick_id
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO picks (pick_id, run_id, game_id, matchup, pick_team, pick_side,
                          conf_pct, bucket, pred_away_score, pred_home_score,
                          pred_total, range_low, range_high, internal_edge,
                          internal_margin, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pick_id) DO UPDATE SET
            result = excluded.result
    """, (pick_id, run_id, game_id, matchup, pick_team, pick_side,
          conf_pct, bucket, pred_away_score, pred_home_score,
          pred_total, range_low, range_high, internal_edge,
          internal_margin, result))
    
    conn.commit()
    conn.close()
    
    return pick_id


def get_ungraded_picks(game_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get picks that haven't been graded yet.
    
    Args:
        game_date: Optional date filter (YYYY-MM-DD)
    
    Returns:
        List of ungraded pick records with game info
    """
    conn = connect()
    cursor = conn.cursor()
    
    if game_date:
        cursor.execute("""
            SELECT p.*, g.away_team, g.home_team, g.status, g.away_score, g.home_score
            FROM picks p
            JOIN games g ON p.game_id = g.game_id
            WHERE p.result = 'PENDING' AND g.game_date = ?
            ORDER BY p.conf_pct DESC
        """, (game_date,))
    else:
        cursor.execute("""
            SELECT p.*, g.away_team, g.home_team, g.status, g.away_score, g.home_score
            FROM picks p
            JOIN games g ON p.game_id = g.game_id
            WHERE p.result = 'PENDING'
            ORDER BY g.game_date DESC, p.conf_pct DESC
        """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_games_for_date(game_date: str) -> List[Dict[str, Any]]:
    """
    Get all games for a specific date.
    
    Args:
        game_date: Date in YYYY-MM-DD format
    
    Returns:
        List of game records
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM games
        WHERE game_date = ?
        ORDER BY start_time_utc
    """, (game_date,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def update_game_score(
    game_id: str,
    status: str,
    away_score: Optional[int],
    home_score: Optional[int],
):
    """
    Update a game's score and status.
    
    Args:
        game_id: Game identifier
        status: New status (scheduled, in_progress, final)
        away_score: Away team score
        home_score: Home team score
    """
    conn = connect()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE games
        SET status = ?, away_score = ?, home_score = ?, last_checked_at = ?
        WHERE game_id = ?
    """, (status, away_score, home_score, now, game_id))
    
    conn.commit()
    conn.close()


def grade_pick(pick_id: str, result: str):
    """
    Grade a pick as W or L.
    
    Args:
        pick_id: Pick identifier
        result: "W" or "L"
    """
    conn = connect()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE picks
        SET result = ?, graded_at = ?
        WHERE pick_id = ?
    """, (result, now, pick_id))
    
    conn.commit()
    conn.close()


def compute_stats() -> WinrateStats:
    """
    Compute win rate statistics from the database.
    
    Returns:
        WinrateStats object with overall and per-bucket stats
    """
    stats = WinrateStats()
    
    conn = connect()
    cursor = conn.cursor()
    
    # Overall stats
    cursor.execute("SELECT COUNT(*) FROM picks")
    stats.total_picks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE result IN ('W', 'L')")
    stats.total_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE result = 'W'")
    stats.wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE result = 'L'")
    stats.losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE result = 'PENDING' OR result IS NULL")
    stats.pending = cursor.fetchone()[0]
    
    if stats.total_graded > 0:
        stats.win_pct = (stats.wins / stats.total_graded) * 100
    
    # HIGH bucket
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'HIGH'")
    stats.high_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'HIGH' AND result IN ('W', 'L')")
    stats.high_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'HIGH' AND result = 'W'")
    stats.high_wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'HIGH' AND result = 'L'")
    stats.high_losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'HIGH' AND (result = 'PENDING' OR result IS NULL)")
    stats.high_pending = cursor.fetchone()[0]
    
    if stats.high_graded > 0:
        stats.high_win_pct = (stats.high_wins / stats.high_graded) * 100
    
    # MEDIUM bucket
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'MEDIUM'")
    stats.med_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'MEDIUM' AND result IN ('W', 'L')")
    stats.med_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'MEDIUM' AND result = 'W'")
    stats.med_wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'MEDIUM' AND result = 'L'")
    stats.med_losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'MEDIUM' AND (result = 'PENDING' OR result IS NULL)")
    stats.med_pending = cursor.fetchone()[0]
    
    if stats.med_graded > 0:
        stats.med_win_pct = (stats.med_wins / stats.med_graded) * 100
    
    # LOW bucket
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'LOW'")
    stats.low_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'LOW' AND result IN ('W', 'L')")
    stats.low_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'LOW' AND result = 'W'")
    stats.low_wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'LOW' AND result = 'L'")
    stats.low_losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM picks WHERE bucket = 'LOW' AND (result = 'PENDING' OR result IS NULL)")
    stats.low_pending = cursor.fetchone()[0]
    
    if stats.low_graded > 0:
        stats.low_win_pct = (stats.low_wins / stats.low_graded) * 100
    
    conn.close()
    
    return stats


def get_recent_picks(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get the most recent picks with game info.
    
    Args:
        limit: Maximum number of picks to return
    
    Returns:
        List of pick records with game info
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.*, g.away_team, g.home_team, g.game_date, g.status, 
               g.away_score, g.home_score, r.created_at as run_created_at
        FROM picks p
        JOIN games g ON p.game_id = g.game_id
        JOIN runs r ON p.run_id = r.run_id
        ORDER BY r.created_at DESC, p.conf_pct DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def export_to_csv(filepath: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """
    Export picks to a CSV file.
    
    Args:
        filepath: Path to output CSV file
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
    """
    conn = connect()
    cursor = conn.cursor()
    
    query = """
        SELECT g.game_date, g.away_team, g.home_team, p.pick_team, p.pick_side,
               p.conf_pct, p.bucket, p.pred_away_score, p.pred_home_score,
               p.pred_total, g.away_score as actual_away, g.home_score as actual_home,
               p.result, r.created_at as run_timestamp
        FROM picks p
        JOIN games g ON p.game_id = g.game_id
        JOIN runs r ON p.run_id = r.run_id
    """
    
    params = []
    conditions = []
    
    if start_date:
        conditions.append("g.game_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("g.game_date <= ?")
        params.append(end_date)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY g.game_date DESC, r.created_at DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    conn.close()
    
    # Write to CSV
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'Date', 'Away', 'Home', 'Pick', 'Side', 'Conf%', 'Bucket',
            'Pred_Away', 'Pred_Home', 'Pred_Total', 'Actual_Away', 'Actual_Home',
            'Result', 'Run_Timestamp'
        ])
        
        # Data
        for row in rows:
            writer.writerow(list(row))


# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize database on module import
init_db()
