"""
Roster module for fetching NBA team rosters.

Uses the CommonTeamRoster endpoint which provides current roster
data including trades and player movement.
"""

from dataclasses import dataclass
from typing import List, Optional
import time

from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import teams as nba_teams


# Custom headers to avoid API blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
}

# Build team mappings
ALL_TEAMS = nba_teams.get_teams()
TEAM_ABBREV_TO_ID = {team["abbreviation"]: team["id"] for team in ALL_TEAMS}
TEAM_ID_TO_ABBREV = {team["id"]: team["abbreviation"] for team in ALL_TEAMS}
TEAM_ABBREV_TO_NAME = {team["abbreviation"]: team["full_name"] for team in ALL_TEAMS}

# List of all team abbreviations sorted
ALL_TEAM_ABBREVS = sorted(TEAM_ABBREV_TO_ID.keys())


@dataclass
class RosterPlayer:
    """Represents a player on a team's roster."""
    player_id: int
    player_name: str
    team_abbrev: str
    position: str
    jersey: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    experience: Optional[str] = None
    age: Optional[int] = None
    
    @property
    def player_name_normalized(self) -> str:
        """Get normalized player name for matching."""
        from .availability import normalize_player_name
        return normalize_player_name(self.player_name)


def get_team_roster(
    team_abbrev: str,
    season: str = "2024-25",
    max_retries: int = 2,
    timeout: int = 60,
) -> List[RosterPlayer]:
    """
    Fetch the current roster for a team.
    
    Args:
        team_abbrev: Team abbreviation (e.g., "BOS", "LAL")
        season: Season string (e.g., "2024-25")
        max_retries: Number of retry attempts
        timeout: Request timeout in seconds
    
    Returns:
        List of RosterPlayer objects sorted by player name
    """
    team_id = TEAM_ABBREV_TO_ID.get(team_abbrev)
    if not team_id:
        print(f"  Unknown team abbreviation: {team_abbrev}")
        return []
    
    for attempt in range(max_retries):
        try:
            # Small delay to avoid rate limiting
            if attempt > 0:
                time.sleep(1.0)
            
            roster = commonteamroster.CommonTeamRoster(
                team_id=team_id,
                season=season,
                timeout=timeout,
                headers=HEADERS,
            )
            
            # Get the roster data frame
            df = roster.get_data_frames()[0]
            
            players = []
            for _, row in df.iterrows():
                # Parse age from birthdate if available
                age = None
                try:
                    age_val = row.get("AGE")
                    if age_val:
                        age = int(float(age_val))
                except (ValueError, TypeError):
                    pass
                
                # Parse experience
                exp = row.get("EXP")
                if exp == "R":
                    experience = "Rookie"
                elif exp:
                    experience = f"{exp} yrs"
                else:
                    experience = None
                
                player = RosterPlayer(
                    player_id=int(row.get("PLAYER_ID", 0)),
                    player_name=row.get("PLAYER", "Unknown"),
                    team_abbrev=team_abbrev,
                    position=row.get("POSITION", ""),
                    jersey=str(row.get("NUM", "")) if row.get("NUM") else None,
                    height=row.get("HEIGHT"),
                    weight=str(row.get("WEIGHT", "")) if row.get("WEIGHT") else None,
                    experience=experience,
                    age=age,
                )
                players.append(player)
            
            # Sort by player name
            players.sort(key=lambda p: p.player_name)
            
            print(f"  Loaded roster for {team_abbrev}: {len(players)} players")
            return players
            
        except Exception as e:
            print(f"  Roster fetch attempt {attempt + 1} failed for {team_abbrev}: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.8)
    
    print(f"  Failed to fetch roster for {team_abbrev}")
    return []


def get_team_full_name(team_abbrev: str) -> str:
    """Get the full team name from abbreviation."""
    return TEAM_ABBREV_TO_NAME.get(team_abbrev, team_abbrev)


def get_all_team_abbrevs() -> List[str]:
    """Get list of all NBA team abbreviations."""
    return ALL_TEAM_ABBREVS.copy()
