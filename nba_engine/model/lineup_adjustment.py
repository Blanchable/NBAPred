"""
Lineup adjustment module for v3 predictions.

Adjusts team strength based on who is actually playing tonight.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LineupAdjustedStrength:
    """Team strength adjusted for tonight's lineup."""
    team: str
    base_net_rating: float
    availability_score: float  # 0-1, percentage of strength available
    adjusted_net_rating: float
    missing_players: list[str]
    confidence_penalty: float  # Uncertainty due to injuries
    
    def to_dict(self) -> dict:
        return {
            'team': self.team,
            'base_net_rating': self.base_net_rating,
            'availability_score': self.availability_score,
            'adjusted_net_rating': self.adjusted_net_rating,
            'missing_players': self.missing_players,
            'confidence_penalty': self.confidence_penalty,
        }


def calculate_lineup_adjusted_strength(
    team: str,
    team_strength,  # TeamStrength object
    players: list,  # List of PlayerImpact
    injuries: list,  # List of InjuryRow
    is_home: bool = True,
) -> LineupAdjustedStrength:
    """
    Calculate lineup-adjusted team strength.
    
    Args:
        team: Team abbreviation.
        team_strength: TeamStrength object with base ratings.
        players: List of PlayerImpact for the team.
        injuries: List of all InjuryRow objects.
        is_home: Whether this is the home team.
    
    Returns:
        LineupAdjustedStrength object.
    """
    # Injury status multipliers
    MULTIPLIERS = {
        "Out": 0.0,
        "Doubtful": 0.25,
        "Questionable": 0.6,
        "Probable": 0.85,
        "Available": 1.0,
    }
    
    # Get base rating (use home or road split)
    if is_home:
        base_rating = getattr(team_strength, 'home_net_rating', team_strength.net_rating)
    else:
        base_rating = getattr(team_strength, 'road_net_rating', team_strength.net_rating)
    
    # Use blended rating if available
    blended = getattr(team_strength, 'blended_net_rating', None)
    if blended is not None and blended != 0:
        # Average base with blended
        base_rating = (base_rating + blended) / 2
    
    # Get team injuries
    team_injuries = {}
    for inj in injuries:
        if inj.team == team:
            team_injuries[_normalize_name(inj.player)] = inj.status
    
    # Calculate availability
    total_impact = 0.0
    available_impact = 0.0
    missing_players = []
    
    key_players = [p for p in players if p.is_key_player]
    
    if not key_players:
        # No player data, use default
        return LineupAdjustedStrength(
            team=team,
            base_net_rating=base_rating,
            availability_score=1.0,
            adjusted_net_rating=base_rating,
            missing_players=[],
            confidence_penalty=0.0,
        )
    
    for player in key_players:
        impact = player.impact_score
        total_impact += impact
        
        # Check if injured
        player_norm = _normalize_name(player.player_name)
        status = None
        
        for inj_name, inj_status in team_injuries.items():
            if _names_match(player_norm, inj_name):
                status = inj_status
                break
        
        if status and status in ["Out", "Doubtful"]:
            missing_players.append(f"{player.player_name} ({status})")
        
        mult = MULTIPLIERS.get(status, 1.0) if status else 1.0
        available_impact += impact * mult
    
    # Calculate availability score
    if total_impact > 0:
        availability = available_impact / total_impact
    else:
        availability = 1.0
    
    # Adjust net rating based on availability
    # Missing players reduces team strength proportionally
    # But cap the penalty to avoid extreme swings
    availability_penalty = (1 - availability) * 10  # Max ~10 point swing
    availability_penalty = min(availability_penalty, 8)  # Cap at 8 points
    
    adjusted_rating = base_rating - availability_penalty
    
    # Confidence penalty (uncertainty from injuries)
    # More questionable players = less confident prediction
    questionable_count = sum(1 for s in team_injuries.values() if s in ["Questionable", "Doubtful"])
    confidence_penalty = questionable_count * 0.1  # 0.1 per questionable player
    
    return LineupAdjustedStrength(
        team=team,
        base_net_rating=base_rating,
        availability_score=availability,
        adjusted_net_rating=adjusted_rating,
        missing_players=missing_players,
        confidence_penalty=confidence_penalty,
    )


def _normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    import re
    name = name.lower()
    name = re.sub(r"[^a-z\s]", "", name)
    return " ".join(name.split())


def _names_match(name1: str, name2: str) -> bool:
    """Check if two player names likely match."""
    words1 = name1.split()
    words2 = name2.split()
    
    if not words1 or not words2:
        return False
    
    # Last name match
    if words1[-1] == words2[-1]:
        return True
    
    # Multiple word match
    return len(set(words1) & set(words2)) >= 2


def calculate_game_confidence(
    home_lineup: LineupAdjustedStrength,
    away_lineup: LineupAdjustedStrength,
    home_volatility: float,
    away_volatility: float,
) -> str:
    """
    Calculate confidence level for a game prediction.
    
    Returns:
        "high", "medium", or "low"
    """
    # Factors that reduce confidence:
    # 1. Missing key players (uncertainty)
    # 2. High team volatility (unpredictable)
    # 3. Close matchup (harder to predict)
    
    # Injury uncertainty
    injury_penalty = home_lineup.confidence_penalty + away_lineup.confidence_penalty
    
    # Volatility (0-1 scale)
    avg_volatility = (home_volatility + away_volatility) / 2
    
    # Edge magnitude (larger edge = more confident)
    rating_diff = abs(home_lineup.adjusted_net_rating - away_lineup.adjusted_net_rating)
    edge_factor = min(1.0, rating_diff / 10)  # 10+ point diff = max confidence
    
    # Calculate overall confidence score
    confidence_score = (
        0.4 * (1 - injury_penalty)  # Injury component
        + 0.3 * (1 - avg_volatility)  # Volatility component
        + 0.3 * edge_factor  # Edge component
    )
    
    if confidence_score >= 0.7:
        return "high"
    elif confidence_score >= 0.4:
        return "medium"
    else:
        return "low"
