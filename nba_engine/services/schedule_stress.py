"""
Schedule stress estimation for NBA predictions.

Captures real schedule effects (back-to-backs, 3-in-4, travel) that
are orthogonal to team-strength and roster-instability factors.

Usage in the model:
- A small scoring factor (weight 3)
- A small confidence compression (~5 % at extreme stress)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from data.arenas import travel_distance_km


# ============================================================================
# SCHEDULE DATA LOADING
# ============================================================================

@dataclass
class RecentGame:
    """A game a team recently played."""
    date: str  # YYYY-MM-DD
    opponent: str
    location: str  # "Home" or "Away"


def load_team_recent_games(
    team_abbrev: str,
    target_date: str,
    season: str = "2024-25",
    lookback_days: int = 7,
    timeout: int = 30,
) -> List[RecentGame]:
    """
    Load a team's recent games in the lookback window.

    Uses TeamGameLog which is already imported in team_stats.
    """
    from nba_api.stats.endpoints import teamgamelog
    from nba_api.stats.static import teams as nba_teams

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.nba.com',
        'Referer': 'https://www.nba.com/',
    }
    abbrev_to_id = {t['abbreviation']: t['id'] for t in nba_teams.get_teams()}

    team_id = abbrev_to_id.get(team_abbrev)
    if not team_id:
        return []

    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    cutoff = target - timedelta(days=lookback_days)

    try:
        gl = teamgamelog.TeamGameLog(
            team_id=team_id,
            season=season,
            timeout=timeout,
            headers=HEADERS,
        )
        df = gl.get_data_frames()[0]
    except Exception:
        return []

    recent: List[RecentGame] = []
    for _, row in df.iterrows():
        try:
            gdate = datetime.strptime(row["GAME_DATE"], "%b %d, %Y").date()
        except Exception:
            continue
        if cutoff <= gdate < target:
            matchup = str(row.get("MATCHUP", ""))
            location = "Away" if "@" in matchup else "Home"
            # Extract opponent abbreviation (last 3 chars)
            opp = matchup.strip()[-3:]
            recent.append(RecentGame(date=gdate.strftime("%Y-%m-%d"), opponent=opp, location=location))
    return recent


# ============================================================================
# STRESS COMPONENTS
# ============================================================================

def is_back_to_back(recent_games: List[RecentGame], target_date: str) -> bool:
    """True if the team played the day before target_date."""
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    yesterday = (target - timedelta(days=1)).strftime("%Y-%m-%d")
    return any(g.date == yesterday for g in recent_games)


def games_last_n_days(recent_games: List[RecentGame], target_date: str, n: int = 4) -> int:
    """Count games in [target_date - (n-1), target_date - 1]."""
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    cutoff = target - timedelta(days=n)
    return sum(1 for g in recent_games if cutoff < datetime.strptime(g.date, "%Y-%m-%d").date() < target)


def last_game_city(recent_games: List[RecentGame], team_abbrev: str) -> Optional[str]:
    """Return the city (team abbrev) of the most recent game."""
    if not recent_games:
        return None
    # Sort by date descending
    sorted_games = sorted(recent_games, key=lambda g: g.date, reverse=True)
    last = sorted_games[0]
    # If away, city = opponent; if home, city = team
    return last.opponent if last.location == "Away" else team_abbrev


# ============================================================================
# COMPOSITE SCORE
# ============================================================================

def schedule_stress_score(
    b2b: bool,
    games_last_4: int,
    travel_km: float,
) -> float:
    """
    Compute raw schedule stress score (0 .. ~2.4).

    Components:
      B2B:         +1.0
      3-in-4 days: +0.6
      4-in-5 days: +0.8  (cumulative with 3-in-4)
      Travel:      up to +0.6 (proportional to distance / 2500 km)
    """
    score = 0.0
    if b2b:
        score += 1.0
    if games_last_4 >= 3:
        score += 0.6
    if games_last_4 >= 4:
        score += 0.8
    score += min(1.0, travel_km / 2500.0) * 0.6
    return min(2.4, score)


MAX_RAW_STRESS = 2.4


def normalize_stress(raw: float) -> float:
    """Normalize raw stress to [0, 1]."""
    return min(1.0, max(0.0, raw / MAX_RAW_STRESS))


# ============================================================================
# CONVENIENCE: per-game stress context
# ============================================================================

@dataclass
class TeamStressContext:
    """Schedule stress data for one team in one game."""
    team: str
    is_b2b: bool
    games_last_4: int
    travel_km: float
    raw_score: float
    normalized: float


def compute_team_stress(
    team_abbrev: str,
    target_date: str,
    game_location_team: str,
    season: str = "2024-25",
    timeout: int = 30,
) -> TeamStressContext:
    """
    Compute schedule stress for a single team on a given date.

    Args:
        team_abbrev: The team.
        target_date: Game date (YYYY-MM-DD).
        game_location_team: The home team of today's game (to determine
            whether `team_abbrev` is travelling to a different city).
        season: NBA season string.
        timeout: API timeout.
    """
    recent = load_team_recent_games(team_abbrev, target_date, season=season, timeout=timeout)

    b2b = is_back_to_back(recent, target_date)
    g4 = games_last_n_days(recent, target_date, n=4)

    prev_city = last_game_city(recent, team_abbrev)
    # Today's city = home team city
    today_city = game_location_team
    t_km = travel_distance_km(prev_city, today_city) if prev_city else 0.0

    raw = schedule_stress_score(b2b, g4, t_km)
    norm = normalize_stress(raw)

    return TeamStressContext(
        team=team_abbrev,
        is_b2b=b2b,
        games_last_4=g4,
        travel_km=round(t_km, 0),
        raw_score=round(raw, 2),
        normalized=round(norm, 3),
    )


def compute_game_stress(
    home_team: str,
    away_team: str,
    target_date: str,
    season: str = "2024-25",
    timeout: int = 30,
) -> Dict[str, TeamStressContext]:
    """Compute stress for both teams in a game."""
    home_ctx = compute_team_stress(home_team, target_date, home_team, season, timeout)
    away_ctx = compute_team_stress(away_team, target_date, home_team, season, timeout)
    return {home_team: home_ctx, away_team: away_ctx}
