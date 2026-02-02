"""
V2 Point System for NBA Pregame Predictions.

Implements a 20-factor weighted scoring system that produces:
- Edge Score (signed, -100 to +100 range)
- Win probability (calibrated via logistic mapping)
- Factor-by-factor breakdown

Total weights sum to 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
from typing import Any, Optional
import re


# ============================================================================
# CONSTANTS AND WEIGHTS
# ============================================================================

# Factor weights (must sum to 100)
FACTOR_WEIGHTS = {
    "net_rating": 14,
    "star_availability": 12,
    "off_vs_def": 8,
    "turnover_diff": 6,
    "shot_quality": 6,
    "three_point_edge": 6,
    "free_throw_rate": 5,
    "rebounding": 5,
    "home_court": 5,
    "rest_fatigue": 5,
    "rim_protection": 4,
    "perimeter_defense": 4,
    "matchup_fit": 3,
    "bench_depth": 3,
    "pace_control": 3,
    "late_game_creation": 3,
    "coaching": 2,
    "foul_trouble_risk": 2,
    "shooting_variance": 2,
    "motivation": 2,
}

# Verify weights sum to 100
assert sum(FACTOR_WEIGHTS.values()) == 100, f"Weights sum to {sum(FACTOR_WEIGHTS.values())}, not 100"

# Factor display names
FACTOR_NAMES = {
    "net_rating": "Net Rating",
    "star_availability": "Star Availability",
    "off_vs_def": "Off vs Def Efficiency",
    "turnover_diff": "Turnover Differential",
    "shot_quality": "Shot Quality",
    "three_point_edge": "3P Edge",
    "free_throw_rate": "Free Throw Rate",
    "rebounding": "Rebounding",
    "home_court": "Home Court",
    "rest_fatigue": "Rest/Fatigue",
    "rim_protection": "Rim Protection",
    "perimeter_defense": "Perimeter Defense",
    "matchup_fit": "Matchup Fit",
    "bench_depth": "Bench Depth",
    "pace_control": "Pace Control",
    "late_game_creation": "Late Game Creation",
    "coaching": "Coaching",
    "foul_trouble_risk": "Foul Trouble Risk",
    "shooting_variance": "Shooting Variance",
    "motivation": "Motivation",
}

# Scaling constants for normalization
SCALES = {
    "net_rating": 10.0,
    "off_vs_def": 10.0,
    "turnover": 4.0,
    "shot_quality": 6.0,
    "three_point": 6.0,
    "ft_rate": 0.08,
    "rebounding": 6.0,
    "pace": 6.0,
    "bench": 5.0,
    "rest": 2.0,
    "rim": 6.0,
    "perimeter": 6.0,
    "availability": 0.25,
}

# Edge score to win probability scale
EDGE_SCALE = 12.0

# Edge score to margin mapping
MARGIN_SCALE = 6.0

# Injury status multipliers
INJURY_MULTIPLIERS = {
    "Out": 0.0,
    "Doubtful": 0.25,
    "Questionable": 0.6,
    "Probable": 0.85,
    "Available": 1.0,
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FactorResult:
    """Result for a single factor calculation."""
    name: str
    display_name: str
    weight: int
    signed_value: float  # [-1, +1]
    contribution: float  # weight * signed_value
    inputs_used: str  # Description of inputs


@dataclass
class GameScore:
    """Complete scoring result for a game."""
    away_team: str
    home_team: str
    edge_score_total: float
    home_win_prob: float
    away_win_prob: float
    projected_margin_home: float
    predicted_winner: str
    factors: list[FactorResult] = field(default_factory=list)
    
    @property
    def top_5_factors_str(self) -> str:
        """Get string of top 5 contributing factors."""
        sorted_factors = sorted(
            self.factors,
            key=lambda f: abs(f.contribution),
            reverse=True
        )[:5]
        
        parts = []
        for f in sorted_factors:
            sign = "+" if f.contribution >= 0 else ""
            parts.append(f"{f.display_name}:{sign}{f.contribution:.1f}")
        
        return ", ".join(parts)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def clamp(value: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
    """Clamp value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def safe_get(stats: dict, key: str, default: float = 0.0) -> float:
    """Safely get a numeric value from stats dict."""
    val = stats.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def edge_to_win_prob(edge_score: float, scale: float = EDGE_SCALE) -> float:
    """Convert edge score to win probability using logistic function."""
    return 1.0 / (1.0 + exp(-edge_score / scale))


