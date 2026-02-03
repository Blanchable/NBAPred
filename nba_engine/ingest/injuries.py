"""
Injuries module for fetching and parsing NBA injury reports.

Downloads official NBA injury report PDFs and parses them into structured data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import re

import pdfplumber
import requests


# NBA injury report base URL
INJURY_REPORT_BASE_URL = "https://ak-static.cms.nba.com/referee/injury/"

# Status keywords to look for
STATUS_KEYWORDS = ["Out", "Doubtful", "Questionable", "Probable"]

# Request timeout in seconds
REQUEST_TIMEOUT = 10

# NBA team abbreviations and full names
NBA_TEAMS = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "LA Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}

# Team name patterns for extraction (without spaces)
TEAM_NAME_PATTERNS = {
    "AtlantaHawks": "ATL",
    "BostonCeltics": "BOS",
    "BrooklynNets": "BKN",
    "CharlotteHornets": "CHA",
    "ChicagoBulls": "CHI",
    "ClevelandCavaliers": "CLE",
    "DallasMavericks": "DAL",
    "DenverNuggets": "DEN",
    "DetroitPistons": "DET",
    "GoldenStateWarriors": "GSW",
    "HoustonRockets": "HOU",
    "IndianaPacers": "IND",
    "LAClippers": "LAC",
    "LosAngelesClippers": "LAC",
    "LosAngelesLakers": "LAL",
    "MemphisGrizzlies": "MEM",
    "MiamiHeat": "MIA",
    "MilwaukeeBucks": "MIL",
    "MinnesotaTimberwolves": "MIN",
    "NewOrleansPelicans": "NOP",
    "NewYorkKnicks": "NYK",
    "OklahomaCityThunder": "OKC",
    "OrlandoMagic": "ORL",
    "Philadelphia76ers": "PHI",
    "PhoenixSuns": "PHX",
    "PortlandTrailBlazers": "POR",
    "SacramentoKings": "SAC",
    "SanAntonioSpurs": "SAS",
    "TorontoRaptors": "TOR",
    "UtahJazz": "UTA",
    "WashingtonWizards": "WAS",
}


@dataclass
class InjuryRow:
    """Represents a single injury report entry."""
    team: str
    player: str
    status: str
    reason: str
    
    @property
    def player_normalized(self) -> str:
        """Get normalized player name for matching."""
        from .availability import normalize_player_name
        return normalize_player_name(self.player)
    
    def get_canonical_status(self):
        """Get canonical availability status."""
        from .availability import normalize_availability
        return normalize_availability(self.status, self.reason)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for CSV output."""
        return {
            'team': self.team,
            'player': self.player,
            'status': self.status,
            'reason': self.reason,
            'canonical_status': self.get_canonical_status().value,
        }


def _get_eastern_time_offset() -> int:
    """
    Get the hour offset from UTC for Eastern Time.
    
    Simplified approach: EST is UTC-5, EDT is UTC-4.
    This is a rough approximation without pytz/zoneinfo.
    
    Returns:
        Hour offset (negative for behind UTC).
    """
    # Approximate: DST roughly March-November
    now = datetime.utcnow()
    month = now.month
    
    # Simplified DST check (second Sunday in March to first Sunday in November)
    if 3 < month < 11:
        return -4  # EDT
    elif month == 3:
        # Rough: assume DST after March 10
        return -4 if now.day > 10 else -5
    elif month == 11:
        # Rough: assume DST ends after November 7
        return -5 if now.day > 7 else -4
    else:
        return -5  # EST


