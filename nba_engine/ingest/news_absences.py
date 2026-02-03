"""
News-based absence detection module.

Fetches player availability status from ESPN and other sports news APIs
to catch absences not on the official NBA injury report.

This catches:
- Personal reasons
- Team decisions
- Rest days
- Suspensions
- Trade-related absences
"""

from dataclasses import dataclass
from typing import Optional
import requests
import time
import re

from .injuries import InjuryRow
from .availability import normalize_player_name, CanonicalStatus


# ESPN API endpoints
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_TEAM_ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

# Request timeout
REQUEST_TIMEOUT = 15

# ESPN team ID mapping
ESPN_TEAM_IDS = {
    "ATL": "1", "BOS": "2", "BKN": "17", "CHA": "30", "CHI": "4",
    "CLE": "5", "DAL": "6", "DEN": "7", "DET": "8", "GSW": "9",
    "HOU": "10", "IND": "11", "LAC": "12", "LAL": "13", "MEM": "29",
    "MIA": "14", "MIL": "15", "MIN": "16", "NOP": "3", "NYK": "18",
    "OKC": "25", "ORL": "19", "PHI": "20", "PHX": "21", "POR": "22",
    "SAC": "23", "SAS": "24", "TOR": "28", "UTA": "26", "WAS": "27",
}


@dataclass  
class NewsAbsence:
    """Player absence from news source."""
    team: str
    player: str
    status: str  # Out, Doubtful, Questionable, Day-To-Day
    reason: str
    source: str  # espn, rotowire, etc.


