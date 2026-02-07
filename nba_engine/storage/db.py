"""
SQLite storage layer for NBA Prediction Engine.

Provides persistent tracking of predictions and results without
requiring Excel or external spreadsheet dependencies.

Tables:
- daily_slates: One entry per day with latest run metadata
- games: NBA game data including scores, status, and start times
- daily_picks: Pick records keyed by (slate_date, game_id) with locking support

Locking Logic:
- Picks for games that haven't started can be overwritten by later runs
- Once a game starts (based on start_time_local), its pick is locked
- Locked picks cannot be overwritten by subsequent runs that day
"""

import sqlite3
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
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
    Performs migrations for existing tables.
    Safe to call multiple times.
    """
    conn = connect()
    cursor = conn.cursor()
    
    # =========================================================================
    # Legacy tables (kept for backward compatibility and migration)
    # =========================================================================
    
    # Create runs table (legacy)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            model_version TEXT DEFAULT 'v3.2',
            notes TEXT
        )
    """)
    
    # Create picks table (legacy)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS picks (
            pick_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            game_id TEXT NOT NULL,
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
    
    # =========================================================================
    # New tables for daily slate with per-game locking
    # =========================================================================
    
    # Create daily_slates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_slates (
            slate_date TEXT PRIMARY KEY,
            last_run_at TEXT NOT NULL,
            model_version TEXT DEFAULT 'v3.2',
            notes TEXT
        )
    """)
    
    # Create games table (updated with start_time_local)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            game_date TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_team TEXT NOT NULL,
            start_time_utc TEXT,
            start_time_local TEXT,
            status TEXT DEFAULT 'scheduled',
            away_score INTEGER,
            home_score INTEGER,
            last_checked_at TEXT
        )
    """)
    
    # Try to add start_time_local column if it doesn't exist (migration)
    try:
        cursor.execute("ALTER TABLE games ADD COLUMN start_time_local TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Create daily_picks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_picks (
            slate_date TEXT NOT NULL,
            game_id TEXT NOT NULL,
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
            locked INTEGER DEFAULT 0,
            locked_at TEXT,
            result TEXT DEFAULT 'PENDING',
            graded_at TEXT,
            PRIMARY KEY (slate_date, game_id)
        )
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_picks_slate ON daily_picks(slate_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_picks_bucket ON daily_picks(bucket)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_picks_result ON daily_picks(result)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_picks_locked ON daily_picks(locked)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)")
    
    # Legacy indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_run_id ON picks(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_bucket ON picks(bucket)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_result ON picks(result)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_picks_game_id ON picks(game_id)")
    
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


@dataclass
class DailyPick:
    """Represents a pick for a specific game on a specific date."""
    slate_date: str
    game_id: str
    matchup: str
    pick_team: str
    pick_side: str
    conf_pct: float
    bucket: str
    pred_away_score: Optional[int] = None
    pred_home_score: Optional[int] = None
    pred_total: Optional[float] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    internal_edge: Optional[float] = None
    internal_margin: Optional[float] = None
    locked: bool = False
    locked_at: Optional[str] = None
    result: str = "PENDING"
    graded_at: Optional[str] = None


# ============================================================================
# HELPER FUNCTIONS
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


def get_now_local() -> str:
    """
    Get current time in Eastern Time as ISO string.
    
    Returns:
        ISO formatted datetime string in ET
    """
    now_utc = datetime.now(timezone.utc)
    # ET offset (simplified - doesn't handle DST precisely)
    et_offset = timedelta(hours=-5)
    now_et = now_utc + et_offset
    return now_et.strftime("%Y-%m-%dT%H:%M:%S")


def get_today_date_local() -> str:
    """
    Get today's date in Eastern Time as YYYY-MM-DD.
    
    Returns:
        Date string in YYYY-MM-DD format
    """
    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-5)
    now_et = now_utc + et_offset
    return now_et.strftime("%Y-%m-%d")


