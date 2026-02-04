"""
Results Update Job for NBA Prediction Engine.

Fetches final game results and updates predictions log with actual winners.
"""

from datetime import date
from typing import Dict, Optional, List

from utils.dates import parse_date, format_date, get_eastern_date
from utils.storage import (
    load_predictions_log,
    update_results_in_log,
    get_entries_needing_results,
    compute_performance_summary,
    save_performance_summary,
    format_performance_summary,
)
from model.asof import get_asof_game_results


def update_results_for_date(game_date: date) -> int:
    """
    Update actual winners for all predictions on a specific date.
    
    Fetches final results from NBA API and updates predictions_log.csv.
    
    Args:
        game_date: Date to update results for
        
    Returns:
        Number of predictions updated
    """
    date_str = format_date(game_date)
    print(f"Updating results for {date_str}...")
    
    # Fetch results
    results = get_asof_game_results(game_date)
    
    if not results:
        print(f"  No final results found for {date_str}")
        return 0
    
    print(f"  Found {len(results)} final games")
    
    # Update log
    updated = update_results_in_log(date_str, results)
    
    print(f"  Updated {updated} predictions")
    
    # Update performance summary
    summary = compute_performance_summary()
    save_performance_summary(summary)
    print(f"  Performance summary updated")
    
    return updated


def update_all_pending_results() -> int:
    """
    Update results for all predictions that don't have actual_winner filled.
    
    Returns:
        Total number of predictions updated
    """
    print("Updating all pending results...")
    
    # Get entries needing results
    pending = get_entries_needing_results()
    
    if not pending:
        print("  No pending predictions to update")
        return 0
    
    # Group by date
    dates_to_update = set()
    for entry in pending:
        if entry.game_date:
            dates_to_update.add(entry.game_date)
    
    print(f"  Found {len(pending)} predictions across {len(dates_to_update)} dates")
    
    # Don't try to update today's games (not finished yet)
    today = format_date(get_eastern_date())
    dates_to_update.discard(today)
    
    total_updated = 0
    for date_str in sorted(dates_to_update):
        try:
            game_date = parse_date(date_str)
            updated = update_results_for_date(game_date)
            total_updated += updated
        except Exception as e:
            print(f"  Error updating {date_str}: {e}")
    
    # Update performance summary
    if total_updated > 0:
        summary = compute_performance_summary()
        save_performance_summary(summary)
        print(format_performance_summary(summary))
    
    return total_updated


def get_pending_dates() -> List[str]:
    """
    Get list of dates that have predictions without results.
    
    Returns:
        List of date strings (YYYY-MM-DD)
    """
    pending = get_entries_needing_results()
    
    dates = set()
    today = format_date(get_eastern_date())
    
    for entry in pending:
        if entry.game_date and entry.game_date != today:
            dates.add(entry.game_date)
    
    return sorted(dates)


def show_performance_summary() -> None:
    """Print performance summary to console."""
    summary = compute_performance_summary()
    print(format_performance_summary(summary))
