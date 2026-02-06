"""Storage module for persistent prediction tracking with daily slate and per-game locking."""

from .db import (
    # Database
    get_db_path,
    connect,
    init_db,
    
    # Daily slates
    upsert_daily_slate,
    get_daily_slate,
    
    # Games
    upsert_game,
    get_game,
    get_games_for_date,
    update_game_score,
    generate_game_id,
    
    # Daily picks (with locking)
    upsert_daily_pick_if_unlocked,
    get_daily_picks,
    get_daily_pick,
    grade_daily_pick,
    get_ungraded_daily_picks,
    
    # Locking
    is_game_locked,
    lock_game_if_started,
    lock_all_started_games,
    
    # Stats and export
    compute_stats,
    export_to_csv,
    WinrateStats,
    DailyPick,
    
    # Time helpers
    get_now_local,
    get_today_date_local,
    utc_to_local,
    
    # Legacy compatibility
    insert_run,
    upsert_pick,
    get_ungraded_picks,
    grade_pick,
)

__all__ = [
    'get_db_path',
    'connect',
    'init_db',
    'upsert_daily_slate',
    'get_daily_slate',
    'upsert_game',
    'get_game',
    'get_games_for_date',
    'update_game_score',
    'generate_game_id',
    'upsert_daily_pick_if_unlocked',
    'get_daily_picks',
    'get_daily_pick',
    'grade_daily_pick',
    'get_ungraded_daily_picks',
    'is_game_locked',
    'lock_game_if_started',
    'lock_all_started_games',
    'compute_stats',
    'export_to_csv',
    'WinrateStats',
    'DailyPick',
    'get_now_local',
    'get_today_date_local',
    'utc_to_local',
    'insert_run',
    'upsert_pick',
    'get_ungraded_picks',
    'grade_pick',
]
