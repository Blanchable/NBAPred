"""
Inactives module for fetching pregame inactive lists.

Attempts to fetch inactive players from NBA live game endpoints.
This is a secondary source to verify/supplement injury report data.
"""

from dataclasses import dataclass
from typing import Optional
import requests
import time

from .availability import normalize_player_name, CanonicalStatus


# NBA Live API endpoints
LIVE_BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
LIVE_SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"

# Request timeout
REQUEST_TIMEOUT = 15


@dataclass
class InactivePlayer:
    """Represents a player on the inactive list."""
    player_name: str
    player_name_normalized: str
    team: str
    reason: str  # May be empty
    source: str  # "boxscore", "scoreboard", "roster"


def fetch_game_inactives(game_id: str) -> tuple[list[InactivePlayer], bool]:
    """
    Fetch inactive players for a specific game.
    
    Tries the live boxscore endpoint to get pregame inactive lists.
    
    Args:
        game_id: NBA game ID (e.g., "0022500712")
    
    Returns:
        Tuple of (list of InactivePlayer, success_flag)
    """
    inactives = []
    
    try:
        url = LIVE_BOXSCORE_URL.format(game_id=game_id)
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Cache-Control": "no-cache",
            }
        )
        
        if response.status_code != 200:
            return [], False
        
        data = response.json()
        game = data.get("game", {})
        
        # Check both teams
        for team_key in ["homeTeam", "awayTeam"]:
            team_data = game.get(team_key, {})
            team_abbrev = team_data.get("teamTricode", "")
            
            # Check inactives list if present
            inactive_list = team_data.get("inactives", [])
            for player in inactive_list:
                player_name = player.get("name", "") or player.get("firstName", "") + " " + player.get("familyName", "")
                player_name = player_name.strip()
                if player_name:
                    inactives.append(InactivePlayer(
                        player_name=player_name,
                        player_name_normalized=normalize_player_name(player_name),
                        team=team_abbrev,
                        reason=player.get("reason", ""),
                        source="boxscore",
                    ))
            
            # Also check players marked with status != ACTIVE if available
            players = team_data.get("players", [])
            for player in players:
                status = player.get("status", "").upper()
                if status in ["INACTIVE", "OUT", "DNP"]:
                    player_name = player.get("name", "") or f"{player.get('firstName', '')} {player.get('familyName', '')}".strip()
                    if player_name and player_name.strip():
                        inactives.append(InactivePlayer(
                            player_name=player_name.strip(),
                            player_name_normalized=normalize_player_name(player_name),
                            team=team_abbrev,
                            reason=player.get("notPlayingReason", ""),
                            source="boxscore_roster",
                        ))
        
        return inactives, True
        
    except requests.RequestException as e:
        print(f"  Warning: Could not fetch inactives for game {game_id}: {e}")
        return [], False
    except Exception as e:
        print(f"  Warning: Error parsing inactives for game {game_id}: {e}")
        return [], False


def fetch_all_game_inactives(
    game_ids: list[str],
    delay_between_requests: float = 0.5,
) -> dict[str, list[InactivePlayer]]:
    """
    Fetch inactives for multiple games.
    
    Args:
        game_ids: List of NBA game IDs
        delay_between_requests: Delay between API calls to avoid rate limiting
    
    Returns:
        Dict mapping team abbreviation to list of inactive players
    """
    all_inactives = {}
    success_count = 0
    
    for game_id in game_ids:
        inactives, success = fetch_game_inactives(game_id)
        
        if success:
            success_count += 1
            for inactive in inactives:
                team = inactive.team
                if team not in all_inactives:
                    all_inactives[team] = []
                # Avoid duplicates
                if not any(
                    normalize_player_name(existing.player_name) == inactive.player_name_normalized
                    for existing in all_inactives[team]
                ):
                    all_inactives[team].append(inactive)
        
        # Small delay between requests
        if delay_between_requests > 0 and game_id != game_ids[-1]:
            time.sleep(delay_between_requests)
    
    if success_count > 0:
        total_inactives = sum(len(v) for v in all_inactives.values())
        print(f"  Fetched inactives from {success_count}/{len(game_ids)} games ({total_inactives} players)")
    else:
        print(f"  Warning: Could not fetch inactives from any game (endpoint may not be available yet)")
    
    return all_inactives


def merge_inactives_with_injuries(
    injuries: list,  # List of InjuryRow
    inactives: dict[str, list[InactivePlayer]],
) -> list:
    """
    Merge inactives list with injury report data.
    
    Inactives take priority - if a player appears in inactives but not injuries,
    they are added as OUT. If they appear in both, the inactive status confirms OUT.
    
    Args:
        injuries: List of InjuryRow from injury report
        inactives: Dict of team -> inactive players from live API
    
    Returns:
        Updated list of injury rows with inactives merged
    """
    from .injuries import InjuryRow
    
    merged = list(injuries)  # Copy original
    
    for team, team_inactives in inactives.items():
        for inactive in team_inactives:
            # Check if already in injury list
            found = False
            for i, inj in enumerate(merged):
                if inj.team == team:
                    from .availability import names_match
                    if names_match(inj.player, inactive.player_name):
                        # Already in list - confirm OUT status
                        found = True
                        # If injury says Questionable but inactives says inactive, update to Out
                        if inj.status in ["Questionable", "Probable"]:
                            merged[i] = InjuryRow(
                                team=inj.team,
                                player=inj.player,
                                status="Out",
                                reason=inactive.reason or inj.reason or "Inactive List",
                            )
                        break
            
            if not found:
                # Player in inactives but not injury report - add them
                merged.append(InjuryRow(
                    team=team,
                    player=inactive.player_name,
                    status="Out",
                    reason=inactive.reason or "Inactive List",
                ))
    
    return merged


def is_player_inactive(
    player_name: str,
    team: str,
    inactives: dict[str, list[InactivePlayer]],
) -> bool:
    """
    Check if a player is on the inactive list.
    
    Args:
        player_name: Player name to check
        team: Team abbreviation
        inactives: Dict of team -> inactive players
    
    Returns:
        True if player is on inactive list
    """
    from .availability import names_match
    
    team_inactives = inactives.get(team, [])
    player_norm = normalize_player_name(player_name)
    
    for inactive in team_inactives:
        if names_match(player_name, inactive.player_name):
            return True
    
    return False
