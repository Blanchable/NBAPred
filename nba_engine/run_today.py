#!/usr/bin/env python3
"""
NBA Prediction Engine v3 - Daily Runner

Lineup-aware, matchup-sensitive NBA pregame predictions with:
- Player availability impact
- Home/road performance splits
- 20-factor weighted scoring system
- Calibrated win probabilities
- Prediction logging for backtesting
- Historical "as-of" mode for backtesting

Usage:
    python run_today.py                  # Run for today
    python run_today.py --date 2024-01-15    # Run for historical date
    python run_today.py --date 2024-01-15 --fill-results  # Fill results too
    python run_today.py --update-results     # Update pending results
    python run_today.py --show-performance   # Show performance summary
    python run_today.py --backfill 2024-01-01 2024-01-15  # Backfill range
"""

import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
import sys

import pandas as pd

from ingest.schedule import get_todays_games, get_current_season
from ingest.team_stats import (
    get_comprehensive_team_stats,
    get_team_rest_days,
    get_fallback_team_strength,
)
from ingest.player_stats import get_player_stats, get_fallback_player_stats
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
from model.calibration import PredictionLogger, PredictionRecord
from model.asof import get_data_confidence

# Import new utilities
from utils.dates import (
    parse_date,
    format_date,
    get_eastern_date,
    enforce_date_limit,
    is_today,
)
from utils.storage import (
    PredictionLogEntry,
    append_predictions,
    export_daily_predictions,
    compute_performance_summary,
    save_performance_summary,
    format_performance_summary,
    OUTPUTS_DIR,
)


# Output directory
OUTPUT_DIR = Path(__file__).parent / "outputs"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="NBA Prediction Engine v3 - Daily Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_today.py                        # Run for today
  python run_today.py --date 2024-01-15      # Historical date
  python run_today.py --fill-results         # Fill results for pending
  python run_today.py --update-results       # Update all pending results
  python run_today.py --show-performance     # Show win % summary
  python run_today.py --backfill START END   # Backfill date range
        """
    )
    
    parser.add_argument(
        "--date", "-d",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD). Default: today"
    )
    
    parser.add_argument(
        "--fill-results", "-f",
        action="store_true",
        help="Fill actual results after generating predictions"
    )
    
    parser.add_argument(
        "--update-results", "-u",
        action="store_true",
        help="Update results for all pending predictions and exit"
    )
    
    parser.add_argument(
        "--show-performance", "-p",
        action="store_true",
        help="Show performance summary and exit"
    )
    
    parser.add_argument(
        "--backfill", "-b",
        nargs=2,
        metavar=("START", "END"),
        help="Backfill predictions for date range (YYYY-MM-DD)"
    )
    
    return parser.parse_args()


def get_timestamp() -> str:
    """Get current timestamp string for filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_predictions_csv(scores: list[GameScore], timestamp: str) -> Path:
    """Save predictions to CSV file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"predictions_{timestamp}.csv"
    
    data = []
    for score in scores:
        data.append({
            "away_team": score.away_team,
            "home_team": score.home_team,
            "predicted_winner": score.predicted_winner,
            "confidence": score.confidence,
            "edge_score": score.edge_score_total,
            "home_win_prob": score.home_win_prob,
            "away_win_prob": score.away_win_prob,
            "projected_margin_home": score.projected_margin_home,
            "home_power": score.home_power_rating,
            "away_power": score.away_power_rating,
            "top_5_factors": score.top_5_factors_str,
        })
    
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    return output_path


def save_factors_csv(scores: list[GameScore], timestamp: str) -> Path:
    """Save factor breakdown to CSV file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"factors_{timestamp}.csv"
    
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
    """Save injuries to CSV file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"injuries_{timestamp}.csv"
    
    data = []
    for i in injuries:
        row = i.to_dict() if hasattr(i, 'to_dict') else {
            "team": i.team, "player": i.player, "status": i.status, "reason": i.reason
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    return output_path


def save_availability_debug_csv(debug_rows: list[dict], timestamp: str) -> Path:
    """Save availability debug info to CSV file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"availability_debug_{timestamp}.csv"
    
    df = pd.DataFrame(debug_rows)
    df.to_csv(output_path, index=False)
    return output_path


def handle_update_results() -> int:
    """Handle --update-results mode."""
    print("=" * 70)
    print("NBA Prediction Engine v3 - Update Results")
    print("=" * 70)
    print()
    
    from jobs.results import update_all_pending_results, show_performance_summary
    
    updated = update_all_pending_results()
    
    if updated > 0:
        print()
        show_performance_summary()
    
    return 0


def handle_show_performance() -> int:
    """Handle --show-performance mode."""
    summary = compute_performance_summary()
    print(format_performance_summary(summary))
    save_performance_summary(summary)
    return 0


