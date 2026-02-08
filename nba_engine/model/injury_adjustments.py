"""
Injury-based efficiency adjustments for NBA Prediction Engine.

When a Tier-1 offensive hub is OUT, the team's ORTG and Net Rating
inputs to the scoring factors must drop accordingly.  This module
computes those per-100-possession penalties and also provides a
validation gate that prevents injury data from leaking across games
(e.g., a player on team X being applied to team Y's matchup).

Design principles:
- Conservative penalties with aggressive shrinkage (0.60) and hard caps.
- Only triggered by OUT status (not Questionable / Probable).
- Penalties flow into the SAME inputs used by Off vs Def and Net Rating,
  so we reduce Star Impact weight to avoid double counting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple
import re


# ============================================================================
# CONSTANTS
# ============================================================================

# Shrinkage factor — we deliberately under-react rather than over-react
SHRINK = 0.60

# Per-100-possession base penalties by tier + role
# (off_penalty, net_penalty)
PENALTY_TABLE = {
    ("T1", "CREATOR"):     (4.5, 4.0),
    ("T1", "NON_CREATOR"): (1.5, 2.5),
    ("T2", "CREATOR"):     (2.0, 1.8),
    ("T2", "NON_CREATOR"): (1.0, 1.5),
}

# Hard caps on cumulative penalty per team
CAP_OFF = 7.0
CAP_NET = 6.0

# Assists threshold to classify as "CREATOR"
CREATOR_APG_THRESHOLD = 5.0


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PlayerOutInfo:
    """Describes an OUT player for efficiency adjustment purposes."""
    team: str
    player_name: str
    player_id: int = 0
    tier: str = "T2"          # "T1" or "T2"
    role: str = "NON_CREATOR" # "CREATOR" or "NON_CREATOR"
    mpg: float = 0.0


@dataclass
class TeamEfficiencyAdj:
    """Computed efficiency penalties for one team."""
    off_penalty: float = 0.0   # per-100 ORTG drop
    net_penalty: float = 0.0   # per-100 Net Rating drop
    has_t1_creator_out: bool = False
    details: list = None        # list of strings describing each OUT contribution

    def __post_init__(self):
        if self.details is None:
            self.details = []


# ============================================================================
# ROLE CLASSIFICATION
# ============================================================================

def classify_player_role(player) -> str:
    """Classify a player as CREATOR or NON_CREATOR based on assists."""
    apg = getattr(player, 'assists_per_game', 0) or 0
    return "CREATOR" if apg >= CREATOR_APG_THRESHOLD else "NON_CREATOR"


# ============================================================================
# BUILD OUT-LIST FROM STAR TIERS + INJURIES
# ============================================================================

def build_out_list(
    players: list,
    injuries: list,
    team: str,
    valid_ids: Optional[Set[int]] = None,
    valid_names: Optional[Set[str]] = None,
) -> List[PlayerOutInfo]:
    """
    Build a list of PlayerOutInfo for players who are OUT on this team.

    Only considers Tier-A (T1) and Tier-B (T2) players (by star_impact
    tiering).  Validates players belong to the team's roster.

    Args:
        players:     Team's PlayerImpact list.
        injuries:    Injury rows (may include other teams).
        team:        Team abbreviation (e.g. "IND").
        valid_ids:   Optional set of roster player_ids for validation.
        valid_names: Optional set of normalised roster names.

    Returns:
        List of PlayerOutInfo for truly-OUT, validated players.
    """
    from .star_impact import select_star_tiers, get_player_status, status_multiplier

    tiers = select_star_tiers(players)

    # Map tier label
    tier_map = {}
    for p in tiers.get("tier_a", []):
        tier_map[_pid(p)] = "T1"
    for p in tiers.get("tier_b", []):
        tier_map[_pid(p)] = "T2"

    out_list: List[PlayerOutInfo] = []

    # Filter injuries to this team only
    team_injuries = [
        inj for inj in (injuries or [])
        if getattr(inj, 'team', '').upper() == team.upper()
    ]

    for p in (tiers.get("tier_a", []) + tiers.get("tier_b", [])):
        pid = _pid(p)
        tier = tier_map.get(pid, "T2")

        # ── Validation gate (STEP 5) ──────────────────────────────
        p_id = getattr(p, 'player_id', 0) or 0
        p_name_norm = _norm(getattr(p, 'player_name', ''))
        if valid_ids and p_id and p_id not in valid_ids:
            print(f"  [INJURY_GATE] Ignoring {getattr(p, 'player_name', '?')} "
                  f"(id={p_id}) — not in {team} roster ids")
            continue
        if valid_names and p_name_norm and p_name_norm not in valid_names:
            print(f"  [INJURY_GATE] Ignoring {getattr(p, 'player_name', '?')} "
                  f"— not in {team} roster names")
            continue

        status = get_player_status(p, team_injuries)
        mult = status_multiplier(status)

        if mult > 0.0:
            # Not OUT — skip
            continue

        role = classify_player_role(p)
        mpg = getattr(p, 'minutes_per_game', 0) or 0

        out_list.append(PlayerOutInfo(
            team=team,
            player_name=getattr(p, 'player_name', 'Unknown'),
            player_id=p_id,
            tier=tier,
            role=role,
            mpg=mpg,
        ))

    return out_list


# ============================================================================
# COMPUTE EFFICIENCY ADJUSTMENTS
# ============================================================================

def compute_team_efficiency_adj(out_list: List[PlayerOutInfo]) -> TeamEfficiencyAdj:
    """
    Compute per-100-possession ORTG and Net Rating penalties for a team
    given its list of OUT star-tier players.

    Uses conservative base penalties, scales by minutes share, applies
    shrinkage, and caps the total.
    """
    adj = TeamEfficiencyAdj()

    for p in out_list:
        base = PENALTY_TABLE.get((p.tier, p.role), (1.0, 1.0))
        base_off, base_net = base

        # Scale by approximate minutes share (proxy if on/off data absent)
        minute_share = max(0.35, min(1.0, p.mpg / 36.0)) if p.mpg > 0 else 0.5

        off_pen = base_off * minute_share * SHRINK
        net_pen = base_net * minute_share * SHRINK

        adj.off_penalty += off_pen
        adj.net_penalty += net_pen

        if p.tier == "T1" and p.role == "CREATOR":
            adj.has_t1_creator_out = True

        adj.details.append(
            f"{p.player_name}({p.tier}/{p.role}) mpg={p.mpg:.0f} "
            f"offP={off_pen:.1f} netP={net_pen:.1f}"
        )

    # Hard cap
    adj.off_penalty = min(adj.off_penalty, CAP_OFF)
    adj.net_penalty = min(adj.net_penalty, CAP_NET)

    return adj


# ============================================================================
# ROSTER VALIDATION HELPERS
# ============================================================================

def build_valid_sets(players: list) -> Tuple[Set[int], Set[str]]:
    """
    Build validation sets from a team's player list.

    Returns:
        (set_of_player_ids, set_of_normalized_names)
    """
    ids: Set[int] = set()
    names: Set[str] = set()
    for p in players:
        pid = getattr(p, 'player_id', 0) or 0
        if pid:
            ids.add(pid)
        name = getattr(p, 'player_name', '')
        if name:
            names.add(_norm(name))
    return ids, names


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _pid(player) -> str:
    """Cheap unique key for a player (name + id)."""
    name = getattr(player, 'player_name', 'unk')
    pid = getattr(player, 'player_id', 0) or 0
    return f"{name}:{pid}"


def _norm(name: str) -> str:
    """Normalise a player name for matching."""
    return re.sub(r"[^a-z ]", "", name.lower()).strip()