def utc_to_local(utc_str: str) -> Optional[str]:
    """
    Convert UTC time string to local (ET) time string.
    
    Args:
        utc_str: ISO formatted UTC datetime string
    
    Returns:
        ISO formatted ET datetime string, or None if parsing fails
    """
    if not utc_str:
        return None
    
    try:
        # Parse UTC time
        if 'Z' in utc_str:
            utc_str = utc_str.replace('Z', '+00:00')
        
        # Handle various formats
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S"]:
            try:
                dt = datetime.strptime(utc_str.split('+')[0].split('-')[0:3][0] + '-' + 
                                       utc_str.split('-')[1] + '-' + utc_str.split('-')[2][:2] + 
                                       'T' + utc_str.split('T')[1][:8], "%Y-%m-%dT%H:%M:%S")
                break
            except:
                continue
        else:
            # Fallback: just parse as-is
            dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        
        # Convert to ET
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        et_offset = timedelta(hours=-5)
        dt_et = dt + et_offset
        return dt_et.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


# ============================================================================
# DAILY SLATE OPERATIONS
# ============================================================================

def upsert_daily_slate(
    slate_date: str,
    last_run_at: str,
    model_version: str = "v3.2",
    notes: Optional[str] = None,
):
    """
    Insert or update a daily slate record.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        last_run_at: ISO timestamp of this run
        model_version: Model version string
        notes: Optional notes
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO daily_slates (slate_date, last_run_at, model_version, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(slate_date) DO UPDATE SET
            last_run_at = excluded.last_run_at,
            model_version = excluded.model_version,
            notes = COALESCE(excluded.notes, notes)
    """, (slate_date, last_run_at, model_version, notes))
    
    conn.commit()
    conn.close()


def get_daily_slate(slate_date: str) -> Optional[Dict[str, Any]]:
    """
    Get the daily slate for a specific date.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
    
    Returns:
        Slate record or None if not found
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM daily_slates WHERE slate_date = ?", (slate_date,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


# ============================================================================
# GAME OPERATIONS
# ============================================================================

def upsert_game(
    game_id: str,
    game_date: str,
    away_team: str,
    home_team: str,
    start_time_utc: Optional[str] = None,
    start_time_local: Optional[str] = None,
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
        start_time_utc: Game start time in UTC (optional)
        start_time_local: Game start time in local/ET (optional)
        status: Game status (scheduled, in_progress, final)
        away_score: Away team final score (optional)
        home_score: Home team final score (optional)
    
    Returns:
        The game_id
    """
    conn = connect()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Convert UTC to local if local not provided but UTC is
    if start_time_local is None and start_time_utc is not None:
        start_time_local = utc_to_local(start_time_utc)
    
    cursor.execute("""
        INSERT INTO games (game_id, game_date, away_team, home_team, start_time_utc,
                          start_time_local, status, away_score, home_score, last_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(game_id) DO UPDATE SET
            start_time_utc = COALESCE(excluded.start_time_utc, start_time_utc),
            start_time_local = COALESCE(excluded.start_time_local, start_time_local),
            status = COALESCE(excluded.status, status),
            away_score = COALESCE(excluded.away_score, away_score),
            home_score = COALESCE(excluded.home_score, home_score),
            last_checked_at = excluded.last_checked_at
    """, (game_id, game_date, away_team, home_team, start_time_utc,
          start_time_local, status, away_score, home_score, now))
    
    conn.commit()
    conn.close()
    
    return game_id


