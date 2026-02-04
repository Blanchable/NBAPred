"""
Star Impact Points module for NBA Prediction Engine.

Implements a tiered Star Impact system that:
- Categorizes players into Tier A (top star) and Tier B (secondary stars)
- Applies status multipliers based on injury/availability
- Provides bounded, normalized edge contributions
- Includes dampening for double-count protection when injuries are already reflected in stats
"""

from dataclasses import dataclass
from typing import Optional
import warnings


# Tier point values
TIER_A_POINTS = 4.0
TIER_B_POINTS = 2.0

# Edge clamp limits
STAR_EDGE_CLAMP = 6.0

# Minimum MPG to be considered rotation player
MIN_ROTATION_MPG = 20.0


@dataclass
class StarDetail:
    """Details about a star player for debugging/display."""
    name: str
    tier: str  # "A" or "B"
    ppg: float
    apg: float
    mpg: float
    impact: float
    status: str
    multiplier: float
    points: float


def status_multiplier(status: Optional[str]) -> float:
    """
    Get the availability multiplier for a player status.
    
    Args:
        status: Player status string (case-insensitive)
    
    Returns:
        Multiplier between 0.0 and 1.0
    """
    if status is None:
        return 1.0
    
    status_lower = status.lower().strip()
    
    # OUT statuses
    if status_lower in ["out", "o", "inactive", "dnp"]:
        return 0.0
    
    # DOUBTFUL
    if status_lower in ["doubtful", "d", "unlikely"]:
        return 0.25
    
    # QUESTIONABLE
    if status_lower in ["questionable", "q", "gtd", "game time decision", "day-to-day"]:
        return 0.60
    
    # PROBABLE
    if status_lower in ["probable", "p", "likely"]:
        return 0.85
    
    # AVAILABLE
    if status_lower in ["available", "active", "healthy", ""]:
        return 1.0
    
    # Unknown status - warn once and return 1.0
    warnings.warn(f"Unknown player status '{status}', treating as available", UserWarning)
    return 1.0


def impact_metric(player) -> float:
    """
    Calculate impact metric for a player.
    
    Impact = PPG + 0.7 * APG (if APG exists)
    
    Args:
        player: Player object with ppg, apg (optional), mpg attributes
    
    Returns:
        Impact score
    """
    ppg = getattr(player, 'points_per_game', 0) or getattr(player, 'ppg', 0) or 0
    apg = getattr(player, 'assists_per_game', 0) or getattr(player, 'apg', 0) or 0
    
    if ppg == 0:
        # Try alternate attribute names
        ppg = getattr(player, 'pts', 0) or 0
        if ppg == 0:
            warnings.warn(f"Player {getattr(player, 'player_name', 'unknown')} has no PPG data", UserWarning)
    
    return ppg + 0.7 * apg


def select_star_tiers(players: list) -> dict:
    """
    Select star tiers from a list of players.
    
    - Tier A: Top 1 player by impact
    - Tier B: Next 2 players by impact
    
    Only considers rotation candidates (MPG >= 20 or no MPG data).
    
    Args:
        players: List of player objects
    
    Returns:
        Dict with "tier_a" (list of 1) and "tier_b" (list of up to 2)
    """
    if not players:
        return {"tier_a": [], "tier_b": []}
    
    # Filter to rotation candidates
    rotation_candidates = []
    for p in players:
        mpg = getattr(p, 'minutes_per_game', None) or getattr(p, 'mpg', None)
        if mpg is None:
            # No MPG data - include but note
            rotation_candidates.append(p)
        elif mpg >= MIN_ROTATION_MPG:
            rotation_candidates.append(p)
    
    if not rotation_candidates:
        # Fallback: use all players if none meet MPG threshold
        rotation_candidates = players
    
    # Sort by impact metric descending
    sorted_players = sorted(rotation_candidates, key=impact_metric, reverse=True)
    
    # Select tiers
    tier_a = sorted_players[:1] if sorted_players else []
    tier_b = sorted_players[1:3] if len(sorted_players) > 1 else []
    
    return {"tier_a": tier_a, "tier_b": tier_b}


