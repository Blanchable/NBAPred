"""
Lineup adjustment module for v3 predictions.

Adjusts team strength based on who is actually playing tonight.
Includes star safeguards, availability confidence tracking, and
proper handling of personal/rest/suspension absences.
"""

from dataclasses import dataclass, field
from typing import Optional

from ingest.availability import (
    CanonicalStatus,
    STATUS_MULTIPLIERS,
    normalize_availability,
    normalize_player_name,
    names_match,
    PlayerAvailability,
    AvailabilityConfidence,
    TeamAvailabilityResult,
    calculate_availability_confidence,
)


@dataclass
class LineupAdjustedStrength:
    """Team strength adjusted for tonight's lineup."""
    team: str
    base_net_rating: float
    availability_score: float  # 0-1, percentage of strength available
    adjusted_net_rating: float
    missing_players: list[str]
    confidence_penalty: float  # Uncertainty due to injuries
    
    # New fields for availability tracking
    availability_confidence: AvailabilityConfidence = AvailabilityConfidence.MEDIUM
    availability_pct: float = 1.0
    stars_out: list[str] = field(default_factory=list)
    stars_unconfirmed: list[str] = field(default_factory=list)
    player_details: list[PlayerAvailability] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'team': self.team,
            'base_net_rating': self.base_net_rating,
            'availability_score': self.availability_score,
            'adjusted_net_rating': self.adjusted_net_rating,
            'missing_players': self.missing_players,
            'confidence_penalty': self.confidence_penalty,
            'availability_confidence': self.availability_confidence.value,
            'availability_pct': round(self.availability_pct * 100, 1),
            'stars_out': self.stars_out,
            'stars_unconfirmed': self.stars_unconfirmed,
        }


