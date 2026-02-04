"""
Backfill Job for NBA Prediction Engine.

Generates historical predictions for past dates using as-of data.
"""

import time
from datetime import date, timedelta
from typing import List, Optional
from pathlib import Path

from utils.dates import (
    parse_date,
    format_date,
    get_eastern_date,
    enforce_date_limit,
    validate_date_range,
    get_date_range,
    DEFAULT_MAX_DAYS_PER_RUN,
)
from utils.storage import (
    PredictionLogEntry,
    append_predictions,
    get_entries_for_date,
)
from model.asof import (
    get_asof_team_stats,
    get_asof_player_stats,
    get_asof_schedule,
    get_asof_game_results,
    get_data_confidence,
)


def backfill_predictions(
    target_date: date,
    fill_results: bool = False,
    use_cache: bool = True,
) -> List[PredictionLogEntry]:
    """
    Generate predictions for a historical date using as-of data.
    
    Args:
        target_date: Date to generate predictions for
        fill_results: If True, also fetch and fill actual winners
        use_cache: Whether to use cached stats
        
    Returns:
        List of PredictionLogEntry objects
    """
    from datetime import datetime
    from model.point_system import score_game_v3
    from model.lineup_adjustment import calculate_lineup_adjusted_strength
    from ingest.team_stats import TeamStrength
    
    # Validate date
    enforce_date_limit(target_date)
    
    date_str = format_date(target_date)
    print(f"\n{'='*60}")
    print(f"Backfilling predictions for {date_str}")
    print(f"{'='*60}")
    
    # Check if we already have predictions for this date
    existing = get_entries_for_date(date_str)
    if existing:
        print(f"  Found {len(existing)} existing predictions for {date_str}")
        if not fill_results:
            print("  Skipping (use --fill-results to update results only)")
            return existing
    
    # Get schedule for target date
    print(f"\n[1/4] Fetching schedule for {date_str}...")
    games = get_asof_schedule(target_date)
    
    if not games:
        print(f"  No games found for {date_str}")
        return []
    
    print(f"  Found {len(games)} games")
    
    # Get as-of team stats
    print(f"\n[2/4] Fetching team stats as-of {date_str}...")
    team_stats = get_asof_team_stats(target_date, use_cache=use_cache)
    team_stats_available = len(team_stats) > 0
    
    # Get as-of player stats
    print(f"\n[3/4] Fetching player stats as-of {date_str}...")
    player_stats = get_asof_player_stats(target_date, use_cache=use_cache)
    player_stats_available = len(player_stats) > 0
    
    # Generate predictions
    print(f"\n[4/4] Generating predictions...")
    predictions = []
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Determine data confidence
    data_confidence = get_data_confidence(
        team_stats_available=team_stats_available,
        player_stats_available=player_stats_available,
        injury_report_available=False,  # Historical injury reports not fetched
    )
    
    for game in games:
        home_team = game['home_team']
        away_team = game['away_team']
        game_id = game.get('game_id', '')
        
        # Get team strengths
        home_ts = team_stats.get(home_team)
        away_ts = team_stats.get(away_team)
        
        if not home_ts or not away_ts:
            print(f"  Warning: Missing stats for {away_team} @ {home_team}")
            continue
        
        # Get player lists
        home_players = player_stats.get(home_team, [])
        away_players = player_stats.get(away_team, [])
        
        # Convert AsOfTeamStats to dict for compatibility
        home_stats_dict = home_ts.to_dict()
        away_stats_dict = away_ts.to_dict()
        
        # Create minimal TeamStrength-like object for lineup adjustment
        class MinimalStrength:
            def __init__(self, stats_dict):
                self.net_rating = stats_dict.get('net_rating', 0)
                self.off_rating = stats_dict.get('off_rating', 110)
                self.def_rating = stats_dict.get('def_rating', 110)
                self.home_net_rating = stats_dict.get('home_net_rating', self.net_rating + 2)
                self.road_net_rating = stats_dict.get('road_net_rating', self.net_rating - 2)
            
            def to_dict(self):
                return {
                    'net_rating': self.net_rating,
                    'off_rating': self.off_rating,
                    'def_rating': self.def_rating,
                    'home_net_rating': self.home_net_rating,
                    'road_net_rating': self.road_net_rating,
                    'pace': 100,
                    'efg_pct': 0.52,
                    'tov_pct': 14,
                    'oreb_pct': 25,
                    'ft_rate': 0.25,
                    'fg3_pct': 0.36,
                    'fg3a_rate': 0.40,
                }
        
        home_strength = MinimalStrength(home_stats_dict)
        away_strength = MinimalStrength(away_stats_dict)
        
        # Convert AsOfPlayerStats to objects with expected attributes
        class MinimalPlayer:
            def __init__(self, p):
                self.player_name = p.player_name
                self.points_per_game = p.points_per_game
                self.assists_per_game = p.assists_per_game
                self.minutes_per_game = p.minutes_per_game
                self.impact_score = p.impact_score
                self.status = "Available"
        
        home_players_obj = [MinimalPlayer(p) for p in home_players]
        away_players_obj = [MinimalPlayer(p) for p in away_players]
        
        # Calculate lineup adjusted strength
        try:
            home_lineup = calculate_lineup_adjusted_strength(
                team=home_team,
                team_strength=home_strength,
                players=home_players_obj,
                injuries=[],
                is_home=True,
            )
            away_lineup = calculate_lineup_adjusted_strength(
                team=away_team,
                team_strength=away_strength,
                players=away_players_obj,
                injuries=[],
                is_home=False,
            )
        except Exception as e:
            print(f"  Warning: Lineup calculation failed for {away_team} @ {home_team}: {e}")
            # Use basic strength
            class BasicStrength:
                def __init__(self, net):
                    self.adjusted_net_rating = net
                    self.availability_score = 1.0
                    self.missing_players = []
                    self.confidence_penalty = 0.0
            
            home_lineup = BasicStrength(home_stats_dict.get('net_rating', 0))
            away_lineup = BasicStrength(away_stats_dict.get('net_rating', 0))
        
        # Score the game
        try:
            score = score_game_v3(
                home_team=home_team,
                away_team=away_team,
                home_strength=home_lineup,
                away_strength=away_lineup,
                home_stats=home_strength.to_dict(),
                away_stats=away_strength.to_dict(),
                home_rest_days=1,
                away_rest_days=1,
                home_players=home_players_obj,
                away_players=away_players_obj,
                home_injuries=[],
                away_injuries=[],
            )
        except Exception as e:
            print(f"  Warning: Scoring failed for {away_team} @ {home_team}: {e}")
            continue
        
        # Create prediction entry
        entry = PredictionLogEntry(
            run_timestamp_local=run_timestamp,
            game_date=date_str,
            game_id=game_id,
            away_team=away_team,
            home_team=home_team,
            pick=score.predicted_winner,
            edge_score_total=round(score.edge_score_total, 2),
            projected_margin_home=round(score.projected_margin_home, 1),
            home_win_prob=round(score.home_win_prob, 3),
            away_win_prob=round(score.away_win_prob, 3),
            confidence_level=score.confidence_label.upper(),
            confidence_pct=score.confidence_pct,
            top_5_factors=score.top_5_factors_str,
            injury_report_url="",
            data_confidence=data_confidence,
        )
        
        predictions.append(entry)
        print(f"  {away_team} @ {home_team}: {score.predicted_winner} ({score.confidence_pct})")
    
    # Save predictions
    if predictions:
        append_predictions(predictions)
        print(f"\n  Saved {len(predictions)} predictions")
    
    # Fill results if requested
    if fill_results:
        print(f"\n[+] Filling results...")
        results = get_asof_game_results(target_date)
        
        if results:
            from utils.storage import update_results_in_log
            updated = update_results_in_log(date_str, results)
            print(f"  Updated {updated} predictions with results")
            
            # Reload to get updated entries
            predictions = get_entries_for_date(date_str)
        else:
            print("  No final results available yet")
    
    return predictions


