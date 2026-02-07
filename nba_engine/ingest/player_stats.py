"""
Player statistics module for lineup-adjusted predictions.

Fetches player stats to calculate impact scores for lineup adjustment.
"""

from dataclasses import dataclass
from typing import Optional
import time

from nba_api.stats.endpoints import leaguedashplayerstats
from nba_api.stats.static import teams as nba_teams


# Custom headers to avoid API blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
}

# Team ID to abbreviation mapping
TEAM_ID_TO_ABBREV = {team['id']: team['abbreviation'] for team in nba_teams.get_teams()}


@dataclass
class PlayerImpact:
    """Player impact data for lineup adjustment."""
    player_name: str
    team: str
    minutes_per_game: float
    points_per_game: float
    usage_pct: float  # If available
    impact_score: float  # Calculated: MPG * PPM
    is_key_player: bool  # Top 6 by impact on team
    impact_rank: int = 0  # 1 = top player, 2 = second, etc.
    is_star: bool = False  # Top 2 player on team
    
    @property
    def player_name_normalized(self) -> str:
        """Get normalized player name for matching."""
        from .availability import normalize_player_name
        return normalize_player_name(self.player_name)


def get_player_stats(
    season: str = "2024-25",
    max_retries: int = 2,
    timeout: int = 60,
) -> dict[str, list[PlayerImpact]]:
    """
    Fetch player stats and calculate impact scores.
    
    Returns:
        Dict mapping team abbreviation to list of PlayerImpact objects.
    """
    print("  Fetching player stats for lineup adjustment...")
    
    for attempt in range(max_retries):
        try:
            stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
                timeout=timeout,
                headers=HEADERS,
            )
            
            df = stats.get_data_frames()[0]
            
            team_players = {}
            
            for _, row in df.iterrows():
                team_abbrev = None

                # 1) Prefer TEAM_ABBREVIATION directly (most reliable)
                raw_abbrev = row.get("TEAM_ABBREVIATION")
                if raw_abbrev and str(raw_abbrev).strip() and str(raw_abbrev) != "nan":
                    team_abbrev = str(raw_abbrev).strip().upper()

                # 2) Fallback to TEAM_ID mapping, but cast safely
                if not team_abbrev:
                    team_id = row.get("TEAM_ID", None)
                    try:
                        if team_id is not None and str(team_id) != "nan":
                            team_id_int = int(float(team_id))
                            team_abbrev = TEAM_ID_TO_ABBREV.get(team_id_int)
                    except Exception:
                        team_abbrev = None

                if not team_abbrev:
                    continue
                
                mpg = float(row.get("MIN", 0) or 0)
                ppg = float(row.get("PTS", 0) or 0)
                
                # Calculate points per minute
                ppm = ppg / mpg if mpg > 0 else 0
                
                # Impact score: minutes * points_per_minute
                # This weights both playing time and scoring efficiency
                impact = mpg * ppm
                
                player = PlayerImpact(
                    player_name=row.get("PLAYER_NAME", "Unknown"),
                    team=team_abbrev,
                    minutes_per_game=mpg,
                    points_per_game=ppg,
                    usage_pct=float(row.get("USG_PCT", 0) or 0) * 100 if row.get("USG_PCT") else 20.0,
                    impact_score=impact,
                    is_key_player=False,  # Will be set later
                )
                
                if team_abbrev not in team_players:
                    team_players[team_abbrev] = []
                team_players[team_abbrev].append(player)
            
            # Mark top 6 players by impact as key players, top 2 as stars
            for team, players in team_players.items():
                players.sort(key=lambda p: p.impact_score, reverse=True)
                for i, player in enumerate(players):
                    player.impact_rank = i + 1
                    if i < 6:
                        player.is_key_player = True
                    if i < 2:
                        player.is_star = True
            
            print(f"  Loaded player stats for {len(team_players)} teams.")

            if len(team_players) < 20:
                print(f"  ⚠ WARNING: Only {len(team_players)} teams returned from LeagueDashPlayerStats. Team mapping may be failing.")
                # Print a small sample of missing common teams
                for t in ["BOS", "LAL", "GSW", "NYK"]:
                    if t not in team_players:
                        print(f"  ⚠ Missing team in player stats: {t}")

            return team_players
            
        except Exception as e:
            print(f"  Player stats attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    print("  Using fallback player data...")
    return get_fallback_player_stats()


def get_fallback_team_players(team: str) -> list[PlayerImpact]:
    """
    Return fallback player stats for a single team.
    Creates generic key players with decreasing impact.
    """
    players = []
    for i in range(6):
        impact = 15.0 - i * 2  # 15, 13, 11, 9, 7, 5
        players.append(PlayerImpact(
            player_name=f"{team} Player {i+1}",
            team=team,
            minutes_per_game=32 - i * 4,
            points_per_game=20 - i * 3,
            usage_pct=25 - i * 2,
            impact_score=impact,
            is_key_player=True,
            impact_rank=i + 1,
            is_star=(i < 2),  # Top 2 are stars
        ))
    return players


def get_fallback_player_stats(teams: list[str] | None = None) -> dict[str, list[PlayerImpact]]:
    """
    Return fallback player stats when API fails.
    Creates generic key players for each team.

    Args:
        teams: Optional list of team abbreviations. If None, all 30 NBA teams.
    """
    if teams is None:
        teams = [
            "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
            "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
            "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
        ]
    
    team_players = {}
    for team in teams:
        team_players[team] = get_fallback_team_players(team)
    
    return team_players


def ensure_team_players(
    player_stats: dict[str, list[PlayerImpact]],
    needed_teams: list[str],
) -> dict[str, list[PlayerImpact]]:
    """
    Ensure all needed teams have player data, filling in fallback for missing ones.

    Args:
        player_stats: Dict mapping team abbreviation to list of PlayerImpact.
        needed_teams: List of team abbreviations that must be present.

    Returns:
        The same dict, with missing teams filled in with fallback data.
    """
    for team in needed_teams:
        if not player_stats.get(team):
            print(f"  ⚠ Player stats missing for {team}, using fallback roster data.")
            player_stats[team] = get_fallback_team_players(team)
    return player_stats


def calculate_team_availability(
    team: str,
    players: list[PlayerImpact],
    injuries: list,
) -> tuple[float, dict]:
    """
    Calculate team availability score based on injuries.
    
    Args:
        team: Team abbreviation.
        players: List of PlayerImpact for the team.
        injuries: List of InjuryRow objects.
    
    Returns:
        Tuple of (availability_score, details_dict)
    """
    # Injury status multipliers
    MULTIPLIERS = {
        "Out": 0.0,
        "Doubtful": 0.25,
        "Questionable": 0.6,
        "Probable": 0.85,
        "Available": 1.0,
    }
    
    # Get injuries for this team
    team_injuries = {
        _normalize_name(i.player): i.status 
        for i in injuries 
        if i.team == team
    }
    
    total_impact = 0.0
    available_impact = 0.0
    affected_players = []
    
    key_players = [p for p in players if p.is_key_player]
    
    for player in key_players:
        impact = player.impact_score
        total_impact += impact
        
        # Check if player is injured
        player_norm = _normalize_name(player.player_name)
        status = None
        
        for inj_name, inj_status in team_injuries.items():
            if _names_match(player_norm, inj_name):
                status = inj_status
                break
        
        if status:
            mult = MULTIPLIERS.get(status, 1.0)
            affected_players.append(f"{player.player_name}:{status}")
        else:
            mult = 1.0
        
        available_impact += impact * mult
    
    if total_impact > 0:
        availability = available_impact / total_impact
    else:
        availability = 1.0
    
    details = {
        "total_impact": total_impact,
        "available_impact": available_impact,
        "affected_players": affected_players,
    }
    
    return availability, details


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
    
    # Check if last names match
    if words1[-1] == words2[-1]:
        return True
    
    # Check for any 2+ matching words
    matching = set(words1) & set(words2)
    return len(matching) >= 2
