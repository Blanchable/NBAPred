"""
Roster instability estimation for trade-aware predictions.

Estimates how much a team's rotation has changed recently by comparing
"rotation signatures" across consecutive days.  A large change (trades,
call-ups, injury waves) triggers higher recency weighting and lower
model confidence, preventing "false locks" on stale data.

No actual trade detection is attempted; the signal comes entirely from
minutes-distribution and availability shifts.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from model.config import (
    INSTABILITY_CONFIDENCE_MULT_HIGH,
    INSTABILITY_CONFIDENCE_MULT_LOW,
    INSTABILITY_HIGH_THRESHOLD,
    INSTABILITY_LOW_THRESHOLD,
    INSTABILITY_NETRATING_MULT_HIGH,
    INSTABILITY_NETRATING_MULT_LOW,
    INSTABILITY_SCORE_PENALTY_MAX,
    RECENCY_BASE_WEIGHT,
    RECENCY_MAX_WEIGHT,
)

# ============================================================================
# PATHS
# ============================================================================

_SIGNATURES_DIR = Path(__file__).resolve().parent.parent / "data"
SIGNATURES_FILE = _SIGNATURES_DIR / "rotation_signatures.json"


# ============================================================================
# ROTATION SIGNATURES
# ============================================================================

def build_rotation_signature(
    player_stats_by_team: Dict[str, list],
    injuries_by_team: Optional[Dict[str, list]] = None,
    top_n: int = 8,
) -> Dict[str, list]:
    """
    Build today's rotation signature for every team.

    A signature is a list of dicts, one per top-N player (by MPG),
    each containing ``name``, ``mpg``, and ``status``.

    Args:
        player_stats_by_team: team_abbrev -> list[PlayerImpact]
        injuries_by_team:     team_abbrev -> list[InjuryRow] (optional)
        top_n: how many top players to include per team

    Returns:
        Dict mapping team_abbrev -> list of player signature dicts
    """
    if injuries_by_team is None:
        injuries_by_team = {}

    # Pre-build injury lookup:  (team, normalized_name) -> status bucket
    injury_lookup: Dict[tuple, str] = {}
    for team, rows in injuries_by_team.items():
        for row in rows:
            player_name = row.player if hasattr(row, "player") else str(row)
            status = _status_bucket(
                row.status if hasattr(row, "status") else "Available"
            )
            key = (team, _norm(player_name))
            injury_lookup[key] = status

    signatures: Dict[str, list] = {}

    for team, players in player_stats_by_team.items():
        # Sort by minutes descending, take top N
        sorted_players = sorted(
            players,
            key=lambda p: getattr(p, "minutes_per_game", 0),
            reverse=True,
        )[:top_n]

        sig = []
        for p in sorted_players:
            name = getattr(p, "player_name", str(p))
            mpg = getattr(p, "minutes_per_game", 0.0)
            status = injury_lookup.get((team, _norm(name)), "OK")
            sig.append({
                "name": _norm(name),
                "mpg": round(mpg, 1),
                "status": status,
            })
        signatures[team] = sig

    return signatures


def compute_instability(
    sig_today: Optional[list],
    sig_prev: Optional[list],
) -> float:
    """
    Compare two rotation signatures and return an instability score in [0, 1].

    If either signature is None the comparison is impossible, so 0.0 is
    returned (no penalty on first run or missing data).
    """
    if not sig_today or not sig_prev:
        return 0.0

    prev_map = {entry["name"]: entry for entry in sig_prev}
    today_total_mpg = sum(e.get("mpg", 0) for e in sig_today) or 1.0

    change = 0.0
    for entry in sig_today:
        name = entry["name"]
        mpg_today = entry.get("mpg", 0)

        prev_entry = prev_map.get(name)
        if prev_entry is None:
            # Completely new player in rotation
            change += mpg_today
        else:
            change += abs(mpg_today - prev_entry.get("mpg", 0))
            # Status swing also counts
            if entry.get("status") != prev_entry.get("status"):
                change += 3.0  # small penalty for status shift

    # Also account for players who dropped out entirely
    today_names = {e["name"] for e in sig_today}
    for entry in sig_prev:
        if entry["name"] not in today_names:
            change += entry.get("mpg", 0)

    # Normalize by twice the total minutes (symmetric range)
    instability = change / (2 * today_total_mpg)
    return min(1.0, max(0.0, instability))


# ============================================================================
# PERSISTENCE
# ============================================================================

def save_signatures(date_str: str, signatures: Dict[str, list]) -> None:
    """Persist today's rotation signatures to JSON."""
    data = _load_all_signatures()
    data[date_str] = signatures

    # Prune entries older than 30 days to keep the file small
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    data = {k: v for k, v in data.items() if k >= cutoff}

    _SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    with open(SIGNATURES_FILE, "w") as f:
        json.dump(data, f, indent=1)