def calculate_lineup_adjusted_strength(
    team: str,
    team_strength,  # TeamStrength object
    players: list,  # List of PlayerImpact for this team
    injuries: list,  # List of InjuryRow objects (all teams)
    is_home: bool = True,
    inactives: Optional[dict] = None,  # Dict of team -> list[InactivePlayer]
    injury_report_available: bool = True,
) -> LineupAdjustedStrength:
    """
    Calculate lineup-adjusted team strength with star safeguards.
    
    Args:
        team: Team abbreviation.
        team_strength: TeamStrength object with base ratings.
        players: List of PlayerImpact for this team.
        injuries: List of all InjuryRow objects.
        is_home: Whether this is the home team.
        inactives: Optional dict of team -> inactive players from live API.
        injury_report_available: Whether injury report was successfully fetched.
    
    Returns:
        LineupAdjustedStrength object with availability analysis.
    """
    if inactives is None:
        inactives = {}
    
    # Get base rating (use home or road split)
    if is_home:
        base_rating = getattr(team_strength, 'home_net_rating', team_strength.net_rating)
    else:
        base_rating = getattr(team_strength, 'road_net_rating', team_strength.net_rating)
    
    # Use blended rating if available
    blended = getattr(team_strength, 'blended_net_rating', None)
    if blended is not None and blended != 0:
        base_rating = (base_rating + blended) / 2
    
    # Get team-specific injuries with canonical status
    team_injuries = {}
    for inj in injuries:
        if inj.team == team:
            player_norm = normalize_player_name(inj.player)
            canonical = normalize_availability(inj.status, inj.reason)
            team_injuries[player_norm] = {
                'raw_status': inj.status,
                'raw_reason': inj.reason,
                'canonical': canonical,
                'player_name': inj.player,
            }
    
    # Get team inactives
    team_inactives = inactives.get(team, [])
    inactives_available = len(team_inactives) > 0
    
    # Build set of inactive player names (normalized)
    inactive_names = set()
    for inactive in team_inactives:
        inactive_names.add(normalize_player_name(inactive.player_name))
    
    # Calculate availability for each player
    total_impact = 0.0
    available_impact = 0.0
    missing_players = []
    stars_out = []
    stars_unconfirmed = []
    player_details = []
    
    key_players = [p for p in players if p.is_key_player]
    stars = [p for p in players if getattr(p, 'is_star', False)]
    
    # If no player data, return default with low confidence
    if not key_players:
        return LineupAdjustedStrength(
            team=team,
            base_net_rating=base_rating,
            availability_score=1.0,
            adjusted_net_rating=base_rating,
            missing_players=[],
            confidence_penalty=0.2,  # Penalty for no data
            availability_confidence=AvailabilityConfidence.LOW,
            availability_pct=1.0,
            stars_out=[],
            stars_unconfirmed=[],
            player_details=[],
        )
    
    # Process each key player
    for player in key_players:
        impact = player.impact_score
        total_impact += impact
        player_norm = normalize_player_name(player.player_name)
        
        # Determine availability status from multiple sources
        canonical_status = CanonicalStatus.AVAILABLE
        source = "default"
        matched = False
        raw_status = ""
        raw_reason = ""
        
        # Check inactives first (highest priority)
        is_inactive = any(names_match(player.player_name, name) for name in inactive_names)
        if is_inactive:
            canonical_status = CanonicalStatus.OUT
            source = "inactives"
            matched = True
            raw_status = "Inactive"
            raw_reason = "Inactive List"
        
        # Check injury report
        injury_match = None
        for inj_norm, inj_data in team_injuries.items():
            if names_match(player_norm, inj_norm):
                injury_match = inj_data
                matched = True
                raw_status = inj_data['raw_status']
                raw_reason = inj_data['raw_reason']
                
                # If not already marked inactive, use injury status
                if source != "inactives":
                    canonical_status = inj_data['canonical']
                    source = "injury_pdf"
                break
        
        # STAR SAFEGUARD: If this is a star and we have no data, mark as UNKNOWN
        is_star = getattr(player, 'is_star', False) or player.impact_rank <= 2
        
        if is_star and not matched:
            if not injury_report_available:
                # No injury report at all - treat star as UNKNOWN
                canonical_status = CanonicalStatus.UNKNOWN
                source = "unknown"
                stars_unconfirmed.append(player.player_name)
            elif not inactives_available:
                # Injury report exists but star not listed
                # Could mean healthy, or could mean we missed them
                # Apply small uncertainty tax
                canonical_status = CanonicalStatus.UNKNOWN
                source = "unknown"
                stars_unconfirmed.append(player.player_name)
        
        # Calculate impact contribution
        multiplier = STATUS_MULTIPLIERS.get(canonical_status, 1.0)
        available_impact += impact * multiplier
        
        # Track missing players
        if canonical_status in [CanonicalStatus.OUT, CanonicalStatus.DOUBTFUL]:
            missing_players.append(f"{player.player_name} ({canonical_status.value})")
            if is_star:
                stars_out.append(player.player_name)
        
        # Build player availability detail
        player_avail = PlayerAvailability(
            player_name=player.player_name,
            player_name_normalized=player_norm,
            team=team,
            impact_rank=getattr(player, 'impact_rank', 0),
            impact_value=impact,
            injury_status_raw=raw_status,
            reason_raw=raw_reason,
            canonical_status=canonical_status,
            source=source,
            matched=matched,
            is_star=is_star,
        )
        player_details.append(player_avail)
    
    # Calculate availability percentage
    if total_impact > 0:
        availability_pct = available_impact / total_impact
    else:
        availability_pct = 1.0
    
    # Calculate confidence
    stars_matched = sum(1 for d in player_details if d.is_star and d.matched)
    stars_total = sum(1 for d in player_details if d.is_star)
    questionable_stars = sum(
        1 for d in player_details 
        if d.is_star and d.canonical_status in [CanonicalStatus.QUESTIONABLE, CanonicalStatus.DOUBTFUL]
    )
    
    availability_confidence = calculate_availability_confidence(
        injury_report_available=injury_report_available,
        inactives_available=inactives_available,
        stars_matched=stars_matched,
        stars_total=stars_total,
        questionable_stars=questionable_stars,
    )
    
    # Adjust net rating based on availability
    availability_penalty = (1 - availability_pct) * 10  # Max ~10 point swing
    availability_penalty = min(availability_penalty, 8)  # Cap at 8 points
    adjusted_rating = base_rating - availability_penalty
    
    # Confidence penalty based on uncertainty
    confidence_penalty = 0.0
    
    # Penalty for questionable/doubtful players
    questionable_count = sum(
        1 for d in player_details 
        if d.canonical_status in [CanonicalStatus.QUESTIONABLE, CanonicalStatus.DOUBTFUL]
    )
    confidence_penalty += questionable_count * 0.1
    
    # Penalty for unconfirmed stars
    confidence_penalty += len(stars_unconfirmed) * 0.15
    
    # Penalty for low confidence data
    if availability_confidence == AvailabilityConfidence.LOW:
        confidence_penalty += 0.2
    elif availability_confidence == AvailabilityConfidence.MEDIUM:
        confidence_penalty += 0.1
    
    # Cap confidence penalty
    confidence_penalty = min(confidence_penalty, 0.5)
    
    return LineupAdjustedStrength(
        team=team,
        base_net_rating=base_rating,
        availability_score=availability_pct,
        adjusted_net_rating=adjusted_rating,
        missing_players=missing_players,
        confidence_penalty=confidence_penalty,
        availability_confidence=availability_confidence,
        availability_pct=availability_pct,
        stars_out=stars_out,
        stars_unconfirmed=stars_unconfirmed,
        player_details=player_details,
    )


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
    # 4. Low availability confidence
    
    # Injury uncertainty
    injury_penalty = home_lineup.confidence_penalty + away_lineup.confidence_penalty
    
    # Volatility (0-1 scale)
    avg_volatility = (home_volatility + away_volatility) / 2
    
    # Edge magnitude (larger edge = more confident)
    rating_diff = abs(home_lineup.adjusted_net_rating - away_lineup.adjusted_net_rating)
    edge_factor = min(1.0, rating_diff / 10)  # 10+ point diff = max confidence
    
    # Availability confidence penalty
    avail_confidence_penalty = 0.0
    for lineup in [home_lineup, away_lineup]:
        if lineup.availability_confidence == AvailabilityConfidence.LOW:
            avail_confidence_penalty += 0.2
        elif lineup.availability_confidence == AvailabilityConfidence.MEDIUM:
            avail_confidence_penalty += 0.1
    
    # Calculate overall confidence score
    confidence_score = (
        0.3 * (1 - min(injury_penalty, 1.0))  # Injury component
        + 0.2 * (1 - avg_volatility)  # Volatility component
        + 0.3 * edge_factor  # Edge component
        + 0.2 * (1 - avail_confidence_penalty)  # Availability confidence
    )
    
    # Force downgrade if availability confidence is LOW
    if home_lineup.availability_confidence == AvailabilityConfidence.LOW or \
       away_lineup.availability_confidence == AvailabilityConfidence.LOW:
        confidence_score = min(confidence_score, 0.65)  # Cap at medium
    
    if confidence_score >= 0.7:
        return "high"
    elif confidence_score >= 0.4:
        return "medium"
    else:
        return "low"


def get_availability_debug_rows(
    home_lineup: LineupAdjustedStrength,
    away_lineup: LineupAdjustedStrength,
) -> list[dict]:
    """
    Get debug rows for availability analysis.
    
    Returns:
        List of dictionaries suitable for CSV output.
    """
    rows = []
    
    for lineup in [home_lineup, away_lineup]:
        for detail in lineup.player_details:
            rows.append(detail.to_dict())
    
    return rows
