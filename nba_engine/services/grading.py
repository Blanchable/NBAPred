"""
Grading service for NBA Prediction Engine.

Automatically grades picks based on final game scores.
Supports **backfill grading** across multiple past dates so that games
from previous days are scored after midnight (the core fix).

Respects locking — grades can be applied regardless of lock status.
"""

from datetime import datetime, timedelta
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
from .scores import (
    fetch_scores_for_date,
    fetch_scores_for_past_date,
    GameScoreUpdate,
    SCORE_BACKFILL_DAYS,
)


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


def _grade_ungraded_from_scores(
    ungraded_picks: List[dict],
    score_map: dict,
) -> Tuple[int, int]:
    """
    Grade a list of ungraded picks using a pre-built score_map.

    Returns:
        Tuple of (picks_graded, picks_still_pending)
    """
    graded = 0
    pending = 0

    for pick in ungraded_picks:
        game_id = pick['game_id']
        pick_side = pick['pick_side']
        slate_date = pick['slate_date']

        # Try API scores first
        score_update = score_map.get(game_id)

        winner_side = None
        if score_update and score_update.is_final:
            winner_side = score_update.get_winner_side()
        elif (pick.get('status') == 'final'
              and pick.get('away_score') is not None
              and pick.get('home_score') is not None):
            # Fall back to DB data (already written by update_games_from_scores)
            if pick['home_score'] > pick['away_score']:
                winner_side = "HOME"
            elif pick['away_score'] > pick['home_score']:
                winner_side = "AWAY"

        if winner_side is None:
            pending += 1
            continue

        result = "W" if pick_side == winner_side else "L"
        grade_daily_pick(slate_date, game_id, result)
        graded += 1

        matchup = pick.get('matchup',
                           f"{pick.get('away_team', '?')} @ {pick.get('home_team', '?')}")
        print(f"    {matchup}: {pick['pick_team']} ({pick_side}) -> {result}")

    return graded, pending


def grade_picks_for_date(date_str: Optional[str] = None) -> Tuple[int, int, int]:
    """
    Grade all ungraded picks for a specific date.
    
    Uses the live scoreboard for today and ScoreboardV2 for past dates.
    Also locks any games that have started.
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
    
    Returns:
        Tuple of (games_updated, picks_graded, picks_pending)
    """
    if date_str is None:
        date_str = get_today_date_local()
    
    now_local = get_now_local()
    today = get_today_date_local()

    print(f"Grading picks for {date_str}...")
    
    # Fetch scores — live for today, ScoreboardV2 for past dates
    if date_str == today:
        scores = fetch_scores_for_date(date_str)
    else:
        scores = fetch_scores_for_past_date(date_str)
    print(f"  Fetched {len(scores)} games from API")
    
    # Update game records in DB
    games_updated = update_games_from_scores(scores)
    print(f"  Updated {games_updated} game records")
    
    # Lock any games that have started (only meaningful for today)
    if date_str == today:
        locked_count = lock_all_started_games(date_str, now_local)
        if locked_count > 0:
            print(f"  Locked {locked_count} started games")
    
    # Build score lookup by game_id
    score_map = {s.game_id: s for s in scores}
    
    # Get ungraded picks for this date
    all_picks = get_daily_picks(date_str)
    ungraded = [p for p in all_picks if p.get('result') == 'PENDING']
    print(f"  Found {len(ungraded)} ungraded picks")
    
    picks_graded, picks_pending = _grade_ungraded_from_scores(ungraded, score_map)
    
    print(f"  Graded: {picks_graded}, Pending: {picks_pending}")
    return games_updated, picks_graded, picks_pending


def grade_all_pending(
    backfill_days: int = SCORE_BACKFILL_DAYS,
) -> Tuple[int, int, int]:
    """
    Grade all pending picks within the backfill window.

    For each unique slate date with ungraded picks (up to ``backfill_days``
    ago), fetches scores from the appropriate API and grades them.

    This is the **core backfill fix**: previous versions only graded
    today's date, leaving yesterday's picks permanently ungraded after
    midnight.

    Returns:
        Tuple of (total_games_updated, total_picks_graded, total_picks_pending)
    """
    today = get_today_date_local()
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    cutoff = (today_dt - timedelta(days=backfill_days)).strftime("%Y-%m-%d")

    # Get ALL ungraded picks (no date filter)
    all_ungraded = get_ungraded_daily_picks()

    # Apply backfill-window filter
    all_ungraded = [p for p in all_ungraded
                    if p.get('slate_date', '') >= cutoff]

    if not all_ungraded:
        print("No ungraded picks in backfill window.")
        return 0, 0, 0

    # Group by slate_date
    picks_by_date: dict[str, list] = {}
    for pick in all_ungraded:
        d = pick['slate_date']
        picks_by_date.setdefault(d, []).append(pick)

    dates_to_check = sorted(picks_by_date.keys())
    print(f"Grading backfill window: last {backfill_days} days (cutoff {cutoff})")
    print(f"Found {len(all_ungraded)} ungraded games across {len(dates_to_check)} dates")

    total_updated = 0
    total_graded = 0
    total_pending = 0

    for date_str in dates_to_check:
        picks = picks_by_date[date_str]
        print(f"\nProcessing {date_str} ({len(picks)} picks)...")

        # Fetch scores for this date (live for today, historical otherwise)
        if date_str == today:
            scores = fetch_scores_for_date(date_str)
        else:
            scores = fetch_scores_for_past_date(date_str)

        # Update game records in DB
        games_updated = update_games_from_scores(scores)
        total_updated += games_updated

        # Build score lookup
        score_map = {s.game_id: s for s in scores}

        # Re-fetch picks from DB (scores may have just been written)
        fresh_picks = get_daily_picks(date_str)
        fresh_ungraded = [p for p in fresh_picks if p.get('result') == 'PENDING']

        graded, pending = _grade_ungraded_from_scores(fresh_ungraded, score_map)
        total_graded += graded
        total_pending += pending

        print(f"  Graded: {graded}, Pending: {pending}")

    print(f"\nBackfill complete: updated {total_updated} games, "
          f"graded {total_graded} picks, {total_pending} still pending")
    return total_updated, total_graded, total_pending