def get_game(game_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a game by ID.
    
    Args:
        game_id: Game identifier
    
    Returns:
        Game record or None
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


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
        ORDER BY start_time_local, start_time_utc
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


# ============================================================================
# LOCKING LOGIC
# ============================================================================

def is_game_locked(slate_date: str, game_id: str, now_local: Optional[str] = None) -> bool:
    """
    Check if a game's pick is locked (game has started).
    
    A game is locked if:
    - The daily_picks row has locked=1, OR
    - now_local >= game.start_time_local, OR
    - game.status is in_progress or final
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        game_id: Game identifier
        now_local: Current local time (ISO), defaults to now
    
    Returns:
        True if game is locked
    """
    if now_local is None:
        now_local = get_now_local()
    
    conn = connect()
    cursor = conn.cursor()
    
    # Check if already marked locked in daily_picks
    cursor.execute("""
        SELECT locked FROM daily_picks
        WHERE slate_date = ? AND game_id = ?
    """, (slate_date, game_id))
    row = cursor.fetchone()
    
    if row and row['locked'] == 1:
        conn.close()
        return True
    
    # Check game status and start time
    cursor.execute("""
        SELECT start_time_local, status FROM games
        WHERE game_id = ?
    """, (game_id,))
    game_row = cursor.fetchone()
    conn.close()
    
    if game_row:
        # Game is locked if in_progress or final
        if game_row['status'] in ('in_progress', 'final'):
            return True
        
        # Game is locked if start time has passed
        start_time = game_row['start_time_local']
        if start_time and now_local >= start_time:
            return True
    
    return False


def lock_game_if_started(slate_date: str, game_id: str, now_local: Optional[str] = None) -> bool:
    """
    Lock a game's pick if the game has started.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        game_id: Game identifier
        now_local: Current local time (ISO), defaults to now
    
    Returns:
        True if game was locked (or already locked)
    """
    if now_local is None:
        now_local = get_now_local()
    
    conn = connect()
    cursor = conn.cursor()
    
    # Check game start time and status
    cursor.execute("""
        SELECT start_time_local, status FROM games
        WHERE game_id = ?
    """, (game_id,))
    game_row = cursor.fetchone()
    
    should_lock = False
    if game_row:
        # Lock if in_progress or final
        if game_row['status'] in ('in_progress', 'final'):
            should_lock = True
        # Lock if start time has passed
        elif game_row['start_time_local'] and now_local >= game_row['start_time_local']:
            should_lock = True
    
    if should_lock:
        # Update the pick to be locked
        cursor.execute("""
            UPDATE daily_picks
            SET locked = 1, locked_at = ?
            WHERE slate_date = ? AND game_id = ? AND locked = 0
        """, (now_local, slate_date, game_id))
        conn.commit()
    
    conn.close()
    return should_lock


def lock_all_started_games(slate_date: str, now_local: Optional[str] = None) -> int:
    """
    Lock all games that have started for a given slate date.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        now_local: Current local time (ISO), defaults to now
    
    Returns:
        Number of games locked
    """
    if now_local is None:
        now_local = get_now_local()
    
    conn = connect()
    cursor = conn.cursor()
    
    # Get all unlocked picks for this slate
    cursor.execute("""
        SELECT dp.game_id, g.start_time_local, g.status
        FROM daily_picks dp
        JOIN games g ON dp.game_id = g.game_id
        WHERE dp.slate_date = ? AND dp.locked = 0
    """, (slate_date,))
    
    unlocked = cursor.fetchall()
    locked_count = 0
    
    for row in unlocked:
        should_lock = False
        
        # Lock if game status is in_progress or final
        if row['status'] in ('in_progress', 'final'):
            should_lock = True
        # Lock if start time has passed
        elif row['start_time_local'] and now_local >= row['start_time_local']:
            should_lock = True
        
        if should_lock:
            cursor.execute("""
                UPDATE daily_picks
                SET locked = 1, locked_at = ?
                WHERE slate_date = ? AND game_id = ?
            """, (now_local, slate_date, row['game_id']))
            locked_count += 1
    
    conn.commit()
    conn.close()
    
    return locked_count


# ============================================================================
# DAILY PICK OPERATIONS
# ============================================================================

def upsert_daily_pick_if_unlocked(
    slate_date: str,
    game_id: str,
    pick_data: Dict[str, Any],
    now_local: Optional[str] = None,
) -> Tuple[bool, bool]:
    """
    Insert or update a daily pick, but only if not locked.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        game_id: Game identifier
        pick_data: Dictionary with pick fields
        now_local: Current local time (ISO), defaults to now
    
    Returns:
        Tuple of (was_saved, is_locked)
    """
    if now_local is None:
        now_local = get_now_local()
    
    conn = connect()
    cursor = conn.cursor()
    
    # First, check if game has started and should be locked
    cursor.execute("""
        SELECT start_time_local, status FROM games
        WHERE game_id = ?
    """, (game_id,))
    game_row = cursor.fetchone()
    
    game_started = False
    if game_row:
        if game_row['status'] in ('in_progress', 'final'):
            game_started = True
        elif game_row['start_time_local'] and now_local >= game_row['start_time_local']:
            game_started = True
    
    # Check if pick already exists and is locked
    cursor.execute("""
        SELECT locked FROM daily_picks
        WHERE slate_date = ? AND game_id = ?
    """, (slate_date, game_id))
    existing = cursor.fetchone()
    
    if existing and existing['locked'] == 1:
        # Already locked, don't update
        conn.close()
        return (False, True)
    
    if game_started:
        # Game has started - lock the existing pick if there is one, don't save new one
        if existing:
            cursor.execute("""
                UPDATE daily_picks
                SET locked = 1, locked_at = ?
                WHERE slate_date = ? AND game_id = ?
            """, (now_local, slate_date, game_id))
            conn.commit()
        conn.close()
        return (False, True)
    
    # Game hasn't started - save/update the pick
    cursor.execute("""
        INSERT INTO daily_picks (
            slate_date, game_id, matchup, pick_team, pick_side,
            conf_pct, bucket, pred_away_score, pred_home_score,
            pred_total, range_low, range_high, internal_edge,
            internal_margin, locked, result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'PENDING')
        ON CONFLICT(slate_date, game_id) DO UPDATE SET
            matchup = excluded.matchup,
            pick_team = excluded.pick_team,
            pick_side = excluded.pick_side,
            conf_pct = excluded.conf_pct,
            bucket = excluded.bucket,
            pred_away_score = excluded.pred_away_score,
            pred_home_score = excluded.pred_home_score,
            pred_total = excluded.pred_total,
            range_low = excluded.range_low,
            range_high = excluded.range_high,
            internal_edge = excluded.internal_edge,
            internal_margin = excluded.internal_margin
        WHERE locked = 0
    """, (
        slate_date,
        game_id,
        pick_data.get('matchup', ''),
        pick_data.get('pick_team', ''),
        pick_data.get('pick_side', ''),
        pick_data.get('conf_pct', 0),
        pick_data.get('bucket', 'LOW'),
        pick_data.get('pred_away_score'),
        pick_data.get('pred_home_score'),
        pick_data.get('pred_total'),
        pick_data.get('range_low'),
        pick_data.get('range_high'),
        pick_data.get('internal_edge'),
        pick_data.get('internal_margin'),
    ))
    
    conn.commit()
    conn.close()
    
    return (True, False)


def get_daily_picks(slate_date: str) -> List[Dict[str, Any]]:
    """
    Get all picks for a specific slate date.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
    
    Returns:
        List of pick records with game info
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT dp.*, g.away_team, g.home_team, g.status, 
               g.away_score, g.home_score, g.start_time_local
        FROM daily_picks dp
        JOIN games g ON dp.game_id = g.game_id
        WHERE dp.slate_date = ?
        ORDER BY dp.conf_pct DESC
    """, (slate_date,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_daily_pick(slate_date: str, game_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific pick.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        game_id: Game identifier
    
    Returns:
        Pick record or None
    """
    conn = connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT dp.*, g.away_team, g.home_team, g.status,
               g.away_score, g.home_score, g.start_time_local
        FROM daily_picks dp
        JOIN games g ON dp.game_id = g.game_id
        WHERE dp.slate_date = ? AND dp.game_id = ?
    """, (slate_date, game_id))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


def grade_daily_pick(slate_date: str, game_id: str, result: str):
    """
    Grade a daily pick as W or L.
    
    Args:
        slate_date: Date in YYYY-MM-DD format
        game_id: Game identifier
        result: "W" or "L"
    """
    conn = connect()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Also ensure it's locked when graded
    cursor.execute("""
        UPDATE daily_picks
        SET result = ?, graded_at = ?, locked = 1, locked_at = COALESCE(locked_at, ?)
        WHERE slate_date = ? AND game_id = ?
    """, (result, now, now, slate_date, game_id))
    
    conn.commit()
    conn.close()


def get_ungraded_daily_picks(slate_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get daily picks that haven't been graded yet.
    
    Args:
        slate_date: Optional date filter (YYYY-MM-DD)
    
    Returns:
        List of ungraded pick records with game info
    """
    conn = connect()
    cursor = conn.cursor()
    
    if slate_date:
        cursor.execute("""
            SELECT dp.*, g.away_team, g.home_team, g.status, 
                   g.away_score, g.home_score, g.start_time_local
            FROM daily_picks dp
            JOIN games g ON dp.game_id = g.game_id
            WHERE dp.result = 'PENDING' AND dp.slate_date = ?
            ORDER BY dp.conf_pct DESC
        """, (slate_date,))
    else:
        cursor.execute("""
            SELECT dp.*, g.away_team, g.home_team, g.status,
                   g.away_score, g.home_score, g.start_time_local
            FROM daily_picks dp
            JOIN games g ON dp.game_id = g.game_id
            WHERE dp.result = 'PENDING'
            ORDER BY dp.slate_date DESC, dp.conf_pct DESC
        """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


# ============================================================================
# STATISTICS
# ============================================================================

def compute_stats() -> WinrateStats:
    """
    Compute win rate statistics from the database.
    
    Uses daily_picks table for stats.
    
    Returns:
        WinrateStats object with overall and per-bucket stats
    """
    stats = WinrateStats()
    
    conn = connect()
    cursor = conn.cursor()
    
    # Overall stats from daily_picks
    cursor.execute("SELECT COUNT(*) FROM daily_picks")
    stats.total_picks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE result IN ('W', 'L')")
    stats.total_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE result = 'W'")
    stats.wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE result = 'L'")
    stats.losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE result = 'PENDING' OR result IS NULL")
    stats.pending = cursor.fetchone()[0]
    
    if stats.total_graded > 0:
        stats.win_pct = (stats.wins / stats.total_graded) * 100
    
    # HIGH bucket
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'HIGH'")
    stats.high_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'HIGH' AND result IN ('W', 'L')")
    stats.high_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'HIGH' AND result = 'W'")
    stats.high_wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'HIGH' AND result = 'L'")
    stats.high_losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'HIGH' AND (result = 'PENDING' OR result IS NULL)")
    stats.high_pending = cursor.fetchone()[0]
    
    if stats.high_graded > 0:
        stats.high_win_pct = (stats.high_wins / stats.high_graded) * 100
    
    # MEDIUM bucket
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'MEDIUM'")
    stats.med_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'MEDIUM' AND result IN ('W', 'L')")
    stats.med_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'MEDIUM' AND result = 'W'")
    stats.med_wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'MEDIUM' AND result = 'L'")
    stats.med_losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'MEDIUM' AND (result = 'PENDING' OR result IS NULL)")
    stats.med_pending = cursor.fetchone()[0]
    
    if stats.med_graded > 0:
        stats.med_win_pct = (stats.med_wins / stats.med_graded) * 100
    
    # LOW bucket
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'LOW'")
    stats.low_total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'LOW' AND result IN ('W', 'L')")
    stats.low_graded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'LOW' AND result = 'W'")
    stats.low_wins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'LOW' AND result = 'L'")
    stats.low_losses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM daily_picks WHERE bucket = 'LOW' AND (result = 'PENDING' OR result IS NULL)")
    stats.low_pending = cursor.fetchone()[0]
    
    if stats.low_graded > 0:
        stats.low_win_pct = (stats.low_wins / stats.low_graded) * 100
    
    conn.close()
    
    return stats


# ============================================================================
# EXPORT
# ============================================================================

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
        SELECT dp.slate_date, g.away_team, g.home_team, dp.pick_team, dp.pick_side,
               dp.conf_pct, dp.bucket, dp.pred_away_score, dp.pred_home_score,
               dp.pred_total, g.away_score as actual_away, g.home_score as actual_home,
               dp.result, dp.locked, ds.last_run_at as run_timestamp
        FROM daily_picks dp
        JOIN games g ON dp.game_id = g.game_id
        LEFT JOIN daily_slates ds ON dp.slate_date = ds.slate_date
    """
    
    params = []
    conditions = []
    
    if start_date:
        conditions.append("dp.slate_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("dp.slate_date <= ?")
        params.append(end_date)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY dp.slate_date DESC, dp.conf_pct DESC"
    
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
            'Result', 'Locked', 'Run_Timestamp'
        ])
        
        # Data
        for row in rows:
            writer.writerow(list(row))


# ============================================================================
# LEGACY COMPATIBILITY
# ============================================================================

def insert_run(
    run_date: str,
    model_version: str = "v3.2",
    notes: Optional[str] = None,
) -> str:
    """
    Insert a new prediction run record (legacy compatibility).
    
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
    Insert or update a pick record (legacy compatibility).
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
    """Get ungraded picks (legacy compatibility - redirects to daily_picks)."""
    return get_ungraded_daily_picks(game_date)


def grade_pick(pick_id: str, result: str):
    """Grade a pick (legacy compatibility)."""
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


# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize database on module import
init_db()
