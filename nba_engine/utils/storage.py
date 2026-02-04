"""
Storage utilities for NBA Prediction Engine.

Handles reading/writing prediction logs, results, and performance summaries.
"""

import csv
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any
import json


# Base paths
BASE_DIR = Path(__file__).parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
CACHE_DIR = OUTPUTS_DIR / "cache"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Log file paths
PREDICTIONS_LOG_PATH = LOGS_DIR / "predictions_log.csv"
RESULTS_LOG_PATH = LOGS_DIR / "results_log.csv"
PERFORMANCE_SUMMARY_PATH = LOGS_DIR / "performance_summary.csv"


@dataclass
class PredictionLogEntry:
    """A single prediction log entry."""
    run_timestamp_local: str
    game_date: str  # YYYY-MM-DD
    game_id: str
    away_team: str
    home_team: str
    pick: str  # Team abbreviation
    edge_score_total: float
    projected_margin_home: float
    home_win_prob: float
    away_win_prob: float
    confidence_level: str  # HIGH/MEDIUM/LOW
    confidence_pct: str  # e.g., "65%"
    top_5_factors: str
    injury_report_url: str
    data_confidence: str  # HIGH/MEDIUM/LOW
    actual_winner: str = ""  # Filled later
    correct: str = ""  # 1 or 0 or blank
    notes: str = ""
    
    def unique_key(self) -> str:
        """Get unique key for deduplication."""
        return f"{self.game_date}|{self.home_team}|{self.away_team}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


# CSV column order
PREDICTION_LOG_COLUMNS = [
    "run_timestamp_local",
    "game_date",
    "game_id",
    "away_team",
    "home_team",
    "pick",
    "edge_score_total",
    "projected_margin_home",
    "home_win_prob",
    "away_win_prob",
    "confidence_level",
    "confidence_pct",
    "top_5_factors",
    "injury_report_url",
    "data_confidence",
    "actual_winner",
    "correct",
    "notes",
]


def load_predictions_log() -> List[PredictionLogEntry]:
    """
    Load all entries from predictions_log.csv.
    
    Returns:
        List of PredictionLogEntry objects
    """
    entries = []
    
    if not PREDICTIONS_LOG_PATH.exists():
        return entries
    
    try:
        with open(PREDICTIONS_LOG_PATH, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    entry = PredictionLogEntry(
                        run_timestamp_local=row.get('run_timestamp_local', ''),
                        game_date=row.get('game_date', ''),
                        game_id=row.get('game_id', ''),
                        away_team=row.get('away_team', ''),
                        home_team=row.get('home_team', ''),
                        pick=row.get('pick', ''),
                        edge_score_total=float(row.get('edge_score_total', 0) or 0),
                        projected_margin_home=float(row.get('projected_margin_home', 0) or 0),
                        home_win_prob=float(row.get('home_win_prob', 0) or 0),
                        away_win_prob=float(row.get('away_win_prob', 0) or 0),
                        confidence_level=row.get('confidence_level', ''),
                        confidence_pct=row.get('confidence_pct', ''),
                        top_5_factors=row.get('top_5_factors', ''),
                        injury_report_url=row.get('injury_report_url', ''),
                        data_confidence=row.get('data_confidence', 'MEDIUM'),
                        actual_winner=row.get('actual_winner', ''),
                        correct=row.get('correct', ''),
                        notes=row.get('notes', ''),
                    )
                    entries.append(entry)
                except (ValueError, KeyError) as e:
                    print(f"  Warning: Skipping malformed log entry: {e}")
                    continue
    except Exception as e:
        print(f"  Error loading predictions log: {e}")
    
    return entries


def save_predictions_log(entries: List[PredictionLogEntry]) -> None:
    """
    Save all entries to predictions_log.csv (overwrites).
    
    Args:
        entries: List of PredictionLogEntry objects
    """
    with open(PREDICTIONS_LOG_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=PREDICTION_LOG_COLUMNS)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_dict())


