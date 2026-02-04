"""
As-Of Stats Computation for NBA Prediction Engine.

Computes team and player statistics as of a specific date without data leakage.
This ensures historical predictions only use data that would have been available
before the games on that date.

Key principle: For date D, use only games completed before D (not including D itself).
"""

import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import utils
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dates import format_date, parse_date, get_eastern_date, get_season_for_date
from utils.storage import load_cache, save_cache


@dataclass
class AsOfTeamStats:
    """Team statistics as of a specific date."""
    team: str
    as_of_date: str
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    
    # Ratings
    off_rating: float = 110.0
    def_rating: float = 110.0
    net_rating: float = 0.0
    
    # Splits
    home_net_rating: float = 0.0
    road_net_rating: float = 0.0
    
    # Recent form
    last_5_net: float = 0.0
    last_15_net: float = 0.0
    
    # Advanced
    pace: float = 100.0
    efg_pct: float = 0.52
    tov_pct: float = 14.0
    oreb_pct: float = 25.0
    ft_rate: float = 0.25
    fg3_pct: float = 0.36
    fg3a_rate: float = 0.40
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AsOfPlayerStats:
    """Player statistics as of a specific date."""
    player_id: str
    player_name: str
    team: str
    as_of_date: str
    games_played: int = 0
    minutes_per_game: float = 0.0
    points_per_game: float = 0.0
    assists_per_game: float = 0.0
    rebounds_per_game: float = 0.0
    impact_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_asof_team_stats(
    target_date: date,
    use_cache: bool = True,
) -> Dict[str, AsOfTeamStats]:
    """
    Get team statistics as of a specific date.
    
    Stats are computed using only games completed before target_date.
    
    Args:
        target_date: Date to compute stats as of
        use_cache: Whether to use/save cache
        
    Returns:
        Dict mapping team abbreviation to AsOfTeamStats
    """
    date_str = format_date(target_date)
    
    # Check cache
    if use_cache:
        cached = load_cache("team_stats_asof", date_str.replace("-", ""))
        if cached:
            print(f"  Using cached team stats for {date_str}")
            return {k: AsOfTeamStats(**v) for k, v in cached.items()}
    
    print(f"  Computing team stats as of {date_str}...")
    
    # Try to fetch from NBA API with date filter
    stats = _fetch_team_stats_asof(target_date)
    
    if stats and use_cache:
        # Save to cache
        cache_data = {k: v.to_dict() for k, v in stats.items()}
        save_cache("team_stats_asof", date_str.replace("-", ""), cache_data)
    
    return stats


def _fetch_team_stats_asof(target_date: date) -> Dict[str, AsOfTeamStats]:
    """
    Fetch team statistics from NBA API as of a specific date.
    
    Uses the DateTo parameter to limit stats to games before target_date.
    """
    try:
        from nba_api.stats.endpoints import LeagueDashTeamStats
        from nba_api.stats.static import teams
    except ImportError:
        print("  Warning: nba_api not available, using fallback stats")
        return _get_fallback_team_stats(target_date)
    
    # Get season for the date
    season = get_season_for_date(target_date)
    
    # Format date for API (MM/DD/YYYY)
    # DateTo should be the day BEFORE target_date (exclusive)
    day_before = target_date - timedelta(days=1)
    date_to = day_before.strftime("%m/%d/%Y")
    
    result = {}
    
    try:
        # Fetch overall stats
        time.sleep(0.6)  # Rate limit
        overall = LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",
            date_to_nullable=date_to,
            per_mode_detailed="PerGame",
        )
        overall_df = overall.get_data_frames()[0]
        
        # Fetch home stats
        time.sleep(0.6)
        home = LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",
            date_to_nullable=date_to,
            per_mode_detailed="PerGame",
            location_nullable="Home",
        )
        home_df = home.get_data_frames()[0]
        
        # Fetch road stats
        time.sleep(0.6)
        road = LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",
            date_to_nullable=date_to,
            per_mode_detailed="PerGame",
            location_nullable="Road",
        )
        road_df = road.get_data_frames()[0]
        
        # Build team abbreviation lookup
        nba_teams = {t['id']: t['abbreviation'] for t in teams.get_teams()}
        
        # Process overall stats
        for _, row in overall_df.iterrows():
            team_id = row.get('TEAM_ID')
            abbrev = nba_teams.get(team_id, '')
            
            if not abbrev:
                continue
            
            # Calculate ratings
            pts = float(row.get('PTS', 0) or 0)
            opp_pts = float(row.get('OPP_PTS', pts) if 'OPP_PTS' in row else pts)
            games = int(row.get('GP', 0) or 0)
            
            # Approximate ratings from per-game stats
            off_rating = pts * 100 / float(row.get('PACE', 100) or 100) if row.get('PACE') else 110.0
            
            # Use actual NET_RATING if available
            net_rating = float(row.get('NET_RATING', 0) or 0)
            if net_rating == 0 and games > 0:
                net_rating = (pts - opp_pts) / games * 2  # Rough approximation
            
            # Get advanced stats
            stats_obj = AsOfTeamStats(
                team=abbrev,
                as_of_date=format_date(target_date),
                games_played=games,
                wins=int(row.get('W', 0) or 0),
                losses=int(row.get('L', 0) or 0),
                off_rating=float(row.get('OFF_RATING', 110) or 110),
                def_rating=float(row.get('DEF_RATING', 110) or 110),
                net_rating=net_rating,
                pace=float(row.get('PACE', 100) or 100),
                efg_pct=float(row.get('EFG_PCT', 0.52) or 0.52),
                tov_pct=float(row.get('TOV_PCT', 14) or 14),
                oreb_pct=float(row.get('OREB_PCT', 25) or 25),
                ft_rate=float(row.get('FTA', 20) or 20) / max(float(row.get('FGA', 80) or 80), 1),
                fg3_pct=float(row.get('FG3_PCT', 0.36) or 0.36),
                fg3a_rate=float(row.get('FG3A', 30) or 30) / max(float(row.get('FGA', 80) or 80), 1),
            )
            
            result[abbrev] = stats_obj
        
        # Add home/road splits
        home_nets = {}
        for _, row in home_df.iterrows():
            team_id = row.get('TEAM_ID')
            abbrev = nba_teams.get(team_id, '')
            if abbrev:
                home_nets[abbrev] = float(row.get('NET_RATING', 0) or 0)
        
        road_nets = {}
        for _, row in road_df.iterrows():
            team_id = row.get('TEAM_ID')
            abbrev = nba_teams.get(team_id, '')
            if abbrev:
                road_nets[abbrev] = float(row.get('NET_RATING', 0) or 0)
        
        for abbrev, stats in result.items():
            stats.home_net_rating = home_nets.get(abbrev, stats.net_rating + 2)
            stats.road_net_rating = road_nets.get(abbrev, stats.net_rating - 2)
        
        print(f"  Loaded as-of stats for {len(result)} teams")
        return result
        
    except Exception as e:
        print(f"  Warning: Failed to fetch as-of stats: {e}")
        return _get_fallback_team_stats(target_date)