def handle_backfill(start_str: str, end_str: str) -> int:
    """Handle --backfill mode."""
    try:
        start_date = parse_date(start_str)
        end_date = parse_date(end_str)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    
    from jobs.backfill import backfill_date_range
    
    try:
        backfill_date_range(start_date, end_date, fill_results=True)
        return 0
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1


def run_historical_predictions(target_date: date, fill_results: bool) -> int:
    """Run predictions for a historical date using as-of data."""
    from jobs.backfill import backfill_predictions
    
    try:
        predictions = backfill_predictions(
            target_date=target_date,
            fill_results=fill_results,
            use_cache=True,
        )
        
        if predictions:
            # Export daily predictions file
            date_str = format_date(target_date)
            export_daily_predictions(predictions, date_str)
            print(f"\nExported predictions to outputs/predictions_{date_str.replace('-', '')}.csv")
        
        return 0
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1


def create_prediction_log_entries(
    scores: list[GameScore],
    games: list,
    injury_url: str,
    data_confidence: str,
) -> list[PredictionLogEntry]:
    """Create prediction log entries from scores."""
    entries = []
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    game_date = format_date(get_eastern_date())
    
    # Build game lookup
    game_lookup = {(g.home_team, g.away_team): g for g in games}
    
    for score in scores:
        game = game_lookup.get((score.home_team, score.away_team))
        game_id = game.game_id if game else ""
        
        entry = PredictionLogEntry(
            run_timestamp_local=run_timestamp,
            game_date=game_date,
            game_id=game_id,
            away_team=score.away_team,
            home_team=score.home_team,
            pick=score.predicted_winner,
            edge_score_total=round(score.edge_score_total, 2),
            projected_margin_home=round(score.projected_margin_home, 1),
            home_win_prob=round(score.home_win_prob, 3),
            away_win_prob=round(score.away_win_prob, 3),
            confidence_level=score.confidence_label.upper(),
            confidence_pct=score.confidence_pct,
            top_5_factors=score.top_5_factors_str,
            injury_report_url=injury_url or "",
            data_confidence=data_confidence,
        )
        entries.append(entry)
    
    return entries


