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
    get_first_game_time,
    get_historical_injury_report,
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
    print(f"\n[1/5] Fetching schedule for {date_str}...")
    games = get_asof_schedule(target_date)
    
    if not games:
        print(f"  No games found for {date_str}")
        return []
    
    print(f"  Found {len(games)} games")
    # Debug: show first 3 games
    for i, g in enumerate(games[:3]):
        print(f"    Game {i+1}: {g['away_team']} @ {g['home_team']} (id: {g['game_id']})")
    
    # Get as-of team stats
    print(f"\n[2/5] Fetching team stats as-of {date_str}...")
    team_stats = get_asof_team_stats(target_date, use_cache=use_cache)
    team_stats_available = len(team_stats) > 0
    print(f"  Loaded {len(team_stats)} team stats")
    
    # Get as-of player stats
    print(f"\n[3/5] Fetching player stats as-of {date_str}...")
    player_stats = get_asof_player_stats(target_date, use_cache=use_cache)
    player_stats_available = len(player_stats) > 0
    print(f"  Loaded player stats for {len(player_stats)} teams")
    
    # Get historical injury report (1 hour before first game)
    print(f"\n[4/5] Fetching historical injury report...")
    first_game_time = get_first_game_time(games, target_date)
    injuries, injury_url, injury_report_available = get_historical_injury_report(
        target_date=target_date,
        first_game_time=first_game_time,
        hours_before=1.0,
    )
    
    # Generate predictions
    print(f"\n[5/5] Generating predictions...")
    
    # Track missing stats for debug
    missing_stats_warned = set()
    predictions = []
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Determine data confidence
    data_confidence = get_data_confidence(
        team_stats_available=team_stats_available,
        player_stats_available=player_stats_available,
        injury_report_available=injury_report_available,
    )
    
    for game in games:
        home_team = game['home_team']
        away_team = game['away_team']
        game_id = game.get('game_id', '')
        
        # Get team strengths
        home_ts = team_stats.get(home_team)
        away_ts = team_stats.get(away_team)
        
        if not home_ts or not away_ts:
            # Only warn once per missing team
            missing = []
            if not home_ts and home_team not in missing_stats_warned:
                missing.append(home_team)
                missing_stats_warned.add(home_team)
            if not away_ts and away_team not in missing_stats_warned:
                missing.append(away_team)
                missing_stats_warned.add(away_team)
            if missing:
                print(f"  Warning: Missing stats for team(s): {', '.join(missing)}")
            continue
        
        # Get player lists
        home_players = player_stats.get(home_team, [])
        away_players = player_stats.get(away_team, [])
        
        # Convert AsOfTeamStats to dict for compatibility
        home_stats_dict = home_ts.to_dict()
        away_stats_dict = away_ts.to_dict()
        
        # Create strength object that passes through ALL actual stats
        class HistoricalStrength:
            """Wraps historical team stats for compatibility with scoring model."""
            def __init__(self, stats_dict):
                self._stats = stats_dict
                # Core ratings
                self.net_rating = stats_dict.get('net_rating', 0)
                self.off_rating = stats_dict.get('off_rating', 110)
                self.def_rating = stats_dict.get('def_rating', 110)
                self.home_net_rating = stats_dict.get('home_net_rating', self.net_rating + 2)
                self.road_net_rating = stats_dict.get('road_net_rating', self.net_rating - 2)
                # Advanced stats
                self.pace = stats_dict.get('pace', 100)
                self.efg_pct = stats_dict.get('efg_pct', 0.52)
                self.tov_pct = stats_dict.get('tov_pct', 14)
                self.oreb_pct = stats_dict.get('oreb_pct', 25)
                self.ft_rate = stats_dict.get('ft_rate', 0.25)
                self.fg3_pct = stats_dict.get('fg3_pct', 0.36)
                self.fg3a_rate = stats_dict.get('fg3a_rate', 0.40)
            
            def to_dict(self):
                """Return ALL actual stats, not hardcoded defaults."""
                return {
                    'net_rating': self.net_rating,
                    'off_rating': self.off_rating,
                    'def_rating': self.def_rating,
                    'home_net_rating': self.home_net_rating,
                    'road_net_rating': self.road_net_rating,
                    'pace': self.pace,
                    'efg_pct': self.efg_pct,
                    'tov_pct': self.tov_pct,
                    'oreb_pct': self.oreb_pct,
                    'ft_rate': self.ft_rate,
                    'fg3_pct': self.fg3_pct,
                    'fg3a_rate': self.fg3a_rate,
                    # Include any additional stats from the source
                    **{k: v for k, v in self._stats.items() 
                       if k not in ['team', 'as_of_date', 'games_played', 'wins', 'losses']}
                }
        
        home_strength = HistoricalStrength(home_stats_dict)
        away_strength = HistoricalStrength(away_stats_dict)
        
        # Filter injuries for each team
        home_injuries = [inj for inj in injuries 
                        if getattr(inj, 'team', '').upper() == home_team.upper()]
        away_injuries = [inj for inj in injuries 
                        if getattr(inj, 'team', '').upper() == away_team.upper()]
        
        # Helper to find player's injury status
        def get_player_injury_status(player_name, team_injuries):
            """Look up player's status from injuries list."""
            player_name_lower = player_name.lower()
            for inj in team_injuries:
                inj_player = getattr(inj, 'player', '') or ''
                if player_name_lower in inj_player.lower() or inj_player.lower() in player_name_lower:
                    return getattr(inj, 'status', 'Available')
            return "Available"
        
        # Convert AsOfPlayerStats to objects with expected attributes
        class HistoricalPlayer:
            """Wraps historical player stats for compatibility with scoring model."""
            def __init__(self, p, team_injuries):
                self.player_name = p.player_name
                self.player_id = getattr(p, 'player_id', '')
                self.team = getattr(p, 'team', '')
                self.points_per_game = p.points_per_game
                self.ppg = p.points_per_game  # Alias
                self.assists_per_game = p.assists_per_game
                self.apg = p.assists_per_game  # Alias
                self.minutes_per_game = p.minutes_per_game
                self.mpg = p.minutes_per_game  # Alias
                self.rebounds_per_game = getattr(p, 'rebounds_per_game', 0)
                self.impact_score = p.impact_score
                # Get status from historical injury report
                self.status = get_player_injury_status(p.player_name, team_injuries)
                self.is_star = False  # Will be set by lineup adjustment
                self.impact_rank = 0  # Will be set by lineup adjustment
        
        home_players_obj = [HistoricalPlayer(p, home_injuries) for p in home_players]
        away_players_obj = [HistoricalPlayer(p, away_injuries) for p in away_players]
        
        # Calculate lineup adjusted strength
        try:
            home_lineup = calculate_lineup_adjusted_strength(
                team=home_team,
                team_strength=home_strength,
                players=home_players_obj,
                injuries=home_injuries,
                is_home=True,
                injury_report_available=injury_report_available,
            )
            away_lineup = calculate_lineup_adjusted_strength(
                team=away_team,
                team_strength=away_strength,
                players=away_players_obj,
                injuries=away_injuries,
                is_home=False,
                injury_report_available=injury_report_available,
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
                home_injuries=home_injuries,
                away_injuries=away_injuries,
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
            injury_report_url=injury_url or "",
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
