#!/usr/bin/env python3
"""
NBA Prediction Engine - Daily Runner

Fetches today's NBA slate, downloads latest injury report, generates predictions,
and saves all outputs to CSV files.

Usage:
    python run_today.py
"""

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
from tqdm import tqdm

from ingest.schedule import get_todays_games, get_team_ratings, get_current_season
from ingest.injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
    InjuryRow,
)
from model.pregame import predict_games, GamePrediction


# Output directory
OUTPUT_DIR = Path(__file__).parent / "outputs"


def get_timestamp() -> str:
    """Get current timestamp string for filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_predictions_csv(predictions: list[GamePrediction], timestamp: str) -> Path:
    """
    Save predictions to CSV file.
    
    Args:
        predictions: List of GamePrediction objects.
        timestamp: Timestamp string for filename.
    
    Returns:
        Path to saved CSV file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output_path = OUTPUT_DIR / f"predictions_{timestamp}.csv"
    
    # Convert to DataFrame
    data = []
    for pred in predictions:
        data.append({
            "away_team": pred.away_team,
            "home_team": pred.home_team,
            "projected_margin_home": pred.projected_margin_home,
            "home_win_prob": pred.home_win_prob,
            "away_win_prob": pred.away_win_prob,
            "start_time_utc": pred.start_time_utc,
        })
    
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    
    return output_path


def save_injuries_csv(injuries: list[InjuryRow], timestamp: str) -> Path:
    """
    Save injuries to CSV file.
    
    Args:
        injuries: List of InjuryRow objects.
        timestamp: Timestamp string for filename.
    
    Returns:
        Path to saved CSV file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output_path = OUTPUT_DIR / f"injuries_{timestamp}.csv"
    
    # Convert to DataFrame
    data = []
    for injury in injuries:
        data.append({
            "team": injury.team,
            "player": injury.player,
            "status": injury.status,
            "reason": injury.reason,
        })
    
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    
    return output_path


def main() -> int:
    """
    Main entry point for daily prediction run.
    
    Returns:
        Exit code (0 for success, 1 for failure).
    """
    print("=" * 60)
    print("NBA Prediction Engine - Daily Run")
    print("=" * 60)
    print()
    
    timestamp = get_timestamp()
    
    # Step 1: Fetch today's slate
    print("[1/5] Pulling today's slate...")
    games = get_todays_games()
    
    if not games:
        print("  No games found for today.")
        print("  This may be normal (no games scheduled) or an API issue.")
        print()
        # Continue to still try to get injuries and ratings
    else:
        print(f"  Found {len(games)} game(s) today:")
        for game in games:
            print(f"    {game.away_team} @ {game.home_team}")
    print()
    
    # Step 2: Load team ratings
    print("[2/5] Loading team ratings...")
    season = get_current_season()
    print(f"  Season: {season}")
    
    ratings = get_team_ratings(season=season)
    
    if not ratings:
        print("  Warning: Could not load team ratings. Using defaults.")
    else:
        print(f"  Loaded ratings for {len(ratings)} teams.")
    print()
    
    # Step 3: Find and download injury report
    print("[3/5] Finding latest injury report PDF...")
    cache_file = OUTPUT_DIR / "latest_injury_url.txt"
    
    injury_url = find_latest_injury_pdf(cache_file=cache_file)
    pdf_bytes = None
    injuries = []
    
    if injury_url:
        print(f"  Found: {injury_url}")
        
        # Download PDF
        pdf_path = OUTPUT_DIR / f"injury_report_{timestamp}.pdf"
        pdf_bytes = download_injury_pdf(injury_url, output_path=pdf_path)
        
        if pdf_bytes:
            print(f"  Downloaded: {pdf_path.name}")
        else:
            print("  Warning: Failed to download PDF.")
    else:
        print("  No injury report found (searched 36 hours back).")
    print()
    
    # Step 4: Parse injuries
    print("[4/5] Parsing injuries...")
    
    if pdf_bytes:
        injuries = parse_injury_pdf(pdf_bytes)
        
        if injuries:
            print(f"  Parsed {len(injuries)} injury entries.")
            
            # Show summary by status
            status_counts = {}
            for injury in injuries:
                status_counts[injury.status] = status_counts.get(injury.status, 0) + 1
            
            for status, count in sorted(status_counts.items()):
                print(f"    {status}: {count}")
        else:
            print("  No injuries parsed (PDF may be empty or parsing failed).")
    else:
        print("  Skipping (no PDF available).")
    print()
    
    # Step 5: Generate predictions
    print("[5/5] Generating predictions...")
    
    if not games:
        print("  Skipping (no games today).")
        print()
        print("=" * 60)
        print("Run complete - no games to predict.")
        print("=" * 60)
        return 0
    
    predictions = predict_games(games, ratings)
    print(f"  Generated {len(predictions)} predictions.")
    print()
    
    # Display predictions
    print("Predictions (sorted by home win probability):")
    print("-" * 60)
    print(f"{'Matchup':<20} {'Margin':>10} {'Home Win':>10} {'Away Win':>10}")
    print("-" * 60)
    
    for pred in predictions:
        matchup = f"{pred.away_team} @ {pred.home_team}"
        print(f"{matchup:<20} {pred.projected_margin_home:>+10.1f} {pred.home_win_prob:>10.1%} {pred.away_win_prob:>10.1%}")
    
    print("-" * 60)
    print()
    
    # Save outputs
    print("Saving outputs...")
    
    # Save predictions
    pred_path = save_predictions_csv(predictions, timestamp)
    print(f"  Predictions: {pred_path}")
    
    # Save injuries if any
    if injuries:
        inj_path = save_injuries_csv(injuries, timestamp)
        print(f"  Injuries: {inj_path}")
    
    print()
    print("=" * 60)
    print("Run complete!")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
