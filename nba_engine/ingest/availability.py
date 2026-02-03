"""
Availability normalization module for injury/inactive status handling.

Normalizes various injury, personal, rest, and suspension statuses into
canonical categories for accurate availability calculations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import re
import unicodedata


class CanonicalStatus(Enum):
    """Canonical availability status categories."""
    OUT = "OUT"
    DOUBTFUL = "DOUBTFUL"
    QUESTIONABLE = "QUESTIONABLE"
    PROBABLE = "PROBABLE"
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"  # For stars when data is incomplete


# Multipliers for each status
STATUS_MULTIPLIERS = {
    CanonicalStatus.OUT: 0.0,
    CanonicalStatus.DOUBTFUL: 0.25,
    CanonicalStatus.QUESTIONABLE: 0.60,
    CanonicalStatus.PROBABLE: 0.85,
    CanonicalStatus.AVAILABLE: 1.00,
    CanonicalStatus.UNKNOWN: 0.90,  # Star uncertainty tax
}

# Keywords that indicate OUT status regardless of reason
OUT_KEYWORDS = [
    "out",
    "inactive",
    "not with team",
    "personal",
    "rest",
    "suspended",
    "suspension",
    "g league",
    "g-league",
    "two-way",
    "two way",
    "illness",
    "health and safety",
    "health & safety",
    "protocol",
    "dnp",
    "did not play",
    "not available",
    "waived",
    "released",
]

# Keywords for other statuses
DOUBTFUL_KEYWORDS = ["doubtful", "unlikely"]
QUESTIONABLE_KEYWORDS = ["questionable", "game time decision", "gtd"]
PROBABLE_KEYWORDS = ["probable", "likely", "expected to play"]


def normalize_availability(
    status_text: str,
    reason_text: str = "",
) -> CanonicalStatus:
    """
    Normalize raw status and reason text into canonical availability status.
    
    Treats personal reasons, rest, suspension, etc. the same as injury OUT.
    
    Args:
        status_text: Raw status from injury report (e.g., "Out", "Questionable")
        reason_text: Raw reason text (e.g., "Left Ankle Sprain", "Personal Reasons")
    
    Returns:
        CanonicalStatus enum value
    """
    # Combine and lowercase for matching
    status_lower = status_text.lower().strip() if status_text else ""
    reason_lower = reason_text.lower().strip() if reason_text else ""
    combined = f"{status_lower} {reason_lower}"
    
    # Check for OUT keywords first (highest priority)
    for keyword in OUT_KEYWORDS:
        if keyword in combined:
            return CanonicalStatus.OUT
    
    # Check for explicit OUT status
    if status_lower in ["out", "o"]:
        return CanonicalStatus.OUT
    
    # Check for DOUBTFUL
    for keyword in DOUBTFUL_KEYWORDS:
        if keyword in combined:
            return CanonicalStatus.DOUBTFUL
    
    # Check for QUESTIONABLE
    for keyword in QUESTIONABLE_KEYWORDS:
        if keyword in combined:
            return CanonicalStatus.QUESTIONABLE
    
    # Check for PROBABLE
    for keyword in PROBABLE_KEYWORDS:
        if keyword in combined:
            return CanonicalStatus.PROBABLE
    
    # If status field contains specific keywords
    if status_lower == "d" or "doubt" in status_lower:
        return CanonicalStatus.DOUBTFUL
    if status_lower == "q" or "question" in status_lower:
        return CanonicalStatus.QUESTIONABLE
    if status_lower == "p" or "prob" in status_lower:
        return CanonicalStatus.PROBABLE
    
    # Default to AVAILABLE if no negative indicators
    return CanonicalStatus.AVAILABLE


def normalize_player_name(name: str) -> str:
    """
    Normalize player name for matching across different sources.
    
    Handles:
    - Case normalization
    - Punctuation removal
    - Suffix removal (Jr., Sr., II, III, IV)
    - Accent/diacritic normalization
    - Whitespace normalization
    
    Args:
        name: Raw player name
    
    Returns:
        Normalized name for comparison
    """
    if not name:
        return ""
    
    # Convert to lowercase
    name = name.lower()
    
    # Normalize unicode characters (accents -> base characters)
    # NFD decomposes characters, then we remove combining marks
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    
    # Remove suffixes (must be done before punctuation removal)
    suffix_patterns = [
        r'\s+jr\.?$',
        r'\s+sr\.?$',
        r'\s+ii+$',
        r'\s+iv$',
        r'\s+v$',
    ]
    for pattern in suffix_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Remove punctuation except spaces
    name = re.sub(r"[^\w\s]", "", name)
    
    # Collapse multiple spaces and strip
    name = " ".join(name.split())
    
    return name


def names_match(name1: str, name2: str, strict: bool = False) -> bool:
    """
    Check if two player names likely match.
    
    Uses normalized names for comparison with multiple matching strategies.
    
    Args:
        name1: First player name (will be normalized)
        name2: Second player name (will be normalized)
        strict: If True, requires exact match; if False, allows partial matches
    
    Returns:
        True if names are considered a match
    """
    norm1 = normalize_player_name(name1)
    norm2 = normalize_player_name(name2)
    
    if not norm1 or not norm2:
        return False
    
    # Exact match
    if norm1 == norm2:
        return True
    
    if strict:
        return False
    
    # Split into words
    words1 = norm1.split()
    words2 = norm2.split()
    
    # Last name match (most reliable)
    if words1 and words2 and words1[-1] == words2[-1]:
        # If last names match and first initial matches, very likely same person
        if words1[0][0] == words2[0][0]:
            return True
        # If last names match exactly and it's a unique enough last name
        # (more than 4 characters), consider it a match
        if len(words1[-1]) > 4:
            return True
    
    # Multiple word match (2+ words matching)
    matching_words = set(words1) & set(words2)
    if len(matching_words) >= 2:
        return True
    
    # Substring match for compound names (e.g., "Gilgeous-Alexander" vs "Shai Gilgeous")
    if any(w1 in norm2 for w1 in words1 if len(w1) > 4):
        return True
    if any(w2 in norm1 for w2 in words2 if len(w2) > 4):
        return True
    
    return False


@dataclass
class PlayerAvailability:
    """Detailed availability info for a single player."""
    player_name: str
    player_name_normalized: str
    team: str
    impact_rank: int  # 1 = top player, 2 = second, etc.
    impact_value: float
    injury_status_raw: str
    reason_raw: str
    canonical_status: CanonicalStatus
    source: str  # "injury_pdf", "inactives", "default", "unknown"
    matched: bool  # Whether we found this player in injury data
    is_star: bool  # Top 2 player on team
    
    @property
    def multiplier(self) -> float:
        """Get availability multiplier for this player."""
        return STATUS_MULTIPLIERS.get(self.canonical_status, 1.0)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for CSV output."""
        return {
            'team': self.team,
            'player': self.player_name,
            'impact_rank': self.impact_rank,
            'impact_value': round(self.impact_value, 2),
            'injury_status_raw': self.injury_status_raw,
            'reason_raw': self.reason_raw,
            'canonical_status': self.canonical_status.value,
            'source': self.source,
            'matched': self.matched,
            'is_star': self.is_star,
            'multiplier': self.multiplier,
        }


