#!/usr/bin/env python3
"""
NBA Prediction Engine - Daily Runner (v2)

Fetches today's NBA slate, downloads latest injury report, generates predictions
using the 20-factor weighted point system, and saves all outputs to CSV files.

Usage:
    python run_today.py
"""

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

from ingest.schedule import (
    get_todays_games,
    get_team_ratings,
    get_advanced_team_stats,
    get_team_rest_days,
    get_current_season,
)
from ingest.injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
    InjuryRow,
)
from model.point_system import score_game, GameScore, validate_system


# Output directory
OUTPUT_DIR = Path(__file__).parent / "outputs"


def get_timestamp() -> str:
    """Get current timestamp string for filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_predictions_csv(scores: list[GameScore], timestamp: str) -> Path:
    """
    Save predictions to CSV file.
    
    Args:
        scores: List of GameScore objects.
        timestamp: Timestamp string for filename.
    
    Returns:
        Path to saved CSV file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output_path = OUTPUT_DIR / f"predictions_{timestamp}.csv"
    
    # Convert to DataFrame
    data = []
    for score in scores:
        data.append({
            "away_team": score.away_team,
            "home_team": score.home_team,
            "predicted_winner": score.predicted_winner,
            "edge_score": score.edge_score_total,
            "home_win_prob": score.home_win_prob,
            "away_win_prob": score.away_win_prob,
            "projected_margin_home": score.projected_margin_home,
            "top_5_factors": score.top_5_factors_str,
        })
    
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    
    return output_path


def save_factors_csv(scores: list[GameScore], timestamp: str) -> Path:
    """
    Save factor breakdown to CSV file.
    
    Args:
        scores: List of GameScore objects.
        timestamp: Timestamp string for filename.
    
    Returns:
        Path to saved CSV file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output_path = OUTPUT_DIR / f"factors_{timestamp}.csv"
    
    # Convert to DataFrame
    data = []
    for score in scores:
        matchup = f"{score.away_team}@{score.home_team}"
        for factor in score.factors:
            data.append({
                "matchup": matchup,
                "factor_name": factor.display_name,
                "weight": factor.weight,
                "signed_value": round(factor.signed_value, 3),
                "contribution": round(factor.contribution, 2),
                "inputs_used": factor.inputs_used,
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
    print("=" * 70)
    print("NBA Prediction Engine v2 - Daily Run (20-Factor Point System)")
    print("=" * 70)
    print()
    
    # Validate point system
    errors = validate_system()
    if errors:
        print("ERROR: Point system validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    
    timestamp = get_timestamp()
    
    # Step 1: Fetch today's slate
    print("[1/6] Pulling today's slate...")
    games = get_todays_games()
    
    if not games:
        print("  No games found for today.")
        print("  This may be normal (no games scheduled) or an API issue.")
        print()
        print("=" * 70)
        print("Run complete - no games to predict.")
        print("=" * 70)
        return 0
    
    print(f"  Found {len(games)} game(s) today:")
    for game in games:
        print(f"    {game.away_team} @ {game.home_team}")
    print()
    
    # Step 2: Load advanced team stats
    print("[2/6] Loading team statistics...")
    season = get_current_season()
    print(f"  Season: {season}")
    
    team_stats = get_advanced_team_stats(season=season)
    
    if not team_stats:
        print("  Warning: Could not load team stats. Using defaults.")
    print()
    
    # Step 3: Get rest days for teams playing today
    print("[3/6] Calculating rest days...")
    teams_playing = list(set(
        [g.away_team for g in games] + [g.home_team for g in games]
    ))
    
    try:
        rest_days = get_team_rest_days(teams_playing, season=season)
        print(f"  Calculated rest days for {len(rest_days)} teams.")
    except Exception as e:
        print(f"  Could not calculate rest days: {e}")
        rest_days = {t: 1 for t in teams_playing}
    print()
    
    # Step 4: Find and download injury report
    print("[4/6] Finding latest injury report PDF...")
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
    
    # Step 5: Parse injuries
    print("[5/6] Parsing injuries...")
    
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
    
    # Step 6: Generate predictions using point system
    print("[6/6] Generating predictions (20-factor point system)...")
    
    scores = []
    for game in games:
        home_rest = rest_days.get(game.home_team, 1)
        away_rest = rest_days.get(game.away_team, 1)
        
        score = score_game(
            home_team=game.home_team,
            away_team=game.away_team,
            team_stats=team_stats,
            injuries=injuries,
            player_stats={},  # TODO: Add player stats in future version
            home_rest_days=home_rest,
            away_rest_days=away_rest,
        )
        scores.append(score)
    
    # Sort by absolute edge score (most confident first)
    scores.sort(key=lambda s: abs(s.edge_score_total), reverse=True)
    
    print(f"  Generated {len(scores)} predictions.")
    print()
    
    # Display predictions
    print("=" * 70)
    print("PREDICTIONS (sorted by confidence)")
    print("=" * 70)
    print(f"{'Matchup':<18} {'Pick':<6} {'Edge':>8} {'Home%':>8} {'Away%':>8} {'Margin':>8}")
    print("-" * 70)
    
    for score in scores:
        matchup = f"{score.away_team} @ {score.home_team}"
        print(f"{matchup:<18} {score.predicted_winner:<6} {score.edge_score_total:>+8.1f} "
              f"{score.home_win_prob:>7.1%} {score.away_win_prob:>7.1%} {score.projected_margin_home:>+8.1f}")
    
    print("-" * 70)
    print()
    
    # Show top factors for each game
    print("TOP FACTORS BY GAME:")
    print("-" * 70)
    for score in scores:
        matchup = f"{score.away_team} @ {score.home_team}"
        print(f"{matchup}: {score.top_5_factors_str}")
    print("-" * 70)
    print()
    
    # Save outputs
    print("Saving outputs...")
    
    # Save predictions
    pred_path = save_predictions_csv(scores, timestamp)
    print(f"  Predictions: {pred_path}")
    
    # Save factors
    factors_path = save_factors_csv(scores, timestamp)
    print(f"  Factors: {factors_path}")
    
    # Save injuries if any
    if injuries:
        inj_path = save_injuries_csv(injuries, timestamp)
        print(f"  Injuries: {inj_path}")
    
    print()
    print("=" * 70)
    print("Run complete!")
    print("=" * 70)
    
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
