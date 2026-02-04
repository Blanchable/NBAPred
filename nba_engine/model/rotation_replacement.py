"""
Rotation Replacement factor for NBA Prediction Engine.

This factor activates ONLY when a Tier A or Tier B star is OUT or DOUBTFUL.
It evaluates the quality of replacement players (next-man-up).

Key features:
- Only triggers for true star absences, not role player injuries
- Bounded contribution to prevent over-weighting
- Uses existing player stats (PPG, MPG) without new data sources
"""

from dataclasses import dataclass
from typing import Optional

from .star_impact import (
    select_star_tiers,
    status_multiplier,
    get_player_status,
    impact_metric,
)


# Replacement edge clamp limits
REPLACEMENT_EDGE_CLAMP = 2.5

# Status threshold for "absent" (OUT or DOUBTFUL)
ABSENT_THRESHOLD = 0.25

# MPG range for replacement candidates
MIN_REPLACEMENT_MPG = 10.0
MAX_REPLACEMENT_MPG = 30.0


@dataclass
class ReplacementCandidate:
    """Details about a replacement candidate."""
    name: str
    ppg: float
    mpg: float
    ppm: float  # Points per minute
    status: str
    quality_score: float


@dataclass
class AbsentStar:
    """Details about an absent star."""
    name: str
    tier: str
    ppg: float
    mpg: float
    ppm: float
    status: str


def star_absent(tiers: dict, injuries: list = None) -> bool:
    """
    Check if any Tier A or Tier B player is OUT or DOUBTFUL.
    
    Args:
        tiers: Dict with "tier_a" and "tier_b" player lists
        injuries: Optional list of injury records
    
    Returns:
        True if any star is absent (status_multiplier <= 0.25)
    """
    for tier_key in ["tier_a", "tier_b"]:
        for player in tiers.get(tier_key, []):
            status = get_player_status(player, injuries)
            mult = status_multiplier(status)
            if mult <= ABSENT_THRESHOLD:
                return True
    return False


def get_absent_stars(tiers: dict, injuries: list = None) -> list[AbsentStar]:
    """
    Get list of absent stars (OUT or DOUBTFUL).
    
    Args:
        tiers: Dict with "tier_a" and "tier_b" player lists
        injuries: Optional list of injury records
    
    Returns:
        List of AbsentStar objects
    """
    absent = []
    
    for tier_key, tier_name in [("tier_a", "A"), ("tier_b", "B")]:
        for player in tiers.get(tier_key, []):
            status = get_player_status(player, injuries)
            mult = status_multiplier(status)
            
            if mult <= ABSENT_THRESHOLD:
                name = getattr(player, 'player_name', 'Unknown')
                ppg = getattr(player, 'points_per_game', 0) or getattr(player, 'ppg', 0) or 0
                mpg = getattr(player, 'minutes_per_game', 0) or getattr(player, 'mpg', 32) or 32
                ppm = ppg / max(mpg, 1)
                
                absent.append(AbsentStar(
                    name=name,
                    tier=tier_name,
                    ppg=ppg,
                    mpg=mpg,
                    ppm=ppm,
                    status=status,
                ))
    
    return absent


def get_replacement_candidates(
    players: list,
    tiers: dict,
    injuries: list = None,
) -> list[ReplacementCandidate]:
    """
    Get replacement candidates (non-stars who can fill minutes).
    
    Candidates must:
    - Not be in Tier A or Tier B
    - Have status_multiplier >= 0.85 (PROBABLE or AVAILABLE)
    - Have MPG between 10 and 30 (if available)
    
    Args:
        players: All team players
        tiers: Team's star tiers
        injuries: Optional injury list
    
    Returns:
        List of top 3 ReplacementCandidate by MPG
    """
    # Get star player names to exclude
    star_names = set()
    for tier_key in ["tier_a", "tier_b"]:
        for player in tiers.get(tier_key, []):
            name = getattr(player, 'player_name', '') or getattr(player, 'name', '')
            star_names.add(name.lower())
    
    candidates = []
    
    for player in players:
        name = getattr(player, 'player_name', '') or getattr(player, 'name', '')
        
        # Skip stars
        if name.lower() in star_names:
            continue
        
        # Check availability
        status = get_player_status(player, injuries)
        mult = status_multiplier(status)
        if mult < 0.85:
            continue
        
        # Check MPG range
        mpg = getattr(player, 'minutes_per_game', None) or getattr(player, 'mpg', None)
        ppg = getattr(player, 'points_per_game', 0) or getattr(player, 'ppg', 0) or 0
        
        if mpg is None:
            # No MPG - include but use default
            mpg = 15.0
        elif mpg < MIN_REPLACEMENT_MPG or mpg > MAX_REPLACEMENT_MPG:
            continue
        
        # Calculate points per minute
        ppm = ppg / max(mpg, 1)
        
        candidates.append(ReplacementCandidate(
            name=name,
            ppg=ppg,
            mpg=mpg,
            ppm=ppm,
            status=status,
            quality_score=ppm,
        ))
    
    # Sort by MPG descending (more minutes = more impactful replacement)
    candidates.sort(key=lambda c: c.mpg, reverse=True)
    
    # Return top 3
    return candidates[:3]