def append_predictions(new_entries: List[PredictionLogEntry], overwrite_existing: bool = True) -> int:
    """
    Append new predictions to the log, handling duplicates.
    
    Args:
        new_entries: New entries to add
        overwrite_existing: If True, update existing entries with same key
        
    Returns:
        Number of entries added/updated
    """
    existing = load_predictions_log()
    
    # Build lookup by unique key
    existing_by_key = {e.unique_key(): e for e in existing}
    
    added = 0
    updated = 0
    
    for new_entry in new_entries:
        key = new_entry.unique_key()
        
        if key in existing_by_key:
            if overwrite_existing:
                # Preserve actual_winner and correct if already filled
                old = existing_by_key[key]
                if old.actual_winner and not new_entry.actual_winner:
                    new_entry.actual_winner = old.actual_winner
                if old.correct and not new_entry.correct:
                    new_entry.correct = old.correct
                existing_by_key[key] = new_entry
                updated += 1
        else:
            existing_by_key[key] = new_entry
            added += 1
    
    # Rebuild list and save
    all_entries = list(existing_by_key.values())
    # Sort by game_date, then by home_team
    all_entries.sort(key=lambda e: (e.game_date, e.home_team))
    
    save_predictions_log(all_entries)
    
    return added + updated


def update_results_in_log(
    game_date: str,
    results: Dict[str, str],  # {unique_key: winner_abbrev}
) -> int:
    """
    Update actual_winner and correct fields for a specific date.
    
    Args:
        game_date: Date string YYYY-MM-DD
        results: Dict mapping unique_key to winner abbreviation
        
    Returns:
        Number of entries updated
    """
    entries = load_predictions_log()
    updated = 0
    
    for entry in entries:
        if entry.game_date == game_date:
            key = entry.unique_key()
            if key in results:
                winner = results[key]
                entry.actual_winner = winner
                entry.correct = "1" if entry.pick == winner else "0"
                updated += 1
    
    save_predictions_log(entries)
    return updated


def get_entries_for_date(game_date: str) -> List[PredictionLogEntry]:
    """Get all prediction entries for a specific date."""
    entries = load_predictions_log()
    return [e for e in entries if e.game_date == game_date]


def get_entries_needing_results() -> List[PredictionLogEntry]:
    """Get entries that have no actual_winner filled in."""
    entries = load_predictions_log()
    return [e for e in entries if not e.actual_winner]


def export_daily_predictions(
    entries: List[PredictionLogEntry],
    game_date: str,
    output_dir: Path = None,
) -> Path:
    """
    Export predictions for a date to a human-friendly CSV.
    
    Args:
        entries: Prediction entries
        game_date: Date string
        output_dir: Output directory (default OUTPUTS_DIR)
        
    Returns:
        Path to created file
    """
    if output_dir is None:
        output_dir = OUTPUTS_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Format filename
    date_str = game_date.replace("-", "")
    filepath = output_dir / f"predictions_{date_str}.csv"
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=PREDICTION_LOG_COLUMNS)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_dict())
    
    return filepath