def load_previous_signatures(
    today_str: str,
    lookback_days: int = 1,
) -> Optional[Dict[str, list]]:
    """
    Load the most recent signature file *before* ``today_str``.

    Searches up to ``lookback_days`` back and returns the first match.
    """
    data = _load_all_signatures()
    today = datetime.strptime(today_str, "%Y-%m-%d")
    for offset in range(1, lookback_days + 1):
        check_date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        if check_date in data:
            return data[check_date]
    return None


def _load_all_signatures() -> dict:
    if SIGNATURES_FILE.exists():
        try:
            with open(SIGNATURES_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


# ============================================================================
# INSTABILITY -> MODEL MODIFIERS
# ============================================================================

def instability_to_recency_weight(instability: float) -> float:
    """Map instability [0, 1] to a recency weight in [BASE, MAX]."""
    w = RECENCY_BASE_WEIGHT + instability * (RECENCY_MAX_WEIGHT - RECENCY_BASE_WEIGHT)
    return min(RECENCY_MAX_WEIGHT, max(RECENCY_BASE_WEIGHT, w))


def instability_bucket(instability: float) -> str:
    """Classify instability into NONE / LOW / HIGH."""
    if instability >= INSTABILITY_HIGH_THRESHOLD:
        return "HIGH"
    if instability >= INSTABILITY_LOW_THRESHOLD:
        return "LOW"
    return "NONE"


def instability_conf_mult(instability: float) -> float:
    """Return the confidence-compression multiplier for a given instability."""
    if instability >= INSTABILITY_HIGH_THRESHOLD:
        return INSTABILITY_CONFIDENCE_MULT_HIGH
    if instability >= INSTABILITY_LOW_THRESHOLD:
        return INSTABILITY_CONFIDENCE_MULT_LOW
    return 1.0


def instability_netrating_mult(instability: float) -> float:
    """Return the net-rating dampening multiplier for a given instability."""
    if instability >= INSTABILITY_HIGH_THRESHOLD:
        return INSTABILITY_NETRATING_MULT_HIGH
    if instability >= INSTABILITY_LOW_THRESHOLD:
        return INSTABILITY_NETRATING_MULT_LOW
    return 1.0


def instability_score_penalty(instability: float) -> float:
    """Small edge-score penalty proportional to instability (for bucket/lock only)."""
    return min(INSTABILITY_SCORE_PENALTY_MAX, instability * INSTABILITY_SCORE_PENALTY_MAX)


# ============================================================================
# CONVENIENCE: compute instability_map for all teams in one shot
# ============================================================================

def compute_instability_map(
    player_stats_by_team: Dict[str, list],
    injuries_by_team: Optional[Dict[str, list]] = None,
    today_str: Optional[str] = None,
    lookback_days: int = 7,
) -> Dict[str, float]:
    """
    End-to-end helper: build today's signatures, load previous, compute
    per-team instability, persist today's data, and return a dict of
    team_abbrev -> instability float.
    """
    if today_str is None:
        today_str = datetime.now().strftime("%Y-%m-%d")

    sig_today = build_rotation_signature(player_stats_by_team, injuries_by_team)
    sig_prev = load_previous_signatures(today_str, lookback_days=lookback_days)

    instability_map: Dict[str, float] = {}
    for team, team_sig in sig_today.items():
        prev_team_sig = sig_prev.get(team) if sig_prev else None
        instability_map[team] = compute_instability(team_sig, prev_team_sig)

    # Persist today's signatures for tomorrow's comparison
    save_signatures(today_str, sig_today)

    return instability_map


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _norm(name: str) -> str:
    """Cheap normalisation for player-name matching."""
    import re
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def _status_bucket(raw: str) -> str:
    upper = raw.upper().strip()
    if upper in ("OUT", "INACTIVE", "NOT WITH TEAM", "SUSPENDED"):
        return "OUT"
    if upper == "DOUBTFUL":
        return "DOUBTFUL"
    if upper == "QUESTIONABLE":
        return "QUESTIONABLE"
    return "OK"
