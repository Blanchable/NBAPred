"""
Player projection engine for NBA games.

Provides stat projections (PTS/REB/AST/3PM) using:
- Season per-minute rates
- Projected minutes based on status
- Pace adjustment
- Optional opponent defense adjustment
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import sys
from pathlib import Path

# Add parent to path if needed
if __name__ != "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ProjectedPlayerLine:
    """Projected stat line for a player."""
    player_id: Optional[int]
    player_name: str
    team_abbrev: str
    status: str              # AVAILABLE/PROBABLE/QUESTIONABLE/DOUBTFUL/OUT/UNKNOWN
    tonight: str             # YES/MAYBE/NO
    proj_min: float
    proj_pts: float
    proj_reb: float
    proj_ast: float
    proj_3pm: float
    uncertainty: str         # LOW/MED/HIGH
    debug: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_playing(self) -> bool:
        """Check if player is likely to play."""
        return self.tonight in ("YES", "MAYBE") and self.proj_min > 0


# ============================================================================
# STATUS AND UNCERTAINTY HELPERS
# ============================================================================

def status_to_multiplier(status: str) -> float:
    """
    Convert injury status to minutes multiplier.
    
    Returns:
        Float from 0.0 to 1.0 representing likelihood/minutes adjustment
    """
    status_upper = status.upper().strip()
    
    multipliers = {
        "OUT": 0.0,
        "DOUBTFUL": 0.05,
        "QUESTIONABLE": 0.60,
        "PROBABLE": 0.90,
        "AVAILABLE": 1.00,
        "UNKNOWN": 0.95,
        "": 1.00,
    }
    
    return multipliers.get(status_upper, 0.95)


def uncertainty_from_status(status: str) -> str:
    """
    Classify uncertainty level based on injury status.
    
    Returns:
        "LOW", "MED", or "HIGH"
    """
    status_upper = status.upper().strip()
    
    if status_upper in ("OUT", "DOUBTFUL", "QUESTIONABLE"):
        return "HIGH"
    elif status_upper in ("UNKNOWN", "PROBABLE"):
        return "MED"
    else:
        return "LOW"


def tonight_from_status(status: str, team_plays: bool) -> str:
    """
    Determine if player plays tonight based on status.
    
    Args:
        status: Injury status string
        team_plays: Whether the team has a game
    
    Returns:
        "YES", "MAYBE", "NO", or "N/A"
    """
    if not team_plays:
        return "N/A"
    
    status_upper = status.upper().strip()
    
    if status_upper in ("OUT", "DOUBTFUL"):
        return "NO"
    elif status_upper == "QUESTIONABLE":
        return "MAYBE"
    else:
        return "YES"


# ============================================================================
# PACE AND DEFENSE FACTORS
# ============================================================================

LEAGUE_AVG_PACE = 99.0
LEAGUE_AVG_DEF_RATING = 114.0


def compute_pace_factor(team_pace: float, opp_pace: float) -> float:
    """
    Compute pace adjustment factor.
    
    Higher pace = more possessions = more stats.
    
    Args:
        team_pace: Team's pace (possessions per 48 min)
        opp_pace: Opponent's pace
    
    Returns:
        Multiplier, clamped to [0.90, 1.10]
    """
    if team_pace <= 0 or opp_pace <= 0:
        return 1.0
    
    game_pace = (team_pace + opp_pace) / 2.0
    raw = game_pace / LEAGUE_AVG_PACE
    
    return min(1.10, max(0.90, raw))


def compute_def_factor(opp_def_rating: float) -> float:
    """
    Compute opponent defense adjustment factor.
    
    Lower defensive rating = better defense = harder to score.
    
    Args:
        opp_def_rating: Opponent's defensive rating (pts allowed per 100 poss)
    
    Returns:
        Multiplier, clamped to [0.94, 1.06]
    """
    if opp_def_rating <= 0:
        return 1.0
    
    # Higher ratio = easier to score against this opponent
    raw = opp_def_rating / LEAGUE_AVG_DEF_RATING
    
    return min(1.06, max(0.94, raw))


# ============================================================================
# MINUTES AND RATE PROJECTIONS
# ============================================================================

def project_minutes(season_mpg: float, status: str) -> float:
    """
    Project minutes for a player based on season average and status.
    
    Args:
        season_mpg: Season minutes per game
        status: Injury status
    
    Returns:
        Projected minutes (0-36 range)
    """
    base = min(36.0, max(0.0, season_mpg))
    mult = status_to_multiplier(status)
    return base * mult


def compute_per_minute_rates(
    mpg: float,
    ppg: float,
    rpg: float,
    apg: float,
    tpm: float,
) -> Dict[str, float]:
    """
    Compute per-minute rates for each stat.
    
    Args:
        mpg: Minutes per game
        ppg: Points per game
        rpg: Rebounds per game
        apg: Assists per game
        tpm: Three-pointers made per game
    
    Returns:
        Dict with per-minute rates
    """
    if mpg <= 0:
        return {
            "pts_per_min": 0.0,
            "reb_per_min": 0.0,
            "ast_per_min": 0.0,
            "three_per_min": 0.0,
        }
    
    return {
        "pts_per_min": ppg / mpg,
        "reb_per_min": rpg / mpg,
        "ast_per_min": apg / mpg,
        "three_per_min": tpm / mpg,
    }


# ============================================================================
# PROJECTION MODES
# ============================================================================

class ProjectionMode:
    """Projection mode constants."""
    BASELINE = "Baseline"
    BASELINE_PACE = "Baseline + Pace"
    BASELINE_PACE_DEF = "Baseline + Pace + Defense"
    FULL = "Full"


def should_apply_pace(mode: str) -> bool:
    """Check if pace adjustment should be applied."""
    return mode in (ProjectionMode.BASELINE_PACE, ProjectionMode.BASELINE_PACE_DEF, ProjectionMode.FULL)


def should_apply_defense(mode: str) -> bool:
    """Check if defense adjustment should be applied."""
    return mode in (ProjectionMode.BASELINE_PACE_DEF, ProjectionMode.FULL)


# ============================================================================
# TEAM-LEVEL PROJECTIONS
# ============================================================================

def project_team_players(
    team_abbrev: str,
    opp_abbrev: str,
    roster_players: List[Any],  # List of RosterPlayer or player name strings
    player_stats_by_team: Dict[str, List[Any]],  # team -> List[PlayerImpact]
    injury_status_map: Dict[str, str],  # normalized_name -> status
    team_pace: float,
    opp_pace: float,
    opp_def_rating: float,
    mode: str,
    team_plays_tonight: bool = True,
) -> List[ProjectedPlayerLine]:
    """
    Project stats for all players on a team.
    
    Args:
        team_abbrev: Team abbreviation
        opp_abbrev: Opponent abbreviation
        roster_players: List of roster players or names
        player_stats_by_team: Dict of team -> PlayerImpact list
        injury_status_map: Dict of normalized name -> status for this team
        team_pace: Team's pace
        opp_pace: Opponent's pace
        opp_def_rating: Opponent's defensive rating
        mode: Projection mode
        team_plays_tonight: Whether team has a game
    
    Returns:
        List of ProjectedPlayerLine sorted by proj_pts desc
    """
    from ingest.availability import normalize_player_name
    
    # Build stats lookup by normalized name
    team_impacts = player_stats_by_team.get(team_abbrev, [])
    stats_map = {}
    for impact in team_impacts:
        name_norm = normalize_player_name(impact.player_name)
        stats_map[name_norm] = impact
    
    # Compute adjustment factors
    pace_factor = compute_pace_factor(team_pace, opp_pace) if should_apply_pace(mode) else 1.0
    def_factor = compute_def_factor(opp_def_rating) if should_apply_defense(mode) else 1.0
    
    projections = []
    
    for player in roster_players:
        # Handle both RosterPlayer objects and plain strings
        if hasattr(player, 'player_name'):
            player_name = player.player_name
            player_id = getattr(player, 'player_id', None)
        else:
            player_name = str(player)
            player_id = None
        
        name_norm = normalize_player_name(player_name)
        
        # Get stats
        impact = stats_map.get(name_norm)
        
        if impact:
            mpg = impact.minutes_per_game
            ppg = impact.points_per_game
            rpg = impact.rebounds_per_game
            apg = impact.assists_per_game
            tpm = impact.threes_made_per_game
            pid = impact.player_id if hasattr(impact, 'player_id') else player_id
        else:
            # No stats found - use defaults
            mpg = ppg = rpg = apg = tpm = 0.0
            pid = player_id
        
        # Get status
        status = injury_status_map.get(name_norm, "UNKNOWN")
        
        # Project minutes
        proj_min = project_minutes(mpg, status)
        
        # Compute per-minute rates
        rates = compute_per_minute_rates(mpg, ppg, rpg, apg, tpm)
        
        # Base projections
        base_pts = rates["pts_per_min"] * proj_min
        base_reb = rates["reb_per_min"] * proj_min
        base_ast = rates["ast_per_min"] * proj_min
        base_3pm = rates["three_per_min"] * proj_min
        
        # Apply pace factor (affects all stats)
        proj_pts = base_pts * pace_factor
        proj_reb = base_reb * pace_factor
        proj_ast = base_ast * pace_factor
        proj_3pm = base_3pm * pace_factor
        
        # Apply defense factor (only to scoring stats)
        proj_pts *= def_factor
        proj_3pm *= def_factor
        
        # Determine tonight status
        tonight = tonight_from_status(status, team_plays_tonight)
        
        # Determine uncertainty
        uncertainty = uncertainty_from_status(status)
        
        # Build debug info
        debug = {
            "season_mpg": mpg,
            "season_ppg": ppg,
            "season_rpg": rpg,
            "season_apg": apg,
            "season_3pm": tpm,
            "pace_factor": pace_factor,
            "def_factor": def_factor,
            "status_mult": status_to_multiplier(status),
            "mode": mode,
            "opponent": opp_abbrev,
        }
        
        projection = ProjectedPlayerLine(
            player_id=pid,
            player_name=player_name,
            team_abbrev=team_abbrev,
            status=status,
            tonight=tonight,
            proj_min=round(proj_min, 1),
            proj_pts=round(proj_pts, 1),
            proj_reb=round(proj_reb, 1),
            proj_ast=round(proj_ast, 1),
            proj_3pm=round(proj_3pm, 1),
            uncertainty=uncertainty,
            debug=debug,
        )
        projections.append(projection)
    
    # Sort by projected points descending
    projections.sort(key=lambda p: p.proj_pts, reverse=True)
    
    return projections


# ============================================================================
# GAME-LEVEL PROJECTIONS
# ============================================================================

def project_game(
    game: Any,  # schedule.Game object
    roster_home: List[Any],
    roster_away: List[Any],
    player_stats_by_team: Dict[str, List[Any]],
    injuries_by_team: Dict[str, Dict[str, str]],  # team -> (name_norm -> status)
    team_stats: Dict[str, Any],  # team -> TeamStrength
    mode: str,
) -> Dict[str, Any]:
    """
    Project stats for all players in a game.
    
    Args:
        game: Game object with home_team, away_team
        roster_home: Home team roster
        roster_away: Away team roster
        player_stats_by_team: Player stats dict
        injuries_by_team: Injury status by team
        team_stats: Team stats dict with pace, def_rating
        mode: Projection mode
    
    Returns:
        Dict with 'home', 'away', 'combined' projection lists and metadata
    """
    home_team = game.home_team
    away_team = game.away_team
    
    # Get team stats with defaults
    home_stats = team_stats.get(home_team)
    away_stats = team_stats.get(away_team)
    
    home_pace = getattr(home_stats, 'pace', LEAGUE_AVG_PACE) if home_stats else LEAGUE_AVG_PACE
    away_pace = getattr(away_stats, 'pace', LEAGUE_AVG_PACE) if away_stats else LEAGUE_AVG_PACE
    home_def = getattr(home_stats, 'def_rating', LEAGUE_AVG_DEF_RATING) if home_stats else LEAGUE_AVG_DEF_RATING
    away_def = getattr(away_stats, 'def_rating', LEAGUE_AVG_DEF_RATING) if away_stats else LEAGUE_AVG_DEF_RATING
    
    # Get injury maps
    home_injuries = injuries_by_team.get(home_team, {})
    away_injuries = injuries_by_team.get(away_team, {})
    
    # Project home team (facing away defense)
    home_projections = project_team_players(
        team_abbrev=home_team,
        opp_abbrev=away_team,
        roster_players=roster_home,
        player_stats_by_team=player_stats_by_team,
        injury_status_map=home_injuries,
        team_pace=home_pace,
        opp_pace=away_pace,
        opp_def_rating=away_def,
        mode=mode,
        team_plays_tonight=True,
    )
    
    # Project away team (facing home defense)
    away_projections = project_team_players(
        team_abbrev=away_team,
        opp_abbrev=home_team,
        roster_players=roster_away,
        player_stats_by_team=player_stats_by_team,
        injury_status_map=away_injuries,
        team_pace=away_pace,
        opp_pace=home_pace,
        opp_def_rating=home_def,
        mode=mode,
        team_plays_tonight=True,
    )
    
    # Combined list sorted by proj_pts
    combined = home_projections + away_projections
    combined.sort(key=lambda p: p.proj_pts, reverse=True)
    
    return {
        'home': home_projections,
        'away': away_projections,
        'combined': combined,
        'home_team': home_team,
        'away_team': away_team,
        'game': game,
    }


# ============================================================================
# SLATE-LEVEL PROJECTIONS
# ============================================================================

def project_slate(
    games: List[Any],
    rosters_by_team: Dict[str, List[Any]],
    player_stats_by_team: Dict[str, List[Any]],
    injuries_by_team: Dict[str, Dict[str, str]],
    team_stats: Dict[str, Any],
    mode: str,
    top_n: int = 100,
) -> List[ProjectedPlayerLine]:
    """
    Project stats for all players across today's slate.
    
    Args:
        games: List of Game objects
        rosters_by_team: Dict of team -> roster list
        player_stats_by_team: Player stats dict
        injuries_by_team: Injury status by team
        team_stats: Team stats dict
        mode: Projection mode
        top_n: Maximum number of players to return
    
    Returns:
        List of top projected players sorted by proj_pts
    """
    all_projections = []
    seen_players = set()  # (name_norm, team) to avoid duplicates
    
    from ingest.availability import normalize_player_name
    
    for game in games:
        result = project_game(
            game=game,
            roster_home=rosters_by_team.get(game.home_team, []),
            roster_away=rosters_by_team.get(game.away_team, []),
            player_stats_by_team=player_stats_by_team,
            injuries_by_team=injuries_by_team,
            team_stats=team_stats,
            mode=mode,
        )
        
        for proj in result['combined']:
            key = (normalize_player_name(proj.player_name), proj.team_abbrev)
            if key not in seen_players:
                seen_players.add(key)
                all_projections.append(proj)
    
    # Sort by projected points and return top N
    all_projections.sort(key=lambda p: p.proj_pts, reverse=True)
    
    return all_projections[:top_n]


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'ProjectedPlayerLine',
    'ProjectionMode',
    'status_to_multiplier',
    'uncertainty_from_status',
    'tonight_from_status',
    'compute_pace_factor',
    'compute_def_factor',
    'project_minutes',
    'compute_per_minute_rates',
    'project_team_players',
    'project_game',
    'project_slate',
]