def _get_fallback_team_stats(target_date: date) -> Dict[str, AsOfTeamStats]:
    """Generate fallback team stats when API fails."""
    # All 30 NBA teams with neutral ratings
    teams = [
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"
    ]
    
    result = {}
    for team in teams:
        result[team] = AsOfTeamStats(
            team=team,
            as_of_date=format_date(target_date),
            games_played=0,
            off_rating=110.0,
            def_rating=110.0,
            net_rating=0.0,
            home_net_rating=2.0,
            road_net_rating=-2.0,
        )
    
    return result


def get_asof_player_stats(
    target_date: date,
    use_cache: bool = True,
) -> Dict[str, List[AsOfPlayerStats]]:
    """
    Get player statistics as of a specific date.
    
    Args:
        target_date: Date to compute stats as of
        use_cache: Whether to use/save cache
        
    Returns:
        Dict mapping team abbreviation to list of AsOfPlayerStats
    """
    date_str = format_date(target_date)
    
    # Check cache
    if use_cache:
        cached = load_cache("player_stats_asof", date_str.replace("-", ""))
        if cached:
            print(f"  Using cached player stats for {date_str}")
            result = {}
            for team, players in cached.items():
                result[team] = [AsOfPlayerStats(**p) for p in players]
            return result
    
    print(f"  Computing player stats as of {date_str}...")
    
    stats = _fetch_player_stats_asof(target_date)
    
    if stats and use_cache:
        cache_data = {k: [p.to_dict() for p in v] for k, v in stats.items()}
        save_cache("player_stats_asof", date_str.replace("-", ""), cache_data)
    
    return stats


def _fetch_player_stats_asof(target_date: date) -> Dict[str, List[AsOfPlayerStats]]:
    """Fetch player statistics from NBA API as of a specific date."""
    try:
        from nba_api.stats.endpoints import LeagueDashPlayerStats
        from nba_api.stats.static import teams
    except ImportError:
        print("  Warning: nba_api not available, using fallback player stats")
        return {}
    
    season = get_season_for_date(target_date)
    day_before = target_date - timedelta(days=1)
    date_to = day_before.strftime("%m/%d/%Y")
    
    result = {}
    
    try:
        time.sleep(0.6)
        players = LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Regular Season",
            date_to_nullable=date_to,
            per_mode_detailed="PerGame",
        )
        players_df = players.get_data_frames()[0]
        
        nba_teams = {t['id']: t['abbreviation'] for t in teams.get_teams()}
        
        for _, row in players_df.iterrows():
            team_id = row.get('TEAM_ID')
            team_abbrev = nba_teams.get(team_id, '')
            
            if not team_abbrev:
                continue
            
            ppg = float(row.get('PTS', 0) or 0)
            apg = float(row.get('AST', 0) or 0)
            mpg = float(row.get('MIN', 0) or 0)
            
            player = AsOfPlayerStats(
                player_id=str(row.get('PLAYER_ID', '')),
                player_name=str(row.get('PLAYER_NAME', '')),
                team=team_abbrev,
                as_of_date=format_date(target_date),
                games_played=int(row.get('GP', 0) or 0),
                minutes_per_game=mpg,
                points_per_game=ppg,
                assists_per_game=apg,
                rebounds_per_game=float(row.get('REB', 0) or 0),
                impact_score=ppg + 0.7 * apg,
            )
            
            if team_abbrev not in result:
                result[team_abbrev] = []
            result[team_abbrev].append(player)
        
        # Sort each team's players by impact score
        for team in result:
            result[team].sort(key=lambda p: p.impact_score, reverse=True)
        
        print(f"  Loaded as-of player stats for {len(result)} teams")
        return result
        
    except Exception as e:
        print(f"  Warning: Failed to fetch as-of player stats: {e}")
        return {}


