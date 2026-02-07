"""
Persistent Path Management for NBA Prediction Engine.

This module provides stable, user-accessible paths that work correctly in:
- Development mode (running from source with python)
- Frozen mode (PyInstaller executable)

IMPORTANT: Never use Path(__file__) for persistent storage in frozen builds.
PyInstaller extracts files to a temporary _MEI folder that is deleted on exit.

Path Layout:
  Windows:  %APPDATA%\\NBA_Engine\\
  macOS:    ~/Library/Application Support/NBA_Engine/
  Linux:    ~/.local/share/NBA_Engine/

Subdirectories:
  - tracking/   -> NBA_Engine_Tracking.xlsx
  - logs/       -> run.log, debug.log
  - cache/      -> any cached data
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple


# ==============================================================================
# APP DETECTION
# ==============================================================================

def is_frozen() -> bool:
    """Check if running as a frozen PyInstaller executable."""
    return getattr(sys, 'frozen', False)


def get_frozen_temp_dir() -> Optional[Path]:
    """Get PyInstaller's temporary extraction directory (if frozen)."""
    if is_frozen() and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return None


# ==============================================================================
# PERSISTENT DATA ROOT
# ==============================================================================

def get_data_root() -> Path:
    """
    Get the persistent data root directory for the application.
    
    This returns a stable, user-accessible location that persists after
    the application exits, regardless of how it was launched.
    
    Returns:
        Path to the app data directory (created if needed)
    """
    if os.name == 'nt':  # Windows
        # Prefer APPDATA (C:\\Users\\<user>\\AppData\\Roaming)
        appdata = os.getenv('APPDATA')
        if appdata:
            data_root = Path(appdata) / 'NBA_Engine'
        else:
            # Fallback to Documents
            data_root = Path.home() / 'Documents' / 'NBA_Engine'
    elif sys.platform == 'darwin':  # macOS
        data_root = Path.home() / 'Library' / 'Application Support' / 'NBA_Engine'
    else:  # Linux and others
        # Follow XDG Base Directory Specification
        xdg_data = os.getenv('XDG_DATA_HOME')
        if xdg_data:
            data_root = Path(xdg_data) / 'NBA_Engine'
        else:
            data_root = Path.home() / '.local' / 'share' / 'NBA_Engine'
    
    return data_root


def get_source_project_root() -> Optional[Path]:
    """
    Get the project root when running from source.
    
    Returns None if running as frozen executable.
    """
    if is_frozen():
        return None
    
    # When running from source, __file__ is reliable
    # This file is at nba_engine/paths.py, so parent is nba_engine/
    return Path(__file__).parent


# ==============================================================================
# DIRECTORY PATHS
# ==============================================================================

# Main data root
DATA_ROOT = get_data_root()

# Subdirectories
TRACKING_DIR = DATA_ROOT / 'tracking'
LOG_DIR = DATA_ROOT / 'logs'
CACHE_DIR = DATA_ROOT / 'cache'