class AvailabilityConfidence(Enum):
    """Confidence level in availability data."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class TeamAvailabilityResult:
    """Complete availability analysis for a team."""
    team: str
    availability_pct: float
    confidence: AvailabilityConfidence
    player_details: list[PlayerAvailability]
    missing_stars: list[str]
    stars_unconfirmed: list[str]
    injury_report_available: bool
    inactives_available: bool
    
    def to_dict(self) -> dict:
        """Convert to dictionary for output."""
        return {
            'team': self.team,
            'availability_pct': round(self.availability_pct * 100, 1),
            'confidence': self.confidence.value,
            'missing_stars': ', '.join(self.missing_stars) if self.missing_stars else 'None',
            'stars_unconfirmed': ', '.join(self.stars_unconfirmed) if self.stars_unconfirmed else 'None',
            'injury_report_available': self.injury_report_available,
            'inactives_available': self.inactives_available,
        }


def calculate_availability_confidence(
    injury_report_available: bool,
    inactives_available: bool,
    stars_matched: int,
    stars_total: int,
    questionable_stars: int,
) -> AvailabilityConfidence:
    """
    Determine confidence level in availability data.
    
    Args:
        injury_report_available: Whether injury PDF was successfully parsed
        inactives_available: Whether inactives list was fetched
        stars_matched: Number of star players found in data sources
        stars_total: Total number of star players (typically 2)
        questionable_stars: Number of stars with questionable/doubtful status
    
    Returns:
        AvailabilityConfidence enum value
    """
    # LOW: No injury data at all
    if not injury_report_available and not inactives_available:
        return AvailabilityConfidence.LOW
    
    # HIGH: Full data and stars accounted for
    if injury_report_available and stars_matched >= stars_total and questionable_stars == 0:
        return AvailabilityConfidence.HIGH
    
    # HIGH: Inactives confirm stars are playing
    if inactives_available and stars_matched >= stars_total:
        return AvailabilityConfidence.HIGH
    
    # MEDIUM: Some data but stars not fully confirmed
    if injury_report_available or inactives_available:
        if stars_matched < stars_total or questionable_stars > 0:
            return AvailabilityConfidence.MEDIUM
    
    return AvailabilityConfidence.MEDIUM