def get_player_status(player, injuries: list = None) -> str:
    """
    Get player's current status from player object or injuries list.
    
    Args:
        player: Player object
        injuries: Optional list of injury records
    
    Returns:
        Status string
    """
    # Check player object first
    status = getattr(player, 'status', None)
    if status:
        return status
    
    # Check injuries list if provided
    if injuries:
        player_name = getattr(player, 'player_name', '') or getattr(player, 'name', '')
        player_name_lower = player_name.lower()
        
        for inj in injuries:
            inj_player = getattr(inj, 'player', '') or ''
            if player_name_lower in inj_player.lower() or inj_player.lower() in player_name_lower:
                return getattr(inj, 'status', 'Available')
    
    return "Available"


def team_star_points(players: list, injuries: list = None) -> tuple[float, list[StarDetail]]:
    """
    Calculate star points for a team.
    
    Tier A = 4.0 points * status_multiplier
    Tier B = 2.0 points each * status_multiplier
    
    Args:
        players: List of player objects for the team
        injuries: Optional list of injury records
    
    Returns:
        Tuple of (total_points, list of StarDetail for debugging)
    """
    tiers = select_star_tiers(players)
    
    total_points = 0.0
    details = []
    
    # Process Tier A
    for player in tiers["tier_a"]:
        name = getattr(player, 'player_name', 'Unknown')
        ppg = getattr(player, 'points_per_game', 0) or getattr(player, 'ppg', 0) or 0
        apg = getattr(player, 'assists_per_game', 0) or getattr(player, 'apg', 0) or 0
        mpg = getattr(player, 'minutes_per_game', 0) or getattr(player, 'mpg', 0) or 0
        impact = impact_metric(player)
        status = get_player_status(player, injuries)
        mult = status_multiplier(status)
        points = TIER_A_POINTS * mult
        total_points += points
        
        details.append(StarDetail(
            name=name,
            tier="A",
            ppg=ppg,
            apg=apg,
            mpg=mpg,
            impact=impact,
            status=status,
            multiplier=mult,
            points=points,
        ))
    
    # Process Tier B
    for player in tiers["tier_b"]:
        name = getattr(player, 'player_name', 'Unknown')
        ppg = getattr(player, 'points_per_game', 0) or getattr(player, 'ppg', 0) or 0
        apg = getattr(player, 'assists_per_game', 0) or getattr(player, 'apg', 0) or 0
        mpg = getattr(player, 'minutes_per_game', 0) or getattr(player, 'mpg', 0) or 0
        impact = impact_metric(player)
        status = get_player_status(player, injuries)
        mult = status_multiplier(status)
        points = TIER_B_POINTS * mult
        total_points += points
        
        details.append(StarDetail(
            name=name,
            tier="B",
            ppg=ppg,
            apg=apg,
            mpg=mpg,
            impact=impact,
            status=status,
            multiplier=mult,
            points=points,
        ))
    
    return total_points, details


def star_edge_points(
    home_players: list,
    away_players: list,
    home_injuries: list = None,
    away_injuries: list = None,
) -> tuple[float, dict]:
    """
    Calculate star edge points (home - away) with clamping.
    
    Args:
        home_players: List of home team players
        away_players: List of away team players
        home_injuries: Optional home team injuries
        away_injuries: Optional away team injuries
    
    Returns:
        Tuple of (clamped_edge, detail_dict)
    """
    home_pts, home_details = team_star_points(home_players, home_injuries)
    away_pts, away_details = team_star_points(away_players, away_injuries)
    
    raw_edge = home_pts - away_pts
    clamped_edge = max(-STAR_EDGE_CLAMP, min(STAR_EDGE_CLAMP, raw_edge))
    
    return clamped_edge, {
        "home_points": home_pts,
        "away_points": away_pts,
        "raw_edge": raw_edge,
        "clamped_edge": clamped_edge,
        "home_stars": home_details,
        "away_stars": away_details,
    }


