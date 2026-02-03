"""
Known absences module for manual override of player availability.

The NBA injury report only includes injuries/illness, NOT:
- Personal reasons
- Team decisions  
- Rest days
- Undisclosed reasons
- Suspensions (sometimes)

This module allows manual tracking of known absences that won't
appear on the official injury report.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import csv

from .injuries import InjuryRow
from .availability import normalize_player_name


# Default location for known absences file
DEFAULT_ABSENCES_FILE = Path(__file__).parent.parent / "data" / "known_absences.csv"


@dataclass
class KnownAbsence:
    """A manually tracked player absence."""
    team: str
    player: str
    reason: str
    start_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD or None if indefinite
    source: str = "manual"  # manual, news, twitter, etc.
    
    def is_active(self, check_date: Optional[str] = None) -> bool:
        """Check if this absence is active for a given date."""
        if check_date is None:
            check_date = datetime.now().strftime("%Y-%m-%d")
        
        # Check start date
        if self.start_date > check_date:
            return False
        
        # Check end date
        if self.end_date and self.end_date < check_date:
            return False
        
        return True
    
    def to_injury_row(self) -> InjuryRow:
        """Convert to InjuryRow for integration with existing system."""
        return InjuryRow(
            team=self.team,
            player=self.player,
            status="Out",
            reason=self.reason,
        )


def load_known_absences(
    file_path: Optional[Path] = None,
    check_date: Optional[str] = None,
) -> list[KnownAbsence]:
    """
    Load known absences from CSV file.
    
    CSV format:
    team,player,reason,start_date,end_date,source
    PHI,James Harden,Personal Reasons,2026-02-01,,news
    LAC,Kawhi Leonard,Load Management,2026-02-02,2026-02-02,team
    
    Args:
        file_path: Path to CSV file. Defaults to data/known_absences.csv
        check_date: Only return absences active on this date (YYYY-MM-DD)
    
    Returns:
        List of active KnownAbsence objects
    """
    if file_path is None:
        file_path = DEFAULT_ABSENCES_FILE
    
    absences = []
    
    if not file_path.exists():
        return absences
    
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip comment rows or empty rows
                team = row.get('team', '')
                if not team or team.startswith('#'):
                    continue
                
                player = row.get('player', '')
                if not player or player.startswith('#'):
                    continue
                
                absence = KnownAbsence(
                    team=team.strip().upper(),
                    player=player.strip(),
                    reason=(row.get('reason') or 'Unknown').strip(),
                    start_date=(row.get('start_date') or '').strip(),
                    end_date=(row.get('end_date') or '').strip() or None,
                    source=(row.get('source') or 'manual').strip(),
                )
                
                # Only include if active
                if absence.team and absence.player and absence.is_active(check_date):
                    absences.append(absence)
    
    except Exception as e:
        print(f"  Warning: Could not load known absences: {e}")
    
    return absences


def save_known_absence(
    absence: KnownAbsence,
    file_path: Optional[Path] = None,
) -> bool:
    """
    Add a new absence to the CSV file.
    
    Args:
        absence: KnownAbsence to add
        file_path: Path to CSV file
    
    Returns:
        True if successful
    """
    if file_path is None:
        file_path = DEFAULT_ABSENCES_FILE
    
    try:
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file exists to determine if we need header
        write_header = not file_path.exists()
        
        with open(file_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            if write_header:
                writer.writerow(['team', 'player', 'reason', 'start_date', 'end_date', 'source'])
            
            writer.writerow([
                absence.team,
                absence.player,
                absence.reason,
                absence.start_date,
                absence.end_date or '',
                absence.source,
            ])
        
        return True
        
    except Exception as e:
        print(f"  Error saving absence: {e}")
        return False


def merge_known_absences_with_injuries(
    injuries: list[InjuryRow],
    absences: list[KnownAbsence],
) -> list[InjuryRow]:
    """
    Merge known absences into injury list.
    
    Known absences take priority over injury report since they
    represent confirmed unavailability.
    
    Args:
        injuries: List of InjuryRow from injury report
        absences: List of KnownAbsence from manual tracking
    
    Returns:
        Merged list of InjuryRow
    """
    merged = list(injuries)
    
    for absence in absences:
        # Check if player already in injuries
        player_norm = normalize_player_name(absence.player)
        found = False
        
        for i, inj in enumerate(merged):
            if inj.team == absence.team:
                inj_norm = normalize_player_name(inj.player)
                if player_norm == inj_norm or _fuzzy_match(player_norm, inj_norm):
                    # Update existing entry to OUT
                    merged[i] = InjuryRow(
                        team=inj.team,
                        player=inj.player,
                        status="Out",
                        reason=absence.reason,
                    )
                    found = True
                    break
        
        if not found:
            # Add new entry
            merged.append(absence.to_injury_row())
    
    return merged


def _fuzzy_match(name1: str, name2: str) -> bool:
    """Simple fuzzy match for player names."""
    words1 = set(name1.split())
    words2 = set(name2.split())
    
    # Match if last names match
    if words1 and words2:
        if list(words1)[-1] == list(words2)[-1]:
            return True
    
    # Match if 2+ words overlap
    return len(words1 & words2) >= 2


def create_sample_absences_file(file_path: Optional[Path] = None):
    """Create a sample known_absences.csv file with instructions."""
    if file_path is None:
        file_path = DEFAULT_ABSENCES_FILE
    
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    sample_content = """# Known Absences File
# Add players who are OUT but NOT on the official injury report
# This includes: personal reasons, rest, team decisions, suspensions, etc.
#
# Format: team,player,reason,start_date,end_date,source
# - team: 3-letter abbreviation (PHI, LAC, etc.)
# - player: Full name as it appears in stats
# - reason: Why they're out
# - start_date: YYYY-MM-DD when absence started
# - end_date: YYYY-MM-DD when they return (leave empty if unknown)
# - source: Where you learned this (news, twitter, team, etc.)
#
# Example entries (uncomment and modify as needed):
# PHI,James Harden,Personal Reasons,2026-02-01,,news
# LAC,Kawhi Leonard,Load Management,2026-02-02,2026-02-02,team
team,player,reason,start_date,end_date,source
"""
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(sample_content)
    
    print(f"Created sample absences file: {file_path}")
    return file_path