def compute_team_replacement_quality(
    absent_stars: list[AbsentStar],
    candidates: list[ReplacementCandidate],
) -> tuple[float, float, float]:
    """
    Compute replacement quality metrics for a team.
    
    Args:
        absent_stars: List of absent star players
        candidates: List of replacement candidates
    
    Returns:
        Tuple of (out_star_quality, replacement_quality, delta)
    """
    # Calculate out star quality (weighted by MPG)
    if absent_stars:
        total_mpg = sum(s.mpg for s in absent_stars)
        out_star_quality = sum(s.ppm * s.mpg for s in absent_stars) / max(total_mpg, 1)
    else:
        out_star_quality = 0.0
    
    # Calculate replacement quality (weighted by MPG)
    if candidates:
        total_mpg = sum(c.mpg for c in candidates)
        replacement_quality = sum(c.ppm * c.mpg for c in candidates) / max(total_mpg, 1)
    else:
        replacement_quality = 0.0
    
    # Delta: positive means replacements are good, negative means they're worse
    delta = replacement_quality - out_star_quality
    
    return out_star_quality, replacement_quality, delta


def compute_rotation_replacement(
    home_players: list,
    away_players: list,
    home_tiers: dict,
    away_tiers: dict,
    home_injuries: list = None,
    away_injuries: list = None,
) -> tuple[float, dict]:
    """
    Compute the rotation replacement factor.
    
    This factor ONLY activates when a Tier A or Tier B star is OUT or DOUBTFUL.
    
    Args:
        home_players: Home team players
        away_players: Away team players
        home_tiers: Home team star tiers
        away_tiers: Away team star tiers
        home_injuries: Home team injuries
        away_injuries: Away team injuries
    
    Returns:
        Tuple of (edge_points, detail_dict)
    """
    # Check if any team has absent stars
    home_has_absent = star_absent(home_tiers, home_injuries)
    away_has_absent = star_absent(away_tiers, away_injuries)
    
    # Activation check
    if not home_has_absent and not away_has_absent:
        return 0.0, {
            "active": False,
            "reason": "No Tier A/B stars OUT or DOUBTFUL",
            "home_points": 0.0,
            "away_points": 0.0,
            "edge": 0.0,
        }
    
    # Get absent stars
    home_absent = get_absent_stars(home_tiers, home_injuries) if home_has_absent else []
    away_absent = get_absent_stars(away_tiers, away_injuries) if away_has_absent else []
    
    # Get replacement candidates
    home_candidates = get_replacement_candidates(home_players, home_tiers, home_injuries) if home_has_absent else []
    away_candidates = get_replacement_candidates(away_players, away_tiers, away_injuries) if away_has_absent else []
    
    # Compute replacement quality
    home_out_q, home_repl_q, home_delta = compute_team_replacement_quality(home_absent, home_candidates)
    away_out_q, away_repl_q, away_delta = compute_team_replacement_quality(away_absent, away_candidates)
    
    # Convert deltas to bounded points
    # Negative delta = worse replacements = negative points for that team
    # Scale by 10 and clamp to [-2, +1] per team
    home_points = max(-2.0, min(1.0, home_delta * 10.0)) if home_has_absent else 0.0
    away_points = max(-2.0, min(1.0, away_delta * 10.0)) if away_has_absent else 0.0
    
    # Edge: positive = home advantage
    raw_edge = home_points - away_points
    clamped_edge = max(-REPLACEMENT_EDGE_CLAMP, min(REPLACEMENT_EDGE_CLAMP, raw_edge))
    
    # Build trigger list
    triggers = []
    for star in home_absent:
        triggers.append(f"HOME {star.tier}: {star.name} ({star.status})")
    for star in away_absent:
        triggers.append(f"AWAY {star.tier}: {star.name} ({star.status})")
    
    return clamped_edge, {
        "active": True,
        "reason": f"Star absence detected: {', '.join(triggers)}",
        "triggers": triggers,
        "home_absent_stars": [
            {"name": s.name, "tier": s.tier, "ppm": s.ppm, "status": s.status}
            for s in home_absent
        ],
        "away_absent_stars": [
            {"name": s.name, "tier": s.tier, "ppm": s.ppm, "status": s.status}
            for s in away_absent
        ],
        "home_candidates": [
            {"name": c.name, "ppm": c.ppm, "mpg": c.mpg}
            for c in home_candidates
        ],
        "away_candidates": [
            {"name": c.name, "ppm": c.ppm, "mpg": c.mpg}
            for c in away_candidates
        ],
        "home_out_quality": round(home_out_q, 3),
        "home_replacement_quality": round(home_repl_q, 3),
        "home_delta": round(home_delta, 3),
        "home_points": round(home_points, 2),
        "away_out_quality": round(away_out_q, 3),
        "away_replacement_quality": round(away_repl_q, 3),
        "away_delta": round(away_delta, 3),
        "away_points": round(away_points, 2),
        "raw_edge": round(raw_edge, 2),
        "clamped_edge": round(clamped_edge, 2),
    }


def format_replacement_detail(detail: dict) -> str:
    """Format replacement detail for display."""
    if not detail.get("active"):
        return "INACTIVE (no star absences)"
    
    parts = []
    
    # Triggers
    triggers = detail.get("triggers", [])
    if triggers:
        parts.append(f"Triggers: {', '.join(triggers)}")
    
    # Home candidates
    home_cands = detail.get("home_candidates", [])
    if home_cands:
        cand_str = ", ".join([f"{c['name']}({c['ppm']:.2f})" for c in home_cands])
        parts.append(f"Home replacements: {cand_str}")
    
    # Away candidates
    away_cands = detail.get("away_candidates", [])
    if away_cands:
        cand_str = ", ".join([f"{c['name']}({c['ppm']:.2f})" for c in away_cands])
        parts.append(f"Away replacements: {cand_str}")
    
    # Edge
    parts.append(f"Edge: {detail.get('clamped_edge', 0):.1f}")
    
    return " | ".join(parts)