def dampened_star_edge(
    edge_points: float,
    context: dict = None,
    home_tiers: dict = None,
    away_tiers: dict = None,
) -> tuple[float, dict]:
    """
    Apply dampening to star edge to prevent double-counting.
    
    If injury is already reflected in lineup/efficiency stats, we dampen
    the star impact factor to avoid counting it twice.
    
    Dampening rules:
    - If lineup_games_used <= 10: multiplier = 0.35 (stats don't reflect injury yet)
    - If lineup_games_used > 10: multiplier = 1.00 (stats already reflect injury)
    - Default (no context): multiplier = 0.60
    
    Args:
        edge_points: Raw star edge points
        context: Optional context dict with 'lineup_games_used' or 'status_changed_recently'
        home_tiers: Home team tier dict (for potential status history check)
        away_tiers: Away team tier dict
    
    Returns:
        Tuple of (dampened_edge, detail_dict)
    """
    if context is None:
        context = {}
    
    # Check for status change (preferred method)
    if context.get('status_changed_recently') is not None:
        if context['status_changed_recently']:
            multiplier = 1.0
            reason = "Recent status change detected"
        else:
            multiplier = 0.35
            reason = "No recent status change, stats likely reflect injury"
    # Fallback: use lineup sample size
    elif context.get('lineup_games_used') is not None:
        games_used = context['lineup_games_used']
        if games_used <= 10:
            multiplier = 1.0
            reason = f"Small sample ({games_used} games), injury may be new info"
        else:
            multiplier = 0.35
            reason = f"Large sample ({games_used} games), stats likely reflect injury"
    else:
        # Default moderate dampening
        multiplier = 0.60
        reason = "No context available, using moderate dampening"
    
    dampened = edge_points * multiplier
    
    return dampened, {
        "multiplier": multiplier,
        "reason": reason,
        "original_edge": edge_points,
        "dampened_edge": dampened,
    }


def compute_star_factor(
    home_players: list,
    away_players: list,
    home_injuries: list = None,
    away_injuries: list = None,
    context: dict = None,
) -> tuple[float, float, dict]:
    """
    Complete star factor computation.
    
    Returns normalized signed value [-1, +1] and raw edge points.
    
    Args:
        home_players: Home team players
        away_players: Away team players
        home_injuries: Home team injuries
        away_injuries: Away team injuries
        context: Optional context for dampening
    
    Returns:
        Tuple of (signed_value, contribution, detail_dict)
    """
    # Get tiers for both teams
    home_tiers = select_star_tiers(home_players)
    away_tiers = select_star_tiers(away_players)
    
    # Calculate edge points
    edge_points, edge_detail = star_edge_points(
        home_players, away_players,
        home_injuries, away_injuries,
    )
    
    # Apply dampening
    dampened_edge, damp_detail = dampened_star_edge(
        edge_points, context, home_tiers, away_tiers
    )
    
    # Normalize to [-1, +1]
    signed_value = dampened_edge / STAR_EDGE_CLAMP
    signed_value = max(-1.0, min(1.0, signed_value))
    
    return signed_value, dampened_edge, {
        **edge_detail,
        "dampening": damp_detail,
        "home_tiers": home_tiers,
        "away_tiers": away_tiers,
        "signed_value": signed_value,
    }


def format_star_detail(detail: dict) -> str:
    """Format star detail for display."""
    parts = []
    
    # Home stars
    home_stars = detail.get("home_stars", [])
    if home_stars:
        home_str = ", ".join([
            f"{s.name}({s.tier}:{s.status}={s.multiplier:.0%})"
            for s in home_stars
        ])
        parts.append(f"Home: {home_str}")
    
    # Away stars
    away_stars = detail.get("away_stars", [])
    if away_stars:
        away_str = ", ".join([
            f"{s.name}({s.tier}:{s.status}={s.multiplier:.0%})"
            for s in away_stars
        ])
        parts.append(f"Away: {away_str}")
    
    # Edge info
    parts.append(f"Edge: {detail.get('dampened_edge', 0):.1f} (raw {detail.get('raw_edge', 0):.1f})")
    
    # Dampening
    damp = detail.get("dampening", {})
    if damp:
        parts.append(f"Damp: {damp.get('multiplier', 1):.0%}")
    
    return " | ".join(parts)