def edge_to_margin(edge_score: float, scale: float = MARGIN_SCALE) -> float:
    """Convert edge score to projected point margin."""
    return edge_score / scale


# ============================================================================
# FACTOR CALCULATORS
# ============================================================================

def calc_net_rating(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 1: Net Rating (14 points)
    Overall team strength measured by point differential per 100 possessions.
    """
    home_net = safe_get(home_stats, "net_rating", 0.0)
    away_net = safe_get(away_stats, "net_rating", 0.0)
    
    delta = home_net - away_net
    signed_value = clamp(delta / SCALES["net_rating"])
    
    return FactorResult(
        name="net_rating",
        display_name=FACTOR_NAMES["net_rating"],
        weight=FACTOR_WEIGHTS["net_rating"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["net_rating"] * signed_value,
        inputs_used=f"Home:{home_net:+.1f} Away:{away_net:+.1f}",
    )


def calc_star_availability(
    home_team: str,
    away_team: str,
    injuries: list,
    player_stats: dict,
) -> FactorResult:
    """
    Factor 2: Star Availability and Health (13 points)
    Impact of injured players on team strength.
    """
    def get_team_availability(team: str) -> tuple[float, str]:
        """Calculate availability score for a team."""
        team_injuries = [i for i in injuries if i.team == team]
        
        # Get top players for team (from player_stats if available)
        team_players = player_stats.get(team, {})
        
        if not team_players:
            # No player data, check if any injuries exist
            if team_injuries:
                # Rough estimate: each Out player costs ~0.15 availability
                out_count = sum(1 for i in team_injuries if i.status == "Out")
                doubtful_count = sum(1 for i in team_injuries if i.status == "Doubtful")
                quest_count = sum(1 for i in team_injuries if i.status == "Questionable")
                
                penalty = out_count * 0.15 + doubtful_count * 0.10 + quest_count * 0.05
                avail = max(0.5, 1.0 - penalty)
                return avail, f"{len(team_injuries)} injuries"
            return 1.0, "No injury data"
        
        total_impact = 0.0
        available_impact = 0.0
        
        for player_name, pstats in team_players.items():
            impact = pstats.get("impact", 10.0)
            total_impact += impact
            
            # Check if this player is injured
            player_injury = None
            for inj in team_injuries:
                # Fuzzy match player name
                if _fuzzy_match_name(player_name, inj.player):
                    player_injury = inj
                    break
            
            if player_injury:
                mult = INJURY_MULTIPLIERS.get(player_injury.status, 1.0)
            else:
                mult = 1.0
            
            available_impact += impact * mult
        
        if total_impact > 0:
            avail = available_impact / total_impact
        else:
            avail = 1.0
        
        return avail, f"Impact: {available_impact:.1f}/{total_impact:.1f}"
    
    home_avail, home_inputs = get_team_availability(home_team)
    away_avail, away_inputs = get_team_availability(away_team)
    
    delta = home_avail - away_avail
    signed_value = clamp(delta / SCALES["availability"])
    
    return FactorResult(
        name="star_availability",
        display_name=FACTOR_NAMES["star_availability"],
        weight=FACTOR_WEIGHTS["star_availability"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["star_availability"] * signed_value,
        inputs_used=f"Home:{home_avail:.2f} ({home_inputs}) Away:{away_avail:.2f} ({away_inputs})",
    )


def _fuzzy_match_name(name1: str, name2: str) -> bool:
    """Check if two player names likely match."""
    # Normalize names
    def normalize(n):
        n = n.lower()
        n = re.sub(r"[^a-z\s]", "", n)
        return n.split()
    
    words1 = normalize(name1)
    words2 = normalize(name2)
    
    if not words1 or not words2:
        return False
    
    # Check if last names match
    if words1[-1] == words2[-1]:
        return True
    
    # Check if any significant word matches
    return bool(set(words1) & set(words2))


def calc_off_vs_def(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 3: Offensive Efficiency vs Opponent Defensive Efficiency (8 points)
    Matchup-specific scoring efficiency.
    """
    home_off = safe_get(home_stats, "off_rating", 110.0)
    home_def = safe_get(home_stats, "def_rating", 110.0)
    away_off = safe_get(away_stats, "off_rating", 110.0)
    away_def = safe_get(away_stats, "def_rating", 110.0)
    
    # Home edge: how much better home offense is vs away defense
    home_edge = home_off - away_def
    # Away edge: how much better away offense is vs home defense
    away_edge = away_off - home_def
    
    delta = home_edge - away_edge
    signed_value = clamp(delta / SCALES["off_vs_def"])
    
    return FactorResult(
        name="off_vs_def",
        display_name=FACTOR_NAMES["off_vs_def"],
        weight=FACTOR_WEIGHTS["off_vs_def"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["off_vs_def"] * signed_value,
        inputs_used=f"HomeOff:{home_off:.1f} AwayDef:{away_def:.1f} | AwayOff:{away_off:.1f} HomeDef:{home_def:.1f}",
    )


def calc_turnover_diff(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 4: Turnover Differential (7 points)
    Ball security advantage.
    """
    # Lower turnover rate is better
    home_tov = safe_get(home_stats, "tov_pct", 14.0)
    away_tov = safe_get(away_stats, "tov_pct", 14.0)
    
    # Positive = home takes care of ball better (lower TO rate)
    delta = away_tov - home_tov
    signed_value = clamp(delta / SCALES["turnover"])
    
    return FactorResult(
        name="turnover_diff",
        display_name=FACTOR_NAMES["turnover_diff"],
        weight=FACTOR_WEIGHTS["turnover_diff"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["turnover_diff"] * signed_value,
        inputs_used=f"HomeTOV%:{home_tov:.1f} AwayTOV%:{away_tov:.1f}",
    )


def calc_shot_quality(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 5: Shot Quality Advantage (7 points)
    Effective field goal percentage and shot selection.
    """
    home_efg = safe_get(home_stats, "efg_pct", 0.52)
    away_efg = safe_get(away_stats, "efg_pct", 0.52)
    
    delta = (home_efg - away_efg) * 100  # Convert to percentage points
    signed_value = clamp(delta / SCALES["shot_quality"])
    
    return FactorResult(
        name="shot_quality",
        display_name=FACTOR_NAMES["shot_quality"],
        weight=FACTOR_WEIGHTS["shot_quality"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["shot_quality"] * signed_value,
        inputs_used=f"HomeEFG:{home_efg:.3f} AwayEFG:{away_efg:.3f}",
    )


def calc_three_point_edge(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 6: 3P Volume and Accuracy Edge (7 points)
    Three-point shooting advantage.
    """
    home_3p_pct = safe_get(home_stats, "fg3_pct", 0.36)
    away_3p_pct = safe_get(away_stats, "fg3_pct", 0.36)
    home_3p_rate = safe_get(home_stats, "fg3a_rate", 0.40)
    away_3p_rate = safe_get(away_stats, "fg3a_rate", 0.40)
    
    # Combined score: accuracy + volume
    home_score = home_3p_pct * 100 + home_3p_rate * 20
    away_score = away_3p_pct * 100 + away_3p_rate * 20
    
    delta = home_score - away_score
    signed_value = clamp(delta / SCALES["three_point"])
    
    return FactorResult(
        name="three_point_edge",
        display_name=FACTOR_NAMES["three_point_edge"],
        weight=FACTOR_WEIGHTS["three_point_edge"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["three_point_edge"] * signed_value,
        inputs_used=f"Home3P%:{home_3p_pct:.3f} Away3P%:{away_3p_pct:.3f}",
    )


def calc_free_throw_rate(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 7: Free Throw Rate Differential (6 points)
    Ability to get to the free throw line.
    """
    home_ftr = safe_get(home_stats, "ft_rate", 0.25)
    away_ftr = safe_get(away_stats, "ft_rate", 0.25)
    
    delta = home_ftr - away_ftr
    signed_value = clamp(delta / SCALES["ft_rate"])
    
    return FactorResult(
        name="free_throw_rate",
        display_name=FACTOR_NAMES["free_throw_rate"],
        weight=FACTOR_WEIGHTS["free_throw_rate"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["free_throw_rate"] * signed_value,
        inputs_used=f"HomeFTr:{home_ftr:.3f} AwayFTr:{away_ftr:.3f}",
    )


def calc_rebounding(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 8: Rebounding Edge (6 points)
    Overall rebounding advantage.
    """
    home_reb = safe_get(home_stats, "reb_pct", 50.0)
    away_reb = safe_get(away_stats, "reb_pct", 50.0)
    
    delta = home_reb - away_reb
    signed_value = clamp(delta / SCALES["rebounding"])
    
    return FactorResult(
        name="rebounding",
        display_name=FACTOR_NAMES["rebounding"],
        weight=FACTOR_WEIGHTS["rebounding"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rebounding"] * signed_value,
        inputs_used=f"HomeREB%:{home_reb:.1f} AwayREB%:{away_reb:.1f}",
    )


def calc_home_court() -> FactorResult:
    """
    Factor 9: Home Court Advantage (5 points)
    Always +1 for home team perspective.
    """
    return FactorResult(
        name="home_court",
        display_name=FACTOR_NAMES["home_court"],
        weight=FACTOR_WEIGHTS["home_court"],
        signed_value=1.0,
        contribution=FACTOR_WEIGHTS["home_court"] * 1.0,
        inputs_used="Home team always +1",
    )


def calc_rest_fatigue(
    home_rest_days: int,
    away_rest_days: int,
) -> FactorResult:
    """
    Factor 10: Rest and Fatigue (5 points)
    Days since last game advantage.
    """
    delta = home_rest_days - away_rest_days
    signed_value = clamp(delta / SCALES["rest"])
    
    return FactorResult(
        name="rest_fatigue",
        display_name=FACTOR_NAMES["rest_fatigue"],
        weight=FACTOR_WEIGHTS["rest_fatigue"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rest_fatigue"] * signed_value,
        inputs_used=f"HomeRest:{home_rest_days}d AwayRest:{away_rest_days}d",
    )


def calc_rim_protection(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 11: Rim Protection vs Rim Pressure (4 points)
    Interior defense and scoring.
    """
    # Proxy using defensive rating and opponent FTr
    home_def = safe_get(home_stats, "def_rating", 110.0)
    away_def = safe_get(away_stats, "def_rating", 110.0)
    
    # Lower defensive rating = better rim protection
    delta = away_def - home_def
    signed_value = clamp(delta / SCALES["rim"])
    
    return FactorResult(
        name="rim_protection",
        display_name=FACTOR_NAMES["rim_protection"],
        weight=FACTOR_WEIGHTS["rim_protection"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["rim_protection"] * signed_value,
        inputs_used=f"HomeDEF:{home_def:.1f} AwayDEF:{away_def:.1f} (proxy)",
    )


def calc_perimeter_defense(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 12: Perimeter Defense / POA Containment (4 points)
    Opponent 3P% allowed as proxy.
    """
    home_opp_3p = safe_get(home_stats, "opp_fg3_pct", 0.36)
    away_opp_3p = safe_get(away_stats, "opp_fg3_pct", 0.36)
    
    # Lower opp 3P% = better perimeter defense
    delta = (away_opp_3p - home_opp_3p) * 100
    signed_value = clamp(delta / SCALES["perimeter"])
    
    return FactorResult(
        name="perimeter_defense",
        display_name=FACTOR_NAMES["perimeter_defense"],
        weight=FACTOR_WEIGHTS["perimeter_defense"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["perimeter_defense"] * signed_value,
        inputs_used=f"HomeOpp3P%:{home_opp_3p:.3f} AwayOpp3P%:{away_opp_3p:.3f}",
    )


def calc_matchup_fit(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 13: Matchup Fit / Lineup Compatibility (4 points)
    Style matchup using rebounding and 3P rate as proxy.
    """
    # v1: Use rebounding rate vs opponent 3P rate as style indicator
    home_reb = safe_get(home_stats, "reb_pct", 50.0)
    away_3p_rate = safe_get(away_stats, "fg3a_rate", 0.40)
    away_reb = safe_get(away_stats, "reb_pct", 50.0)
    home_3p_rate = safe_get(home_stats, "fg3a_rate", 0.40)
    
    # Teams with good rebounding match well against high-3P teams (more misses)
    home_matchup = home_reb * away_3p_rate
    away_matchup = away_reb * home_3p_rate
    
    delta = home_matchup - away_matchup
    signed_value = clamp(delta / 4.0)  # Small scale
    
    return FactorResult(
        name="matchup_fit",
        display_name=FACTOR_NAMES["matchup_fit"],
        weight=FACTOR_WEIGHTS["matchup_fit"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["matchup_fit"] * signed_value,
        inputs_used=f"Style proxy - REB vs 3PAr",
    )


def calc_bench_depth(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 14: Bench Depth / Rotation Quality (4 points)
    Proxy using team depth indicators.
    """
    # v1: Use net rating as proxy (better teams generally have better benches)
    home_net = safe_get(home_stats, "net_rating", 0.0)
    away_net = safe_get(away_stats, "net_rating", 0.0)
    
    # Scale down since this overlaps with net rating factor
    delta = (home_net - away_net) * 0.3
    signed_value = clamp(delta / SCALES["bench"])
    
    return FactorResult(
        name="bench_depth",
        display_name=FACTOR_NAMES["bench_depth"],
        weight=FACTOR_WEIGHTS["bench_depth"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["bench_depth"] * signed_value,
        inputs_used=f"Net rating proxy (scaled)",
    )


def calc_pace_control(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 15: Pace Control (3 points)
    Ability to dictate game tempo.
    """
    home_pace = safe_get(home_stats, "pace", 100.0)
    away_pace = safe_get(away_stats, "pace", 100.0)
    
    delta = home_pace - away_pace
    signed_value = clamp(delta / SCALES["pace"])
    
    return FactorResult(
        name="pace_control",
        display_name=FACTOR_NAMES["pace_control"],
        weight=FACTOR_WEIGHTS["pace_control"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["pace_control"] * signed_value,
        inputs_used=f"HomePace:{home_pace:.1f} AwayPace:{away_pace:.1f}",
    )


def calc_late_game_creation(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 16: Late-Game Shot Creation (3 points)
    Clutch performance proxy.
    """
    # v1: Use offensive rating as proxy
    home_off = safe_get(home_stats, "off_rating", 110.0)
    away_off = safe_get(away_stats, "off_rating", 110.0)
    
    delta = (home_off - away_off) * 0.5
    signed_value = clamp(delta / 5.0)
    
    return FactorResult(
        name="late_game_creation",
        display_name=FACTOR_NAMES["late_game_creation"],
        weight=FACTOR_WEIGHTS["late_game_creation"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["late_game_creation"] * signed_value,
        inputs_used=f"Off rating proxy",
    )


def calc_coaching() -> FactorResult:
    """
    Factor 17: Coaching / Adjustments (3 points)
    Not directly measurable - neutral in v1.
    """
    return FactorResult(
        name="coaching",
        display_name=FACTOR_NAMES["coaching"],
        weight=FACTOR_WEIGHTS["coaching"],
        signed_value=0.0,
        contribution=0.0,
        inputs_used="Neutral (no data in v1)",
    )


def calc_foul_trouble_risk(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 18: Foul Trouble Risk for Key Players (2 points)
    Team foul rate proxy.
    """
    home_pf = safe_get(home_stats, "pf_per_game", 20.0)
    away_pf = safe_get(away_stats, "pf_per_game", 20.0)
    
    # Lower fouls = less risk = advantage
    delta = away_pf - home_pf
    signed_value = clamp(delta / 4.0)
    
    return FactorResult(
        name="foul_trouble_risk",
        display_name=FACTOR_NAMES["foul_trouble_risk"],
        weight=FACTOR_WEIGHTS["foul_trouble_risk"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["foul_trouble_risk"] * signed_value,
        inputs_used=f"HomePF:{home_pf:.1f} AwayPF:{away_pf:.1f}",
    )


def calc_shooting_variance(
    home_stats: dict,
    away_stats: dict,
) -> FactorResult:
    """
    Factor 19: Shooting Variance Profile (2 points)
    Higher 3PAr = more variance. Conservative advantage to less volatile team.
    """
    home_3p_rate = safe_get(home_stats, "fg3a_rate", 0.40)
    away_3p_rate = safe_get(away_stats, "fg3a_rate", 0.40)
    
    # Positive = home is less volatile (advantage)
    delta = away_3p_rate - home_3p_rate
    signed_value = clamp(delta / 0.10)
    
    return FactorResult(
        name="shooting_variance",
        display_name=FACTOR_NAMES["shooting_variance"],
        weight=FACTOR_WEIGHTS["shooting_variance"],
        signed_value=signed_value,
        contribution=FACTOR_WEIGHTS["shooting_variance"] * signed_value,
        inputs_used=f"Home3PAr:{home_3p_rate:.3f} Away3PAr:{away_3p_rate:.3f}",
    )


def calc_motivation() -> FactorResult:
    """
    Factor 20: Motivation / Situational Context (1 point)
    Hard to automate - neutral in v1.
    """
    return FactorResult(
        name="motivation",
        display_name=FACTOR_NAMES["motivation"],
        weight=FACTOR_WEIGHTS["motivation"],
        signed_value=0.0,
        contribution=0.0,
        inputs_used="Neutral (no data in v1)",
    )


# ============================================================================
# MAIN SCORING FUNCTION
# ============================================================================

def score_game(
    home_team: str,
    away_team: str,
    team_stats: dict[str, dict],
    injuries: list = None,
    player_stats: dict = None,
    home_rest_days: int = 1,
    away_rest_days: int = 1,
) -> GameScore:
    """
    Score a game using the 20-factor weighted point system.
    
    Args:
        home_team: Home team abbreviation.
        away_team: Away team abbreviation.
        team_stats: Dict mapping team abbrev to stats dict.
        injuries: List of InjuryRow objects.
        player_stats: Dict mapping team abbrev to player stats.
        home_rest_days: Days since home team's last game.
        away_rest_days: Days since away team's last game.
    
    Returns:
        GameScore object with all scoring details.
    """
    injuries = injuries or []
    player_stats = player_stats or {}
    
    home_stats = team_stats.get(home_team, {})
    away_stats = team_stats.get(away_team, {})
    
    factors = []
    
    # Calculate all 20 factors
    factors.append(calc_net_rating(home_stats, away_stats))
    factors.append(calc_star_availability(home_team, away_team, injuries, player_stats))
    factors.append(calc_off_vs_def(home_stats, away_stats))
    factors.append(calc_turnover_diff(home_stats, away_stats))
    factors.append(calc_shot_quality(home_stats, away_stats))
    factors.append(calc_three_point_edge(home_stats, away_stats))
    factors.append(calc_free_throw_rate(home_stats, away_stats))
    factors.append(calc_rebounding(home_stats, away_stats))
    factors.append(calc_home_court())
    factors.append(calc_rest_fatigue(home_rest_days, away_rest_days))
    factors.append(calc_rim_protection(home_stats, away_stats))
    factors.append(calc_perimeter_defense(home_stats, away_stats))
    factors.append(calc_matchup_fit(home_stats, away_stats))
    factors.append(calc_bench_depth(home_stats, away_stats))
    factors.append(calc_pace_control(home_stats, away_stats))
    factors.append(calc_late_game_creation(home_stats, away_stats))
    factors.append(calc_coaching())
    factors.append(calc_foul_trouble_risk(home_stats, away_stats))
    factors.append(calc_shooting_variance(home_stats, away_stats))
    factors.append(calc_motivation())
    
    # Sum contributions
    edge_score_total = sum(f.contribution for f in factors)
    
    # Convert to probabilities
    home_win_prob = edge_to_win_prob(edge_score_total)
    away_win_prob = 1.0 - home_win_prob
    
    # Convert to margin
    projected_margin = edge_to_margin(edge_score_total)
    
    # Determine predicted winner
    if home_win_prob > 0.5:
        predicted_winner = home_team
    else:
        predicted_winner = away_team
    
    return GameScore(
        away_team=away_team,
        home_team=home_team,
        edge_score_total=round(edge_score_total, 2),
        home_win_prob=round(home_win_prob, 4),
        away_win_prob=round(away_win_prob, 4),
        projected_margin_home=round(projected_margin, 2),
        predicted_winner=predicted_winner,
        factors=factors,
    )


def validate_system():
    """Validate that the point system is correctly configured."""
    errors = []
    
    # Check weights sum to 100
    total = sum(FACTOR_WEIGHTS.values())
    if total != 100:
        errors.append(f"Weights sum to {total}, not 100")
    
    # Check all factors have names
    for key in FACTOR_WEIGHTS:
        if key not in FACTOR_NAMES:
            errors.append(f"Missing display name for factor: {key}")
    
    return errors