def import_results_from_csv(filepath: Path) -> int:
    """
    Import results from a user-edited CSV file.
    
    Expects columns: game_date, home_team, away_team, actual_winner
    
    Args:
        filepath: Path to CSV file
        
    Returns:
        Number of results imported
    """
    results_by_date = {}
    
    with open(filepath, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            game_date = row.get('game_date', '')
            home_team = row.get('home_team', '')
            away_team = row.get('away_team', '')
            actual_winner = row.get('actual_winner', '').strip()
            
            if game_date and actual_winner:
                key = f"{game_date}|{home_team}|{away_team}"
                if game_date not in results_by_date:
                    results_by_date[game_date] = {}
                results_by_date[game_date][key] = actual_winner
    
    total_updated = 0
    for game_date, results in results_by_date.items():
        updated = update_results_in_log(game_date, results)
        total_updated += updated
    
    return total_updated


@dataclass
class PerformanceSummary:
    """Performance summary statistics."""
    total_games: int = 0
    wins: int = 0
    losses: int = 0
    win_pct: float = 0.0
    
    high_conf_games: int = 0
    high_conf_wins: int = 0
    high_conf_win_pct: float = 0.0
    
    med_conf_games: int = 0
    med_conf_wins: int = 0
    med_conf_win_pct: float = 0.0
    
    low_conf_games: int = 0
    low_conf_wins: int = 0
    low_conf_win_pct: float = 0.0
    
    last_7_days_games: int = 0
    last_7_days_wins: int = 0
    last_7_days_win_pct: float = 0.0
    
    last_30_days_games: int = 0
    last_30_days_wins: int = 0
    last_30_days_win_pct: float = 0.0
    
    start_date: str = ""
    end_date: str = ""
    generated_at: str = ""


def compute_performance_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> PerformanceSummary:
    """
    Compute performance summary from predictions log.
    
    Args:
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
        
    Returns:
        PerformanceSummary object
    """
    from .dates import get_eastern_date, days_ago, parse_date
    
    entries = load_predictions_log()
    
    # Filter to entries with results
    entries_with_results = [e for e in entries if e.correct in ("0", "1")]
    
    # Apply date filters
    if start_date:
        entries_with_results = [e for e in entries_with_results if e.game_date >= start_date]
    if end_date:
        entries_with_results = [e for e in entries_with_results if e.game_date <= end_date]
    
    summary = PerformanceSummary()
    summary.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not entries_with_results:
        return summary
    
    # Overall stats
    summary.total_games = len(entries_with_results)
    summary.wins = sum(1 for e in entries_with_results if e.correct == "1")
    summary.losses = summary.total_games - summary.wins
    summary.win_pct = summary.wins / summary.total_games if summary.total_games > 0 else 0.0
    
    # Date range
    dates = [e.game_date for e in entries_with_results]
    summary.start_date = min(dates)
    summary.end_date = max(dates)
    
    # By confidence level
    for level, prefix in [("high", "high_conf"), ("medium", "med_conf"), ("low", "low_conf")]:
        level_entries = [e for e in entries_with_results if e.confidence_level.lower() == level]
        games = len(level_entries)
        wins = sum(1 for e in level_entries if e.correct == "1")
        
        setattr(summary, f"{prefix}_games", games)
        setattr(summary, f"{prefix}_wins", wins)
        setattr(summary, f"{prefix}_win_pct", wins / games if games > 0 else 0.0)
    
    # Last 7 days
    today = get_eastern_date()
    last_7 = [e for e in entries_with_results 
              if days_ago(parse_date(e.game_date)) <= 7]
    summary.last_7_days_games = len(last_7)
    summary.last_7_days_wins = sum(1 for e in last_7 if e.correct == "1")
    summary.last_7_days_win_pct = (
        summary.last_7_days_wins / summary.last_7_days_games 
        if summary.last_7_days_games > 0 else 0.0
    )
    
    # Last 30 days
    last_30 = [e for e in entries_with_results 
               if days_ago(parse_date(e.game_date)) <= 30]
    summary.last_30_days_games = len(last_30)
    summary.last_30_days_wins = sum(1 for e in last_30 if e.correct == "1")
    summary.last_30_days_win_pct = (
        summary.last_30_days_wins / summary.last_30_days_games 
        if summary.last_30_days_games > 0 else 0.0
    )
    
    return summary


def save_performance_summary(summary: PerformanceSummary) -> Path:
    """
    Save performance summary to CSV.
    
    Args:
        summary: PerformanceSummary object
        
    Returns:
        Path to saved file
    """
    data = asdict(summary)
    
    with open(PERFORMANCE_SUMMARY_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Metric', 'Value'])
        
        # Format nicely
        writer.writerow(['Generated At', summary.generated_at])
        writer.writerow(['Date Range', f"{summary.start_date} to {summary.end_date}"])
        writer.writerow(['', ''])
        
        writer.writerow(['Overall Performance', ''])
        writer.writerow(['Total Games', summary.total_games])
        writer.writerow(['Wins', summary.wins])
        writer.writerow(['Losses', summary.losses])
        writer.writerow(['Win %', f"{summary.win_pct:.1%}"])
        writer.writerow(['', ''])
        
        writer.writerow(['By Confidence Level', ''])
        writer.writerow(['High Conf Games', summary.high_conf_games])
        writer.writerow(['High Conf Wins', summary.high_conf_wins])
        writer.writerow(['High Conf Win %', f"{summary.high_conf_win_pct:.1%}"])
        writer.writerow(['Med Conf Games', summary.med_conf_games])
        writer.writerow(['Med Conf Wins', summary.med_conf_wins])
        writer.writerow(['Med Conf Win %', f"{summary.med_conf_win_pct:.1%}"])
        writer.writerow(['Low Conf Games', summary.low_conf_games])
        writer.writerow(['Low Conf Wins', summary.low_conf_wins])
        writer.writerow(['Low Conf Win %', f"{summary.low_conf_win_pct:.1%}"])
        writer.writerow(['', ''])
        
        writer.writerow(['Recent Performance', ''])
        writer.writerow(['Last 7 Days Games', summary.last_7_days_games])
        writer.writerow(['Last 7 Days Wins', summary.last_7_days_wins])
        writer.writerow(['Last 7 Days Win %', f"{summary.last_7_days_win_pct:.1%}"])
        writer.writerow(['Last 30 Days Games', summary.last_30_days_games])
        writer.writerow(['Last 30 Days Wins', summary.last_30_days_wins])
        writer.writerow(['Last 30 Days Win %', f"{summary.last_30_days_win_pct:.1%}"])
    
    return PERFORMANCE_SUMMARY_PATH


def format_performance_summary(summary: PerformanceSummary) -> str:
    """Format performance summary as a string for display."""
    lines = [
        "=" * 50,
        "PERFORMANCE SUMMARY",
        "=" * 50,
        f"Date Range: {summary.start_date} to {summary.end_date}",
        "",
        f"Overall: {summary.wins}/{summary.total_games} ({summary.win_pct:.1%})",
        "",
        "By Confidence:",
        f"  HIGH:   {summary.high_conf_wins}/{summary.high_conf_games} ({summary.high_conf_win_pct:.1%})",
        f"  MEDIUM: {summary.med_conf_wins}/{summary.med_conf_games} ({summary.med_conf_win_pct:.1%})",
        f"  LOW:    {summary.low_conf_wins}/{summary.low_conf_games} ({summary.low_conf_win_pct:.1%})",
        "",
        "Recent:",
        f"  Last 7 days:  {summary.last_7_days_wins}/{summary.last_7_days_games} ({summary.last_7_days_win_pct:.1%})",
        f"  Last 30 days: {summary.last_30_days_wins}/{summary.last_30_days_games} ({summary.last_30_days_win_pct:.1%})",
        "=" * 50,
    ]
    return "\n".join(lines)


# Cache utilities
def get_cache_path(cache_type: str, date_str: str, extension: str = "json") -> Path:
    """Get cache file path for a specific type and date."""
    return CACHE_DIR / f"{cache_type}_{date_str}.{extension}"


def load_cache(cache_type: str, date_str: str) -> Optional[Dict]:
    """Load cached data if it exists."""
    path = get_cache_path(cache_type, date_str)
    
    if not path.exists():
        return None
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  Warning: Failed to load cache {path}: {e}")
        return None


def save_cache(cache_type: str, date_str: str, data: Dict) -> Path:
    """Save data to cache."""
    path = get_cache_path(cache_type, date_str)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)
    
    return path


def clear_cache(before_date: Optional[str] = None) -> int:
    """
    Clear cache files, optionally only those before a date.
    
    Args:
        before_date: If provided, only clear caches for dates before this
        
    Returns:
        Number of files deleted
    """
    deleted = 0
    
    for f in CACHE_DIR.glob("*.json"):
        if before_date:
            # Extract date from filename (e.g., team_stats_asof_20240101.json)
            parts = f.stem.split("_")
            if len(parts) >= 3:
                try:
                    file_date = parts[-1]
                    if file_date >= before_date.replace("-", ""):
                        continue
                except:
                    pass
        
        f.unlink()
        deleted += 1
    
    return deleted