def get_asof_schedule(target_date: date) -> List[Dict[str, Any]]:
    """
    Get NBA games scheduled for a specific date.
    
    Args:
        target_date: Date to get schedule for
        
    Returns:
        List of game dictionaries with home_team, away_team, game_id, etc.
    """
    try:
        from nba_api.stats.endpoints import ScoreboardV2
    except ImportError:
        print("  Warning: nba_api not available")
        return []
    
    date_str = format_date(target_date, "%Y-%m-%d")
    
    try:
        time.sleep(0.6)
        scoreboard = ScoreboardV2(game_date=date_str)
        games_df = scoreboard.get_data_frames()[0]  # GameHeader
        
        games = []
        for _, row in games_df.iterrows():
            game = {
                'game_id': str(row.get('GAME_ID', '')),
                'game_date': date_str,
                'home_team': str(row.get('HOME_TEAM_ABBREVIATION', '') or row.get('HOME_TEAM', '')),
                'away_team': str(row.get('VISITOR_TEAM_ABBREVIATION', '') or row.get('VISITOR_TEAM', '')),
                'game_status': str(row.get('GAME_STATUS_TEXT', '')),
            }
            
            # Only include if we have both teams
            if game['home_team'] and game['away_team']:
                games.append(game)
        
        return games
        
    except Exception as e:
        print(f"  Warning: Failed to fetch schedule for {date_str}: {e}")
        return []


def get_asof_game_results(target_date: date) -> Dict[str, str]:
    """
    Get final results for games on a specific date.
    
    Args:
        target_date: Date to get results for
        
    Returns:
        Dict mapping game unique key to winner abbreviation
    """
    try:
        from nba_api.stats.endpoints import ScoreboardV2
    except ImportError:
        print("  Warning: nba_api not available")
        return {}
    
    date_str = format_date(target_date, "%Y-%m-%d")
    
    try:
        time.sleep(0.6)
        scoreboard = ScoreboardV2(game_date=date_str)
        
        # Get game header and line score
        games_df = scoreboard.get_data_frames()[0]  # GameHeader
        line_df = scoreboard.get_data_frames()[1]   # LineScore
        
        results = {}
        
        for _, game_row in games_df.iterrows():
            game_id = str(game_row.get('GAME_ID', ''))
            home_team = str(game_row.get('HOME_TEAM_ABBREVIATION', '') or '')
            away_team = str(game_row.get('VISITOR_TEAM_ABBREVIATION', '') or '')
            status = str(game_row.get('GAME_STATUS_TEXT', ''))
            
            # Only process Final games
            if 'Final' not in status:
                continue
            
            if not home_team or not away_team:
                continue
            
            # Get scores from LineScore
            game_lines = line_df[line_df['GAME_ID'] == game_id]
            
            if len(game_lines) >= 2:
                home_score = 0
                away_score = 0
                
                for _, line in game_lines.iterrows():
                    team_abbrev = str(line.get('TEAM_ABBREVIATION', ''))
                    pts = int(line.get('PTS', 0) or 0)
                    
                    if team_abbrev == home_team:
                        home_score = pts
                    elif team_abbrev == away_team:
                        away_score = pts
                
                winner = home_team if home_score > away_score else away_team
                key = f"{date_str}|{home_team}|{away_team}"
                results[key] = winner
        
        return results
        
    except Exception as e:
        print(f"  Warning: Failed to fetch results for {date_str}: {e}")
        return {}


def get_data_confidence(
    team_stats_available: bool,
    player_stats_available: bool,
    injury_report_available: bool,
) -> str:
    """
    Determine data confidence level based on available data.
    
    Args:
        team_stats_available: Whether team stats were loaded
        player_stats_available: Whether player stats were loaded
        injury_report_available: Whether injury report was available
        
    Returns:
        Confidence level: "HIGH", "MEDIUM", or "LOW"
    """
    score = 0
    
    if team_stats_available:
        score += 2
    if player_stats_available:
        score += 1
    if injury_report_available:
        score += 1
    
    if score >= 3:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    else:
        return "LOW"
