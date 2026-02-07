#!/usr/bin/env python3
"""
NBA Prediction Engine v3 - Daily Runner

Lineup-aware, matchup-sensitive NBA pregame predictions with:
- Player availability impact
- Home/road performance splits
- 21-factor weighted scoring system
- Calibrated win probabilities
- Excel tracking with overwrite-by-day

Usage:
    python run_today.py              # Run for today's slate
    python run_today.py --refresh    # Refresh winrate stats only

NOTE: This engine ONLY supports today's slate. No historical/backfill modes.
"""

import argparse
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

from ingest.schedule import get_todays_games, get_current_season
from ingest.team_stats import (
    get_comprehensive_team_stats,
    get_team_rest_days,
    get_fallback_team_strength,
)
from ingest.player_stats import get_player_stats, get_fallback_player_stats, ensure_team_players
from ingest.injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
    InjuryRow,
)
from ingest.inactives import fetch_all_game_inactives, merge_inactives_with_injuries
from ingest.known_absences import load_known_absences, merge_known_absences_with_injuries
from ingest.news_absences import fetch_all_news_absences, merge_news_absences_with_injuries
from ingest.availability import AvailabilityConfidence, normalize_player_name
from model.lineup_adjustment import (
    calculate_lineup_adjusted_strength,
    calculate_game_confidence,
    get_availability_debug_rows,
)
from model.point_system import score_game_v3, validate_system, GameScore
from tracking import ExcelTracker, PickEntry, WinrateStats