def _format_injury_url(dt: datetime) -> str:
    """
    Format the injury report URL for a given datetime.
    
    Args:
        dt: Datetime to format (should be in Eastern Time).
    
    Returns:
        Full URL to the injury report PDF.
    """
    # Format: Injury-Report_YYYY-MM-DD_HH_MMAM.pdf or HH_MMPM.pdf
    date_str = dt.strftime("%Y-%m-%d")
    
    hour = dt.hour
    minute = dt.minute
    
    # Round minute to nearest 15
    minute = (minute // 15) * 15
    
    # Convert to 12-hour format
    if hour == 0:
        hour_12 = 12
        am_pm = "AM"
    elif hour < 12:
        hour_12 = hour
        am_pm = "AM"
    elif hour == 12:
        hour_12 = 12
        am_pm = "PM"
    else:
        hour_12 = hour - 12
        am_pm = "PM"
    
    filename = f"Injury-Report_{date_str}_{hour_12:02d}_{minute:02d}{am_pm}.pdf"
    return f"{INJURY_REPORT_BASE_URL}{filename}"


def find_latest_injury_pdf(
    max_hours_back: int = 36,
    cache_file: Optional[Path] = None,
) -> Optional[str]:
    """
    Find the URL of the latest available injury report PDF.
    
    Searches backwards in time (15-minute increments) to find an available report.
    
    Args:
        max_hours_back: Maximum hours to search backwards.
        cache_file: Optional path to cache file for storing latest URL.
    
    Returns:
        URL of the latest injury report, or None if not found.
    """
    # Check cache first if provided
    if cache_file and cache_file.exists():
        try:
            cached_url = cache_file.read_text().strip()
            # Verify it's still valid
            response = requests.head(cached_url, timeout=REQUEST_TIMEOUT)
            content_type = response.headers.get("Content-Type", "")
            if response.status_code == 200 and "pdf" in content_type.lower():
                return cached_url
        except Exception:
            pass  # Cache invalid or expired, continue searching
    
    # Calculate Eastern time from UTC
    utc_now = datetime.utcnow()
    et_offset = _get_eastern_time_offset()
    eastern_now = utc_now + timedelta(hours=et_offset)
    
    # Search backwards in 15-minute increments
    max_steps = (max_hours_back * 60) // 15
    
    for step in range(max_steps):
        check_time = eastern_now - timedelta(minutes=step * 15)
        url = _format_injury_url(check_time)
        
        try:
            response = requests.head(url, timeout=REQUEST_TIMEOUT)
            content_type = response.headers.get("Content-Type", "")
            
            if response.status_code == 200 and "pdf" in content_type.lower():
                # Found it! Cache if file provided
                if cache_file:
                    try:
                        cache_file.parent.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(url)
                    except Exception:
                        pass  # Cache write failed, not critical
                
                return url
                
        except requests.RequestException:
            continue  # Try next timestamp
    
    return None


def download_injury_pdf(
    url: str,
    output_path: Optional[Path] = None,
    max_retries: int = 3,
) -> Optional[bytes]:
    """
    Download the injury report PDF.
    
    Args:
        url: URL of the PDF to download.
        output_path: Optional path to save the PDF.
        max_retries: Maximum number of retry attempts.
    
    Returns:
        PDF content as bytes, or None if download failed.
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT * 2)
            response.raise_for_status()
            
            pdf_bytes = response.content
            
            # Save to file if path provided
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(pdf_bytes)
            
            return pdf_bytes
            
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                continue
            else:
                print(f"  Failed to download PDF after {max_retries} attempts: {e}")
                return None
    
    return None


def parse_injury_pdf(pdf_bytes: bytes) -> list[InjuryRow]:
    """
    Parse injury report PDF into structured rows.
    
    This is a best-effort heuristic parser for v1. Some entries may be
    missed or incorrectly parsed.
    
    Args:
        pdf_bytes: Raw PDF content.
    
    Returns:
        List of InjuryRow objects.
    """
    injuries = []
    
    try:
        import io
        pdf_file = io.BytesIO(pdf_bytes)
        
        with pdfplumber.open(pdf_file) as pdf:
            current_team = ""
            
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                
                lines = text.split("\n")
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check for game header line (contains matchup like NOP@CHA)
                    matchup_match = re.search(r"([A-Z]{3})@([A-Z]{3})", line)
                    if matchup_match:
                        # Extract away and home team from matchup for context
                        # The injuries below will be for these teams
                        pass
                    
                    # Try to parse this line
                    injury = _parse_injury_line(line, current_team)
                    
                    if injury:
                        injuries.append(injury)
                        current_team = injury.team
                    else:
                        # Check if this line sets a new team context
                        team_match = _extract_team_from_line(line)
                        if team_match:
                            current_team = team_match
    
    except Exception as e:
        print(f"  Error parsing PDF: {e}")
    
    return injuries


def _extract_team_abbrev_from_text(text: str) -> Optional[str]:
    """
    Extract team abbreviation from text that may contain full team name.
    
    Args:
        text: Text that may contain team name.
    
    Returns:
        Team abbreviation or None.
    """
    # First check for direct abbreviations
    for abbrev in NBA_TEAMS.keys():
        if text.startswith(abbrev + " ") or text == abbrev:
            return abbrev
    
    # Check for full team names (without spaces)
    for pattern, abbrev in TEAM_NAME_PATTERNS.items():
        if pattern in text:
            return abbrev
    
    return None


def _extract_team_from_line(line: str) -> Optional[str]:
    """
    Extract team abbreviation from a line if present.
    
    Args:
        line: Text line to analyze.
    
    Returns:
        Team abbreviation or None.
    """
    # Check for direct abbreviation at start
    words = line.split()
    if words:
        first_word = words[0].upper()
        if first_word in NBA_TEAMS:
            return first_word
    
    # Check for full team name patterns
    return _extract_team_abbrev_from_text(line)


def _parse_injury_line(line: str, current_team: str) -> Optional[InjuryRow]:
    """
    Attempt to parse a single line into an InjuryRow.
    
    Args:
        line: Text line to parse.
        current_team: Current team context (used if team not in line).
    
    Returns:
        InjuryRow if successfully parsed, None otherwise.
    """
    # Skip header lines and non-data lines
    # Be careful not to match actual injury reasons like "Personal Reasons"
    lower_line = line.lower().strip()
    
    # Skip exact header matches or lines starting with header text
    header_patterns = [
        "game date",
        "game time", 
        "matchup",
        "injury report",
        "nba official",
    ]
    if any(lower_line.startswith(p) for p in header_patterns):
        return None
    
    # Skip lines that are just notes or page markers
    if lower_line.startswith("note:") or lower_line.startswith("page"):
        return None
    
    # Skip "NOT YET SUBMITTED" lines (these are team placeholders)
    if "not yet submitted" in lower_line:
        return None
    
    # Skip header row with column names (very specific match)
    if lower_line == "team player name current status reason":
        return None
    if "playername" in lower_line.replace(" ", "") and "currentstatus" in lower_line.replace(" ", ""):
        return None
    
    # Skip lines that are just game info (date/time + matchup only)
    if re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s*\(ET\)\s+[A-Z]{3}@[A-Z]{3}$", line):
        return None
    
    # Find status keyword in line
    status_found = None
    status_pos = -1
    
    for status in STATUS_KEYWORDS:
        # Use word boundary matching to avoid partial matches
        pattern = r"\b" + status + r"\b"
        match = re.search(pattern, line)
        if match:
            pos = match.start()
            # Use the first (leftmost) status found
            if status_pos == -1 or pos < status_pos:
                status_found = status
                status_pos = pos
    
    if not status_found or status_pos == -1:
        return None
    
    # Split line around status
    before_status = line[:status_pos].strip()
    after_status = line[status_pos + len(status_found):].strip()
    
    # Try to extract team from beginning
    team = current_team
    player_text = before_status
    
    # Check if line starts with full date/time info (e.g., "02/02/2026 07:00(ET) HOU@IND")
    datetime_match = re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s*\(ET\)\s+([A-Z]{3})@([A-Z]{3})\s+", before_status)
    if datetime_match:
        # Extract teams from matchup, but the player belongs to the team after the matchup
        before_status = before_status[datetime_match.end():].strip()
        player_text = before_status
    else:
        # Check if line starts with just time info (e.g., "07:00(ET) HOU@IND")
        time_match = re.match(r"^\d{1,2}:\d{2}\s*\(ET\)\s+([A-Z]{3})@([A-Z]{3})\s+", before_status)
        if time_match:
            # Extract teams from matchup, but the player belongs to the team after the matchup
            before_status = before_status[time_match.end():].strip()
            player_text = before_status
    
    # Check if text starts with full team name (no space separation)
    team_from_name = _extract_team_abbrev_from_text(player_text)
    if team_from_name:
        team = team_from_name
        # Remove the team name pattern from player text
        for pattern, abbrev in TEAM_NAME_PATTERNS.items():
            if abbrev == team_from_name and pattern in player_text:
                player_text = player_text.replace(pattern, "", 1).strip()
                break
    else:
        # Check if line starts with team abbreviation
        words = player_text.split()
        if words and words[0].upper() in NBA_TEAMS:
            team = words[0].upper()
            player_text = " ".join(words[1:]).strip()
    
    # Clean up player name - handle "LastName,FirstName" format
    player = player_text.strip()
    
    # Convert "LastName,FirstName" to "FirstName LastName"
    if "," in player and not any(c.isdigit() for c in player):
        parts = player.split(",", 1)
        if len(parts) == 2:
            last_name = parts[0].strip()
            first_name = parts[1].strip()
            if first_name and last_name:
                player = f"{first_name} {last_name}"
    
    # Clean up reason
    reason = after_status.strip()
    
    # Sanity checks
    if len(player) < 3:
        return None
    if len(reason) < 1:
        return None
    
    # Additional cleanup - remove common prefixes/suffixes
    # Remove position markers sometimes attached
    player = re.sub(r"\s*[CGFP]{1,2}$", "", player)  # Remove trailing position
    player = re.sub(r"^[CGFP]{1,2}\s+", "", player)  # Remove leading position
    
    # Remove any remaining game time patterns
    player = re.sub(r"^\d{1,2}:\d{2}\s*\(ET\)\s*", "", player)
    
    return InjuryRow(
        team=team,
        player=player.strip(),
        status=status_found,
        reason=reason,
    )