# Ensure all directories exist
for _dir in [DATA_ROOT, TRACKING_DIR, LOG_DIR, CACHE_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# FILE PATHS
# ==============================================================================

TRACKING_FILE_PATH = TRACKING_DIR / 'NBA_Engine_Tracking.xlsx'
RUN_LOG_PATH = LOG_DIR / 'run.log'
DEBUG_LOG_PATH = LOG_DIR / 'debug.log'


# ==============================================================================
# LEGACY PATH DETECTION (for migration)
# ==============================================================================

def get_legacy_tracking_paths() -> List[Path]:
    """
    Get list of potential legacy tracking file locations.
    
    These are paths where older versions may have written the tracking file.
    Used for migration to the new persistent location.
    """
    legacy_paths = []
    
    # Old relative path from source runs
    source_root = get_source_project_root()
    if source_root:
        legacy_paths.append(source_root / 'outputs' / 'tracking' / 'NBA_Engine_Tracking.xlsx')
    
    # Current working directory (common mistake)
    cwd = Path.cwd()
    legacy_paths.append(cwd / 'outputs' / 'tracking' / 'NBA_Engine_Tracking.xlsx')
    legacy_paths.append(cwd / 'NBA_Engine_Tracking.xlsx')
    
    # User Documents (another common location)
    docs = Path.home() / 'Documents'
    legacy_paths.append(docs / 'NBA_Engine_Tracking.xlsx')
    legacy_paths.append(docs / 'NBA_Engine' / 'NBA_Engine_Tracking.xlsx')
    
    # Filter to unique paths that aren't the new canonical path
    seen = set()
    unique_paths = []
    canonical = TRACKING_FILE_PATH.resolve()
    
    for p in legacy_paths:
        try:
            resolved = p.resolve()
            if resolved not in seen and resolved != canonical:
                seen.add(resolved)
                unique_paths.append(p)
        except (OSError, ValueError):
            pass
    
    return unique_paths


def migrate_legacy_tracking_file() -> Tuple[bool, str]:
    """
    Migrate tracking file from legacy location to new persistent location.
    
    Returns:
        Tuple of (migrated: bool, message: str)
    """
    # If new file already exists, don't migrate
    if TRACKING_FILE_PATH.exists():
        return False, f"Tracking file already exists at: {TRACKING_FILE_PATH}"
    
    # Search legacy locations
    for legacy_path in get_legacy_tracking_paths():
        if legacy_path.exists():
            try:
                # Copy to new location (don't move, safer)
                shutil.copy2(legacy_path, TRACKING_FILE_PATH)
                msg = f"Migrated tracking file from {legacy_path} to {TRACKING_FILE_PATH}"
                return True, msg
            except Exception as e:
                return False, f"Migration failed from {legacy_path}: {e}"
    
    return False, "No legacy tracking file found to migrate"


def check_for_duplicate_tracking_files() -> List[Path]:
    """
    Check for tracking files in multiple locations (potential confusion).
    
    Returns list of paths where tracking files exist.
    """
    found = []
    
    # Check canonical location
    if TRACKING_FILE_PATH.exists():
        found.append(TRACKING_FILE_PATH)
    
    # Check legacy locations
    for legacy_path in get_legacy_tracking_paths():
        if legacy_path.exists():
            found.append(legacy_path)
    
    return found


# ==============================================================================
# LOGGING SETUP
# ==============================================================================

def setup_file_logging():
    """
    Configure logging to write to persistent log file.
    
    This ensures logs survive after the app exits.
    """
    # Create a file handler for the run log
    file_handler = logging.FileHandler(RUN_LOG_PATH, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    
    return file_handler


def log_startup_diagnostics():
    """
    Log diagnostic information about paths and environment.
    
    This helps debug path issues in the future.
    """
    lines = [
        "",
        "=" * 60,
        f"NBA Engine Startup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        f"Frozen (PyInstaller): {is_frozen()}",
        f"Python executable: {sys.executable}",
        f"Current working dir: {os.getcwd()}",
    ]
    
    # Frozen-specific info
    if is_frozen():
        temp_dir = get_frozen_temp_dir()
        lines.append(f"PyInstaller temp dir: {temp_dir}")
    else:
        lines.append(f"Source __file__: {__file__}")
        lines.append(f"Project root: {get_source_project_root()}")
    
    # Path info
    lines.extend([
        "",
        "Persistent Paths:",
        f"  Data root:     {DATA_ROOT}",
        f"  Tracking dir:  {TRACKING_DIR}",
        f"  Log dir:       {LOG_DIR}",
        f"  Tracking file: {TRACKING_FILE_PATH}",
        f"  Run log:       {RUN_LOG_PATH}",
        "",
        f"Tracking file exists: {TRACKING_FILE_PATH.exists()}",
    ])
    
    # Check for duplicates
    duplicates = check_for_duplicate_tracking_files()
    if len(duplicates) > 1:
        lines.append("")
        lines.append("WARNING: Multiple tracking files found!")
        for p in duplicates:
            lines.append(f"  - {p}")
        lines.append(f"Canonical location: {TRACKING_FILE_PATH}")
    
    # Write to log file
    log_text = "\n".join(lines) + "\n"
    
    try:
        with open(RUN_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(log_text)
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")
    
    # Also print to console
    print(log_text)
    
    return log_text


def get_tracking_path_message() -> str:
    """Get a user-friendly message about where the tracking file is saved."""
    return f"Tracking workbook location: {TRACKING_FILE_PATH}"


# ==============================================================================
# MODULE INITIALIZATION
# ==============================================================================

# Run migration check on import (safe, only copies if needed)
_migration_result = migrate_legacy_tracking_file()
if _migration_result[0]:
    print(f"[MIGRATION] {_migration_result[1]}")


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    # Detection
    'is_frozen',
    'get_frozen_temp_dir',
    # Paths
    'DATA_ROOT',
    'TRACKING_DIR',
    'LOG_DIR',
    'CACHE_DIR',
    'TRACKING_FILE_PATH',
    'RUN_LOG_PATH',
    'DEBUG_LOG_PATH',
    # Functions
    'get_data_root',
    'get_source_project_root',
    'get_legacy_tracking_paths',
    'migrate_legacy_tracking_file',
    'check_for_duplicate_tracking_files',
    'setup_file_logging',
    'log_startup_diagnostics',
    'get_tracking_path_message',
]