def main() -> int:
    """Main entry point for daily prediction run."""
    args = parse_args()
    
    # Handle special modes first
    if args.update_results:
        return handle_update_results()
    
    if args.show_performance:
        return handle_show_performance()
    
    if args.backfill:
        return handle_backfill(args.backfill[0], args.backfill[1])
    
    # Determine target date
    if args.date:
        try:
            target_date = parse_date(args.date)
            enforce_date_limit(target_date)
            is_historical = not is_today(target_date)
        except ValueError as e:
            print(f"ERROR: {e}")
            return 1
    else:
        target_date = get_eastern_date()
        is_historical = False
    
    date_str = format_date(target_date)
    
    print("=" * 70)
    print("NBA Prediction Engine v3 - Lineup-Aware Predictions")
    if is_historical:
        print(f"  HISTORICAL MODE: {date_str}")
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
    season = get_current_season()
    
    # Initialize prediction logger
    logger = PredictionLogger(OUTPUT_DIR)
    
    # For historical mode, use as-of data
    if is_historical:
        return run_historical_predictions(target_date, args.fill_results)
    
    # Step 1: Fetch today's slate
    print("[1/7] Pulling today's slate...")
    games, api_date, is_current_date = get_todays_games()
    
    if not games:
        print("  No games found.")
        if not is_current_date:
            print("  ⚠ The API may not have updated to today's games yet.")
            print("    Try again after 10 AM Eastern Time.")
        print("=" * 70)
        print("Run complete - no games to predict.")
        print("=" * 70)
        return 0
    
    print(f"  Found {len(games)} game(s) for {api_date}:")
    for game in games:
        print(f"    {game.away_team} @ {game.home_team}")
    
    if not is_current_date:
        print()
        print("  " + "=" * 50)
        print("  ⚠ WARNING: These may be YESTERDAY'S games!")
        print(f"    API Date: {api_date}")
        print("    The NBA API typically updates around 6-10 AM ET.")
        print("  " + "=" * 50)
    print()
    
    # Step 2: Load comprehensive team stats
    print("[2/7] Loading team statistics (with home/road splits)...")
    try:
        team_strength = get_comprehensive_team_stats(season=season)
        if not team_strength:
            print("  API returned empty, using fallback data...")
            team_strength = get_fallback_team_strength()
    except Exception as e:
        print(f"  Error: {e}")
        print("  Using fallback team data...")
        team_strength = get_fallback_team_strength()
    
    print(f"  Loaded stats for {len(team_strength)} teams.")
    print()
    
    # Step 3: Load player stats
    print("[3/7] Loading player statistics...")
    try:
        player_stats = get_player_stats(season=season)
        if not player_stats:
            print("  API returned empty, using fallback data...")
            player_stats = get_fallback_player_stats()
    except Exception as e:
        print(f"  Error: {e}")
        print("  Using fallback player data...")
        player_stats = get_fallback_player_stats()
    
    if player_stats:
        print(f"  Loaded players for {len(player_stats)} teams.")
    print()
    
    # Step 4: Get rest days
    print("[4/7] Calculating rest days...")
    teams_playing = list(set([g.away_team for g in games] + [g.home_team for g in games]))
    
    try:
        rest_days = get_team_rest_days(teams_playing, season=season)
        for team in sorted(teams_playing):
            days = rest_days.get(team, 1)
            status = "B2B" if days == 0 else f"{days}d rest"
            print(f"    {team}: {status}")
    except Exception as e:
        print(f"  Error: {e}")
        rest_days = {t: 1 for t in teams_playing}
    print()
    
    # Step 5: Fetch injury report
    print("[5/7] Fetching injury report...")
    cache_file = OUTPUT_DIR / "latest_injury_url.txt"
    injury_url = find_latest_injury_pdf(cache_file=cache_file)
    injuries = []
    injury_report_available = False
    
    if injury_url:
        print(f"  Found: {injury_url}")
        pdf_path = OUTPUT_DIR / f"injury_report_{timestamp}.pdf"
        pdf_bytes = download_injury_pdf(injury_url, output_path=pdf_path)
        
        if pdf_bytes:
            injuries = parse_injury_pdf(pdf_bytes)
            injury_report_available = len(injuries) > 0
            print(f"  Parsed {len(injuries)} injury entries.")
            
            # Show key injuries with canonical status
            key_statuses = ["Out", "Doubtful"]
            key_injuries = [i for i in injuries if i.status in key_statuses]
            if key_injuries:
                print("  Key injuries (Out/Doubtful):")
                for inj in key_injuries[:10]:
                    canonical = inj.get_canonical_status().value
                    print(f"    {inj.team}: {inj.player} ({inj.status} -> {canonical}) - {inj.reason[:30]}")
    else:
        print("  No injury report found.")
        print("  ⚠ Availability confidence will be LOW without injury data.")
    print()
    
    # Step 5b: Load known absences (manual overrides)
    print("[5b/8] Loading known absences (manual overrides)...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    known_absences = load_known_absences(check_date=today_str)
    
    if known_absences:
        print(f"  Found {len(known_absences)} known absence(s):")
        for absence in known_absences:
            print(f"    {absence.team}: {absence.player} ({absence.reason})")
        
        injuries = merge_known_absences_with_injuries(injuries, known_absences)
    else:
        print("  No manual absences configured.")
        print("  Tip: Add to data/known_absences.csv for players out for personal reasons, etc.")
    print()
    
    # Step 5c: Fetch ESPN injury data (supplemental)
    print("[5c/8] Fetching ESPN injury data (supplemental)...")
    teams_playing = list(set([g.away_team for g in games] + [g.home_team for g in games]))
    news_absences = fetch_all_news_absences(teams_playing)
    
    if news_absences:
        injuries = merge_news_absences_with_injuries(injuries, news_absences)
    print()
    
    # Step 5d: Fetch inactives from game feeds
    print("[5d/8] Fetching game inactives (pregame rosters)...")
    game_ids = [g.game_id for g in games if g.game_id]
    inactives = {}
    
    if game_ids:
        inactives = fetch_all_game_inactives(game_ids)
        
        # Merge inactives with injuries (inactives take priority)
        if inactives:
            injuries = merge_inactives_with_injuries(injuries, inactives)
            print(f"  Merged inactives with injury report.")
    else:
        print("  No game IDs available for inactive fetch.")
    print()
    
    # Step 6: Generate lineup-adjusted predictions
    print("[6/8] Generating lineup-adjusted predictions...")
    scores = []
    prediction_records = []
    all_availability_debug = []
    
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
        
        # Calculate lineup-adjusted strengths with star safeguards
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
        
        # Collect availability debug info
        debug_rows = get_availability_debug_rows(home_lineup, away_lineup)
        all_availability_debug.extend(debug_rows)
        
        # Get rest days
        home_rest = rest_days.get(game.home_team, 1)
        away_rest = rest_days.get(game.away_team, 1)
        
        # Score the game
        home_stats = home_ts.to_dict() if hasattr(home_ts, 'to_dict') else home_ts
        away_stats = away_ts.to_dict() if hasattr(away_ts, 'to_dict') else away_ts
        
        # Filter injuries by team for star impact calculation
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
        scores.append(score)
        
        # Create prediction record for logging
        record = PredictionRecord(
            date=datetime.now().strftime("%Y-%m-%d"),
            game_id=game.game_id,
            home_team=game.home_team,
            away_team=game.away_team,
            edge_score=score.edge_score_total,
            home_win_prob=score.home_win_prob,
            away_win_prob=score.away_win_prob,
            predicted_winner=score.predicted_winner,
            confidence=score.confidence,
            projected_margin=score.projected_margin_home,
        )
        prediction_records.append(record)
    
    # Sort by abs(edge_score_total) (strongest edge first), then by confidence (pick probability)
    scores.sort(key=lambda s: (abs(s.edge_score_total), s.confidence), reverse=True)
    
    print(f"  Generated {len(scores)} predictions.")
    print()
    
    # Display predictions
    print("=" * 90)
    print("PREDICTIONS (sorted by confidence)")
    print("=" * 90)
    print(f"{'Matchup':<18} {'Pick':<6} {'Conf':<6} {'Edge':>7} {'Home%':>7} {'Away%':>7} {'Margin':>7} {'Avail':>10}")
    print("-" * 90)
    
    for score in scores:
        matchup = f"{score.away_team} @ {score.home_team}"
        # Find availability info from debug data
        home_avail = "100%"
        away_avail = "100%"
        for debug in all_availability_debug:
            if debug.get('team') == score.home_team and debug.get('impact_rank') == 1:
                pass  # Will use lineup data
            if debug.get('team') == score.away_team and debug.get('impact_rank') == 1:
                pass
        
        print(f"{matchup:<18} {score.predicted_winner:<6} {score.confidence:>5.0%} "
              f"{score.edge_score_total:>+7.1f} {score.home_win_prob:>6.1%} "
              f"{score.away_win_prob:>6.1%} {score.projected_margin_home:>+7.1f}")
    
    print("-" * 90)
    print()
    
    # Show star player alerts for unconfirmed stars
    unconfirmed_stars = []
    for debug in all_availability_debug:
        if debug.get('is_star') and not debug.get('matched') and debug.get('source') == 'unknown':
            unconfirmed_stars.append((debug.get('team'), debug.get('player')))
    
    if unconfirmed_stars:
        print("=" * 90)
        print("⚠ STAR PLAYER ALERTS (not found in any data source)")
        print("=" * 90)
        for team, player in unconfirmed_stars:
            print(f"  {team}: {player} - STATUS UNKNOWN")
            print(f"       → Verify status via news/social media")
            print(f"       → Add to data/known_absences.csv if confirmed out")
        print("=" * 90)
        print()
    
    # Show top factors
    print("TOP FACTORS BY GAME:")
    print("-" * 90)
    for score in scores:
        matchup = f"{score.away_team} @ {score.home_team}"
        print(f"{matchup}: {score.top_5_factors_str}")
    print("-" * 90)
    print()
    
    # Step 7: Save outputs
    print("[7/8] Saving outputs...")
    
    pred_path = save_predictions_csv(scores, timestamp)
    print(f"  Predictions: {pred_path}")
    
    factors_path = save_factors_csv(scores, timestamp)
    print(f"  Factors: {factors_path}")
    
    if injuries:
        inj_path = save_injuries_csv(injuries, timestamp)
        print(f"  Injuries: {inj_path}")
    
    if all_availability_debug:
        avail_path = save_availability_debug_csv(all_availability_debug, timestamp)
        print(f"  Availability Debug: {avail_path}")
    
    # Log predictions for calibration (old logger)
    logger.log_predictions(prediction_records)
    print(f"  Logged {len(prediction_records)} predictions for calibration.")
    
    # Log to new prediction log system
    data_confidence = get_data_confidence(
        team_stats_available=len(team_strength) > 0,
        player_stats_available=len(player_stats) > 0,
        injury_report_available=injury_report_available,
    )
    
    log_entries = create_prediction_log_entries(
        scores=scores,
        games=games,
        injury_url=injury_url or "",
        data_confidence=data_confidence,
    )
    
    if log_entries:
        append_predictions(log_entries)
        print(f"  Saved {len(log_entries)} entries to predictions_log.csv")
        
        # Export daily predictions file
        date_str = format_date(get_eastern_date())
        daily_path = export_daily_predictions(log_entries, date_str)
        print(f"  Daily export: {daily_path}")
    
    print()
    
    # Show performance summary if we have results
    summary = compute_performance_summary()
    if summary.total_games > 0:
        print("=" * 70)
        print("PERFORMANCE SUMMARY")
        print("=" * 70)
        print(f"  Overall: {summary.wins}/{summary.total_games} ({summary.win_pct:.1%})")
        print(f"  Last 7 days: {summary.last_7_days_wins}/{summary.last_7_days_games} ({summary.last_7_days_win_pct:.1%})")
        print(f"  Last 30 days: {summary.last_30_days_wins}/{summary.last_30_days_games} ({summary.last_30_days_win_pct:.1%})")
        save_performance_summary(summary)
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