def backfill_date_range(
    start_date: date,
    end_date: date,
    fill_results: bool = True,
    max_days: int = DEFAULT_MAX_DAYS_PER_RUN,
    use_cache: bool = True,
) -> int:
    """
    Backfill predictions for a range of dates.
    
    Args:
        start_date: Start of range (inclusive)
        end_date: End of range (inclusive)
        fill_results: Whether to fill results for completed games
        max_days: Maximum days to process in one run
        use_cache: Whether to use cached stats
        
    Returns:
        Total number of predictions generated
    """
    # Validate and potentially limit range
    start_date, end_date = validate_date_range(start_date, end_date, max_days)
    
    dates = get_date_range(start_date, end_date)
    
    print(f"\n{'#'*60}")
    print(f"BACKFILL: {format_date(start_date)} to {format_date(end_date)}")
    print(f"         ({len(dates)} days)")
    print(f"{'#'*60}")
    
    total_predictions = 0
    
    for i, d in enumerate(dates, 1):
        print(f"\n[{i}/{len(dates)}]", end="")
        
        try:
            predictions = backfill_predictions(
                target_date=d,
                fill_results=fill_results,
                use_cache=use_cache,
            )
            total_predictions += len(predictions)
        except Exception as e:
            print(f"  Error: {e}")
        
        # Rate limit between dates
        if i < len(dates):
            time.sleep(1)
    
    print(f"\n{'#'*60}")
    print(f"BACKFILL COMPLETE: {total_predictions} predictions generated")
    print(f"{'#'*60}")
    
    # Update performance summary
    from utils.storage import compute_performance_summary, save_performance_summary, format_performance_summary
    summary = compute_performance_summary()
    save_performance_summary(summary)
    print(format_performance_summary(summary))
    
    return total_predictions
