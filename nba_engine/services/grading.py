"""
Grading service for NBA Prediction Engine.

Automatically grades picks based on final game scores.
Respects locking - grades can be applied regardless of lock status.
"""

from datetime import datetime
from typing import List, Tuple, Optional

from storage.db import (
    get_ungraded_daily_picks,
    get_games_for_date,
    update_game_score,
    grade_daily_pick,
    lock_all_started_games,
    get_daily_picks,
    connect,
    get_now_local,
    get_today_date_local,
)
from .scores import fetch_scores_for_date, GameScoreUpdate


def update_games_from_scores(scores: List[GameScoreUpdate]) -> int:
    """
    Update game records in database from score updates.
    
    Args:
        scores: List of GameScoreUpdate objects from score provider
    
    Returns:
        Number of games updated
    """
    updated = 0
    
    for score in scores:
        if not score.game_id:
            continue
        
        update_game_score(
            game_id=score.game_id,
            status=score.status,
            away_score=score.away_score,
            home_score=score.home_score,
        )
        updated += 1
    
    return updated


def grade_picks_for_date(date_str: Optional[str] = None) -> Tuple[int, int, int]:
    """
    Grade all ungraded picks for a specific date.
    
    Also locks any games that have started.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    
    Returns:
        Tuple of (games_updated, picks_graded, picks_pending)
    """
    if date_str is None:
        date_str = get_today_date_local()
    
    now_local = get_now_local()
    print(f"Grading picks for {date_str}...")
    
    # Fetch latest scores
    scores = fetch_scores_for_date(date_str)
    print(f"  Fetched {len(scores)} games from API")
    
    # Update game records
    games_updated = update_games_from_scores(scores)
    print(f"  Updated {games_updated} game records")
    
    # Lock any games that have started
    locked_count = lock_all_started_games(date_str, now_local)
    if locked_count > 0:
        print(f"  Locked {locked_count} started games")
    
    # Build score lookup by game_id
    score_map = {s.game_id: s for s in scores}
    
    # Get all picks for this date (including already graded for status check)
    all_picks = get_daily_picks(date_str)
    ungraded = [p for p in all_picks if p.get('result') == 'PENDING']
    print(f"  Found {len(ungraded)} ungraded picks")
    
    picks_graded = 0
    picks_pending = 0
    
    for pick in ungraded:
        game_id = pick['game_id']
        pick_side = pick['pick_side']
        slate_date = pick['slate_date']
        
        # Get score info - first try our fetched scores
        score_update = score_map.get(game_id)
        
        if score_update and score_update.is_final:
            # Use API data
            winner_side = score_update.get_winner_side()
            away_score = score_update.away_score
            home_score = score_update.home_score
        elif pick.get('status') == 'final' and pick.get('away_score') is not None and pick.get('home_score') is not None:
            # Use database data
            away_score = pick['away_score']
            home_score = pick['home_score']
            if home_score > away_score:
                winner_side = "HOME"
            elif away_score > home_score:
                winner_side = "AWAY"
            else:
                winner_side = None  # Tie
        else:
            # Game not final yet
            picks_pending += 1
            continue
        
        if winner_side is None:
            # Tie or unknown - leave pending
            picks_pending += 1
            continue
        
        # Determine if pick was correct
        if pick_side == winner_side:
            result = "W"
        else:
            result = "L"
        
        grade_daily_pick(slate_date, game_id, result)
        picks_graded += 1
        
        matchup = pick.get('matchup', f"{pick.get('away_team', '?')} @ {pick.get('home_team', '?')}")
        print(f"    {matchup}: {pick['pick_team']} ({pick_side}) -> {result}")
    
    print(f"  Graded: {picks_graded}, Pending: {picks_pending}")
    
    return games_updated, picks_graded, picks_pending


def grade_all_pending() -> Tuple[int, int, int]:
    """
    Grade all pending picks across all dates.
    
    Fetches scores for today (live API only shows today) and grades
    any matching pending picks.
    
    Returns:
        Tuple of (games_updated, picks_graded, picks_pending)
    """
    today = get_today_date_local()
    
    # Get all ungraded picks
    all_ungraded = get_ungraded_daily_picks()
    print(f"Found {len(all_ungraded)} total pending picks")
    
    # Group by date
    picks_by_date = {}
    for pick in all_ungraded:
        slate_date = pick.get('slate_date')
        if slate_date:
            if slate_date not in picks_by_date:
                picks_by_date[slate_date] = []
            picks_by_date[slate_date].append(pick)
    
    total_updated = 0
    total_graded = 0
    total_pending = 0
    
    # Process each date
    for date_str, picks in picks_by_date.items():
        print(f"\nProcessing {date_str} ({len(picks)} picks)...")
        
        if date_str == today:
            # Fetch fresh scores for today
            updated, graded, pending = grade_picks_for_date(date_str)
            total_updated += updated
            total_graded += graded
            total_pending += pending
        else:
            # For past dates, check if game data in DB has scores
            for pick in picks:
                if pick.get('status') == 'final' and pick.get('away_score') is not None and pick.get('home_score') is not None:
                    pick_side = pick['pick_side']
                    
                    if pick['home_score'] > pick['away_score']:
                        winner_side = "HOME"
                    elif pick['away_score'] > pick['home_score']:
                        winner_side = "AWAY"
                    else:
                        total_pending += 1
                        continue  # Tie
                    
                    result = "W" if pick_side == winner_side else "L"
                    grade_daily_pick(pick['slate_date'], pick['game_id'], result)
                    total_graded += 1
                else:
                    total_pending += 1
    
    return total_updated, total_graded, total_pending