def fetch_espn_injuries() -> list[NewsAbsence]:
    """
    Fetch injury/absence data from ESPN API.
    
    ESPN often has more comprehensive absence data than the
    official NBA injury report, including personal reasons.
    
    Returns:
        List of NewsAbsence objects
    """
    absences = []
    
    try:
        response = requests.get(
            ESPN_INJURIES_URL,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        
        if response.status_code != 200:
            print(f"  ESPN injuries API returned {response.status_code}")
            return absences
        
        data = response.json()
        
        # Parse injury data
        for team_data in data.get("injuries", []):
            # Team info can be at top level or nested
            team_abbrev = ""
            if "displayName" in team_data:
                # Try to map display name to abbreviation
                display_name = team_data.get("displayName", "")
                team_abbrev = _team_name_to_abbrev(display_name)
            
            for injury in team_data.get("injuries", []):
                athlete = injury.get("athlete", {})
                player_name = athlete.get("displayName", "")
                
                # Team abbreviation might be in athlete's team info
                if not team_abbrev:
                    athlete_team = athlete.get("team", {})
                    team_abbrev = athlete_team.get("abbreviation", "")
                
                status = injury.get("status", "")
                description = injury.get("longComment", "") or injury.get("shortComment", "")
                
                # Get injury type if available
                injury_type = injury.get("type", {}).get("description", "")
                if injury_type and not description:
                    description = injury_type
                
                if player_name and team_abbrev:
                    absences.append(NewsAbsence(
                        team=team_abbrev,
                        player=player_name,
                        status=status,
                        reason=description[:200] if description else "",
                        source="espn",
                    ))
        
        print(f"  ESPN: Found {len(absences)} injury/absence entries")
        
    except requests.RequestException as e:
        print(f"  ESPN injuries fetch failed: {e}")
    except Exception as e:
        print(f"  ESPN injuries parse error: {e}")
    
    return absences


def _team_name_to_abbrev(name: str) -> str:
    """Convert team display name to abbreviation."""
    name_map = {
        "Atlanta Hawks": "ATL",
        "Boston Celtics": "BOS",
        "Brooklyn Nets": "BKN",
        "Charlotte Hornets": "CHA",
        "Chicago Bulls": "CHI",
        "Cleveland Cavaliers": "CLE",
        "Dallas Mavericks": "DAL",
        "Denver Nuggets": "DEN",
        "Detroit Pistons": "DET",
        "Golden State Warriors": "GSW",
        "Houston Rockets": "HOU",
        "Indiana Pacers": "IND",
        "LA Clippers": "LAC",
        "Los Angeles Clippers": "LAC",
        "Los Angeles Lakers": "LAL",
        "Memphis Grizzlies": "MEM",
        "Miami Heat": "MIA",
        "Milwaukee Bucks": "MIL",
        "Minnesota Timberwolves": "MIN",
        "New Orleans Pelicans": "NOP",
        "New York Knicks": "NYK",
        "Oklahoma City Thunder": "OKC",
        "Orlando Magic": "ORL",
        "Philadelphia 76ers": "PHI",
        "Phoenix Suns": "PHX",
        "Portland Trail Blazers": "POR",
        "Sacramento Kings": "SAC",
        "San Antonio Spurs": "SAS",
        "Toronto Raptors": "TOR",
        "Utah Jazz": "UTA",
        "Washington Wizards": "WAS",
    }
    return name_map.get(name, "")


def fetch_espn_game_status(game_date: Optional[str] = None) -> list[NewsAbsence]:
    """
    Fetch today's game data from ESPN scoreboard.
    
    The scoreboard sometimes shows player availability info
    that's not in the injuries endpoint.
    
    Args:
        game_date: Date in YYYYMMDD format (defaults to today)
    
    Returns:
        List of NewsAbsence objects
    """
    absences = []
    
    try:
        params = {}
        if game_date:
            params["dates"] = game_date
        
        response = requests.get(
            ESPN_SCOREBOARD_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        
        if response.status_code != 200:
            return absences
        
        data = response.json()
        
        # Check each game for lineup/injury info
        for event in data.get("events", []):
            for competition in event.get("competitions", []):
                for competitor in competition.get("competitors", []):
                    team = competitor.get("team", {})
                    team_abbrev = team.get("abbreviation", "")
                    
                    # Check for injury info in odds or notes
                    notes = competitor.get("notes", [])
                    for note in notes:
                        # Look for injury-related notes
                        note_text = note.get("text", "")
                        if any(kw in note_text.lower() for kw in ["out", "doubtful", "questionable"]):
                            # Try to extract player name
                            # This is heuristic-based
                            pass
        
    except Exception as e:
        print(f"  ESPN scoreboard fetch error: {e}")
    
    return absences


def fetch_rotowire_news() -> list[NewsAbsence]:
    """
    Fetch player news from Rotowire (if available).
    
    Note: This may require API key or have rate limits.
    Currently a placeholder for future implementation.
    
    Returns:
        List of NewsAbsence objects
    """
    # Rotowire requires subscription for API
    # This is a placeholder for future implementation
    return []


def fetch_all_news_absences(teams_playing: Optional[list[str]] = None) -> list[NewsAbsence]:
    """
    Fetch absences from all available news sources.
    
    Args:
        teams_playing: Optional list of team abbreviations to filter by
    
    Returns:
        Combined list of NewsAbsence objects (deduplicated)
    """
    all_absences = []
    seen = set()
    
    # ESPN Injuries
    espn_absences = fetch_espn_injuries()
    for absence in espn_absences:
        key = (absence.team, normalize_player_name(absence.player))
        if key not in seen:
            seen.add(key)
            all_absences.append(absence)
    
    # Filter by teams if specified
    if teams_playing:
        all_absences = [a for a in all_absences if a.team in teams_playing]
    
    return all_absences


def news_absence_to_injury_row(absence: NewsAbsence) -> InjuryRow:
    """Convert NewsAbsence to InjuryRow."""
    # Normalize status
    status = absence.status
    if status.lower() in ["out", "o"]:
        status = "Out"
    elif status.lower() in ["doubtful", "d"]:
        status = "Doubtful"
    elif status.lower() in ["questionable", "q", "day-to-day"]:
        status = "Questionable"
    elif status.lower() in ["probable", "p"]:
        status = "Probable"
    else:
        status = "Out"  # Default to Out for unknown statuses
    
    return InjuryRow(
        team=absence.team,
        player=absence.player,
        status=status,
        reason=f"{absence.reason} (via {absence.source})",
    )


def merge_news_absences_with_injuries(
    injuries: list[InjuryRow],
    news_absences: list[NewsAbsence],
) -> list[InjuryRow]:
    """
    Merge news-sourced absences with injury report.
    
    News absences supplement (not override) the injury report,
    adding players who aren't listed on the official report.
    
    Args:
        injuries: List of InjuryRow from injury report
        news_absences: List of NewsAbsence from news sources
    
    Returns:
        Merged list of InjuryRow
    """
    merged = list(injuries)
    
    # Build set of players already in injuries
    existing_players = set()
    for inj in injuries:
        key = (inj.team, normalize_player_name(inj.player))
        existing_players.add(key)
    
    # Add news absences that aren't already covered
    added = 0
    for absence in news_absences:
        key = (absence.team, normalize_player_name(absence.player))
        
        if key not in existing_players:
            merged.append(news_absence_to_injury_row(absence))
            existing_players.add(key)
            added += 1
    
    if added > 0:
        print(f"  Added {added} absences from news sources")
    
    return merged


def check_star_recent_games(
    team: str,
    player_name: str,
    days_back: int = 5,
) -> Optional[dict]:
    """
    Check if a star player has played in recent games.
    
    If a star hasn't played recently but isn't on the injury report,
    this is a red flag that should trigger manual investigation.
    
    Args:
        team: Team abbreviation
        player_name: Player name
        days_back: Number of days to check
    
    Returns:
        Dict with recent game info, or None if can't determine
    """
    # This would require checking game logs
    # For now, return None (future enhancement)
    return None