# Output directory
OUTPUT_DIR = Path(__file__).parent / "outputs"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="NBA Prediction Engine v3 - Daily Runner (Today Only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_today.py              # Run for today's slate
  python run_today.py --refresh    # Refresh winrate stats only
        """
    )
    
    parser.add_argument(
        "--refresh", "-r",
        action="store_true",
        help="Refresh winrate statistics only (don't run predictions)"
    )
    
    return parser.parse_args()


def get_data_confidence(
    team_stats_available: bool,
    player_stats_available: bool,
    injury_report_available: bool,
) -> str:
    """Determine data confidence level."""
    if team_stats_available and player_stats_available and injury_report_available:
        return "HIGH"
    elif team_stats_available and injury_report_available:
        return "MEDIUM"
    else:
        return "LOW"


def create_pick_entries(scores: list, run_date: str, run_timestamp: str, 
                        data_confidence: str) -> list:
    """
    Convert GameScore objects to PickEntry objects for Excel tracking.
    
    Args:
        scores: List of GameScore objects
        run_date: Date string (YYYY-MM-DD)
        run_timestamp: Timestamp string (YYYY-MM-DD HH:MM:SS)
        data_confidence: Data quality level
        
    Returns:
        List of PickEntry objects
    """
    entries = []
    
    for score in scores:
        # Determine pick side
        pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
        
        entry = PickEntry(
            run_date=run_date,
            run_timestamp=run_timestamp,
            game_id=getattr(score, 'game_id', ''),
            away_team=score.away_team,
            home_team=score.home_team,
            pick_team=score.predicted_winner,
            pick_side=pick_side,
            confidence_level=score.confidence_label.upper(),
            edge_score_total=round(score.edge_score_total, 2),
            projected_margin_home=round(score.projected_margin_home, 1),
            home_win_prob=round(score.home_win_prob, 3),
            away_win_prob=round(score.away_win_prob, 3),
            top_5_factors=score.top_5_factors_str,
            data_confidence=data_confidence,
        )
        entries.append(entry)
    
    return entries


def main() -> int:
    """Main entry point for daily prediction run."""
    args = parse_args()
    
    # Initialize Excel tracker
    tracker = ExcelTracker()
    
    # Handle refresh-only mode
    if args.refresh:
        print("Refreshing winrate statistics...")
        stats = tracker.refresh_winrates()
        print(f"\nOverall: {stats.wins}/{stats.total_graded} ({stats.win_pct:.1f}%)")
        print(f"HIGH:    {stats.high_wins}/{stats.high_graded} ({stats.high_win_pct:.1f}%)")
        print(f"MEDIUM:  {stats.medium_wins}/{stats.medium_graded} ({stats.medium_win_pct:.1f}%)")
        print(f"LOW:     {stats.low_wins}/{stats.low_graded} ({stats.low_win_pct:.1f}%)")
        print(f"Pending: {stats.pending_total}")
        return 0
    
    # Get current timestamp
    now = datetime.now()
    run_date = now.strftime("%Y-%m-%d")
    run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
    print("=" * 70)
    print("NBA PREDICTION ENGINE v3 - DAILY RUN")
    print(f"Date: {run_date}")
    print(f"Time: {run_timestamp}")
    print("=" * 70)
    print()
    
    # Validate scoring system
    try:
        validate_system()
        print("[OK] Scoring system validated (weights sum to 100)")
    except AssertionError as e:
        print(f"[ERROR] Scoring system validation failed: {e}")
        return 1
    print()
    
    # Step 1: Get today's games
    print("[1/7] Fetching today's games...")
    games = get_todays_games()
    
    if not games:
        print("  No games scheduled for today.")
        print("\nNo predictions to generate.")
        return 0
    
    print(f"  Found {len(games)} games:")
    for game in games:
        print(f"    {game.away_team} @ {game.home_team} ({game.start_time_et})")
    print()
    
    # Step 2: Get team statistics
    print("[2/7] Fetching team statistics...")
    season = get_current_season()
    team_strength = get_comprehensive_team_stats(season)
    
    team_stats_available = len(team_strength) > 0
    
    if not team_strength:
        print("  Warning: Could not load team stats, using fallback values")
        # Create fallback for all teams in today's games
        for game in games:
            for team in [game.home_team, game.away_team]:
                if team not in team_strength:
                    team_strength[team] = get_fallback_team_strength(team)
    else:
        print(f"  Loaded stats for {len(team_strength)} teams")
    print()
    
    # Step 3: Get player statistics
    print("[3/7] Fetching player statistics...")
    player_stats = get_player_stats(season)
    
    player_stats_available = len(player_stats) > 0
    
    if not player_stats:
        print("  Warning: Could not load player stats, using fallback")
        player_stats = get_fallback_player_stats(
            [g.home_team for g in games] + [g.away_team for g in games]
        )
    else:
        total_players = sum(len(p) for p in player_stats.values())
        print(f"  Loaded stats for {total_players} players across {len(player_stats)} teams")

    # Ensure every team playing today has player data (fallback if missing)
    teams_today = list(set([g.home_team for g in games] + [g.away_team for g in games]))
    player_stats = ensure_team_players(player_stats, teams_today)
    print()
    
    # Step 4: Get rest days
    print("[4/7] Calculating rest days...")
    rest_days = get_team_rest_days(season)
    print(f"  Calculated rest days for {len(rest_days)} teams")
    print()
    
    # Step 5: Get injury report
    print("[5/7] Fetching injury report...")
    injury_url = find_latest_injury_pdf()
    injuries = []
    injury_report_available = False
    
    if injury_url:
        print(f"  Found: {injury_url}")
        pdf_bytes = download_injury_pdf(injury_url)
        if pdf_bytes:
            injuries = parse_injury_pdf(pdf_bytes)
            injury_report_available = True
            print(f"  Parsed {len(injuries)} injury entries")
        else:
            print("  Warning: Could not download injury report")
    else:
        print("  No recent injury report found")
    print()
    
    # Step 5a: Load manual absences
    print("[5a/7] Loading manual absences...")
    known_absences = load_known_absences()
    if known_absences:
        injuries = merge_known_absences_with_injuries(injuries, known_absences)
        print(f"  Merged {len(known_absences)} manual absence entries")
    else:
        print("  No manual absences configured")
    print()
    
    # Step 5b: Fetch ESPN injury data
    print("[5b/7] Fetching ESPN injury data...")
    teams_playing = list(set([g.away_team for g in games] + [g.home_team for g in games]))
    news_absences = fetch_all_news_absences(teams_playing)
    
    if news_absences:
        injuries = merge_news_absences_with_injuries(injuries, news_absences)
        print(f"  Merged {len(news_absences)} ESPN injury entries")
    else:
        print("  No additional ESPN injury data")
    print()
    
    # Step 5c: Fetch inactives
    print("[5c/7] Fetching game inactives...")
    game_ids = [g.game_id for g in games if g.game_id]
    inactives = {}
    
    if game_ids:
        inactives = fetch_all_game_inactives(game_ids)
        if inactives:
            injuries = merge_inactives_with_injuries(injuries, inactives)
            print(f"  Merged inactives for {len(inactives)} teams")
        else:
            print("  No inactive data available yet")
    else:
        print("  No game IDs available")
    print()
    
    # Step 6: Generate predictions
    print("[6/7] Generating predictions...")
    scores = []
    
    for game in games:
        # Get team strengths
        home_ts = team_strength.get(game.home_team)
        away_ts = team_strength.get(game.away_team)
        
        if home_ts is None or away_ts is None:
            print(f"  Warning: Missing stats for {game.away_team} @ {game.home_team}")
            continue
        
        # Get player lists
        home_players = player_stats.get(game.home_team, [])
        away_players = player_stats.get(game.away_team, [])
        
        # Calculate lineup-adjusted strengths
        home_lineup = calculate_lineup_adjusted_strength(
            team=game.home_team,
            team_strength=home_ts,
            players=home_players,
            injuries=injuries,
            is_home=True,
            inactives=inactives,
            injury_report_available=injury_report_available,
        )
        
        away_lineup = calculate_lineup_adjusted_strength(
            team=game.away_team,
            team_strength=away_ts,
            players=away_players,
            injuries=injuries,
            is_home=False,
            inactives=inactives,
            injury_report_available=injury_report_available,
        )
        
        # Get rest days
        home_rest = rest_days.get(game.home_team, 1)
        away_rest = rest_days.get(game.away_team, 1)
        
        # Score the game
        home_stats = home_ts.to_dict() if hasattr(home_ts, 'to_dict') else home_ts
        away_stats = away_ts.to_dict() if hasattr(away_ts, 'to_dict') else away_ts
        
        # Filter injuries by team
        home_injuries = [inj for inj in injuries if getattr(inj, 'team', '').upper() == game.home_team.upper()]
        away_injuries = [inj for inj in injuries if getattr(inj, 'team', '').upper() == game.away_team.upper()]
        
        score = score_game_v3(
            home_team=game.home_team,
            away_team=game.away_team,
            home_strength=home_lineup,
            away_strength=away_lineup,
            home_stats=home_stats,
            away_stats=away_stats,
            home_rest_days=home_rest,
            away_rest_days=away_rest,
            home_players=home_players,
            away_players=away_players,
            home_injuries=home_injuries,
            away_injuries=away_injuries,
        )
        
        # Add game_id to score for tracking
        score.game_id = game.game_id
        scores.append(score)
    
    # Sort by confidence (strongest edge first)
    scores.sort(key=lambda s: (abs(s.edge_score_total), s.confidence), reverse=True)
    
    print(f"  Generated {len(scores)} predictions")
    print()
    
    # Determine data confidence
    data_confidence = get_data_confidence(
        team_stats_available=team_stats_available,
        player_stats_available=player_stats_available,
        injury_report_available=injury_report_available,
    )
    
    # Step 7: Save to Excel tracking
    print("[7/7] Saving to Excel tracking...")
    
    try:
        # Create pick entries
        entries = create_pick_entries(scores, run_date, run_timestamp, data_confidence)
        
        # Save to Excel (overwrite-by-day)
        saved_count = tracker.save_predictions(entries)
        print(f"  Saved {saved_count} predictions to {tracker.get_file_path()}")
        
        # Update summary sheet
        stats = tracker.refresh_winrates()
        print(f"  Updated summary statistics")
        
    except IOError as e:
        print(f"  ERROR: {e}")
        return 1
    
    print()
    
    # Display predictions
    print("=" * 90)
    print("TODAY'S PREDICTIONS (sorted by confidence)")
    print("=" * 90)
    print(f"{'Matchup':<18} {'Pick':<6} {'Conf':<8} {'Edge':>7} {'Home%':>7} {'Away%':>7} {'Margin':>7}")
    print("-" * 90)
    
    for score in scores:
        matchup = f"{score.away_team} @ {score.home_team}"
        print(f"{matchup:<18} {score.predicted_winner:<6} {score.confidence_label.upper():<8} "
              f"{score.edge_score_total:>+7.1f} {score.home_win_prob:>6.1%} "
              f"{score.away_win_prob:>6.1%} {score.projected_margin_home:>+7.1f}")
    
    print("-" * 90)
    print()
    
    # Show winrate summary
    print("WINRATE SUMMARY:")
    print(f"  Overall: {stats.wins}/{stats.total_graded} ({stats.win_pct:.1f}%)" if stats.total_graded > 0 else "  Overall: No graded picks yet")
    print(f"  HIGH:    {stats.high_wins}/{stats.high_graded} ({stats.high_win_pct:.1f}%)" if stats.high_graded > 0 else "  HIGH:    No graded picks")
    print(f"  MEDIUM:  {stats.medium_wins}/{stats.medium_graded} ({stats.medium_win_pct:.1f}%)" if stats.medium_graded > 0 else "  MEDIUM:  No graded picks")
    print(f"  LOW:     {stats.low_wins}/{stats.low_graded} ({stats.low_win_pct:.1f}%)" if stats.low_graded > 0 else "  LOW:     No graded picks")
    print(f"  Pending: {stats.pending_total}")
    print()
    
    print(f"Predictions saved to: {tracker.get_file_path()}")
    print("Open the Excel file to fill in actual_winner for graded picks.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
