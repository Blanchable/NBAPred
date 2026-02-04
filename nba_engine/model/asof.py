"""
As-Of Stats Computation for NBA Prediction Engine.

Computes team and player statistics as of a specific date without data leakage.
This ensures historical predictions only use data that would have been available
before the games on that date.

Key principle: For date D, use only games completed before D (not including D itself).
"""

import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

# Import utils
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.dates import format_date, parse_date, get_eastern_date, get_season_for_date
from utils.storage import load_cache, save_cache


# Retry configuration for API calls
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # Exponential backoff


def api_call_with_retry(func: Callable, *args, **kwargs) -> Any:
    """
    Execute an API call with retry logic.
    
    Args:
        func: The function to call
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
        
    Returns:
        Result of func
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"    API call failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"    API call failed after {MAX_RETRIES} attempts")
    
    raise last_exception


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
        from nba_api.stats.static import teams as static_teams
    except ImportError:
        print("  Warning: nba_api not available")
        return []
    
    # Log date in YYYY-MM-DD format for consistency
    log_date = target_date.strftime("%Y-%m-%d")
    # API expects MM/DD/YYYY format
    api_date = target_date.strftime("%m/%d/%Y")
    
    # Build team ID to abbreviation mapping
    id_to_abbrev = {t["id"]: t["abbreviation"] for t in static_teams.get_teams()}
    
    try:
        time.sleep(0.6)
        
        # Use retry logic for API call
        def fetch_scoreboard():
            return ScoreboardV2(game_date=api_date, timeout=60)
        
        scoreboard = api_call_with_retry(fetch_scoreboard)
        games_df = scoreboard.get_data_frames()[0]  # GameHeader
        
        print(f"  ScoreboardV2 returned {len(games_df)} games for {api_date}")
        
        games = []
        for _, row in games_df.iterrows():
            game_id = str(row.get('GAME_ID', '') or '')
            
            # Use team IDs and map to abbreviations
            home_id = int(row.get('HOME_TEAM_ID', 0) or 0)
            away_id = int(row.get('VISITOR_TEAM_ID', 0) or 0)
            
            home_abbrev = id_to_abbrev.get(home_id, '')
            away_abbrev = id_to_abbrev.get(away_id, '')
            
            if not home_abbrev or not away_abbrev:
                print(f"    Skipping game {game_id}: missing team mapping (home_id={home_id}, away_id={away_id})")
                continue
            
            # Get game time if available
            game_time_utc = str(row.get('GAME_DATE_EST', '') or '')  # Usually has datetime
            game_time_et = str(row.get('GAME_STATUS_TEXT', '') or '')
            
            game = {
                'game_id': game_id,
                'game_date': log_date,
                'home_team': home_abbrev,
                'away_team': away_abbrev,
                'game_status': game_time_et,
                'game_time_utc': game_time_utc,
            }
            games.append(game)
        
        # Debug: print first 3 games
        if games:
            print(f"  Sample games: {games[:3]}")
        
        return games
        
    except Exception as e:
        print(f"  Warning: Failed to fetch schedule for {api_date}: {e}")
        import traceback
        traceback.print_exc()
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
        from nba_api.stats.static import teams as static_teams
    except ImportError:
        print("  Warning: nba_api not available")
        return {}
    
    # Log date in YYYY-MM-DD format for key consistency
    log_date = target_date.strftime("%Y-%m-%d")
    # API expects MM/DD/YYYY format
    api_date = target_date.strftime("%m/%d/%Y")
    
    # Build team ID to abbreviation mapping
    id_to_abbrev = {t["id"]: t["abbreviation"] for t in static_teams.get_teams()}
    
    try:
        time.sleep(0.6)
        
        # Use retry logic for API call
        def fetch_scoreboard():
            return ScoreboardV2(game_date=api_date, timeout=60)
        
        scoreboard = api_call_with_retry(fetch_scoreboard)
        
        # Get game header and line score
        games_df = scoreboard.get_data_frames()[0]  # GameHeader
        line_df = scoreboard.get_data_frames()[1]   # LineScore
        
        results = {}
        
        for _, game_row in games_df.iterrows():
            game_id = str(game_row.get('GAME_ID', '') or '')
            status = str(game_row.get('GAME_STATUS_TEXT', '') or '')
            
            # Only process Final games
            if 'Final' not in status:
                continue
            
            # Use team IDs and map to abbreviations
            home_id = int(game_row.get('HOME_TEAM_ID', 0) or 0)
            away_id = int(game_row.get('VISITOR_TEAM_ID', 0) or 0)
            
            home_abbrev = id_to_abbrev.get(home_id, '')
            away_abbrev = id_to_abbrev.get(away_id, '')
            
            if not home_abbrev or not away_abbrev:
                continue
            
            # Get scores from LineScore - use TEAM_ABBREVIATION which is available
            game_lines = line_df[line_df['GAME_ID'] == game_id]
            
            if len(game_lines) >= 2:
                home_score = 0
                away_score = 0
                
                for _, line in game_lines.iterrows():
                    team_abbrev = str(line.get('TEAM_ABBREVIATION', '') or '')
                    pts = int(line.get('PTS', 0) or 0)
                    
                    if team_abbrev == home_abbrev:
                        home_score = pts
                    elif team_abbrev == away_abbrev:
                        away_score = pts
                
                if home_score > 0 or away_score > 0:
                    winner = home_abbrev if home_score > away_score else away_abbrev
                    # Key format must match what storage.update_results_in_log expects
                    key = f"{log_date}|{home_abbrev}|{away_abbrev}"
                    results[key] = winner
        
        print(f"  Found {len(results)} final games for {log_date}")
        return results
        
    except Exception as e:
        print(f"  Warning: Failed to fetch results for {api_date}: {e}")
        import traceback
        traceback.print_exc()
        return {}


def get_first_game_time(games: List[Dict[str, Any]], target_date: date) -> datetime:
    """
    Get the start time of the first game on a date.
    
    Used to determine the cutoff time for historical injury reports.
    
    Args:
        games: List of game dicts from get_asof_schedule
        target_date: The target date
        
    Returns:
        datetime of first game (defaults to 7 PM ET if not available)
    """
    import pytz
    
    eastern = pytz.timezone('US/Eastern')
    
    # Default to 7 PM ET on game day (typical first game time)
    default_time = eastern.localize(datetime(
        target_date.year, target_date.month, target_date.day,
        19, 0, 0  # 7:00 PM ET
    ))
    
    if not games:
        return default_time
    
    # Try to parse game times from the schedule
    earliest = None
    
    for game in games:
        game_time_str = game.get('game_time_utc', '')
        
        if game_time_str:
            try:
                # Try parsing ISO format
                if 'T' in game_time_str:
                    dt = datetime.fromisoformat(game_time_str.replace('Z', '+00:00'))
                    dt_eastern = dt.astimezone(eastern)
                else:
                    # Try parsing date format
                    dt = datetime.strptime(game_time_str[:19], '%Y-%m-%dT%H:%M:%S')
                    dt_eastern = eastern.localize(dt)
                
                if earliest is None or dt_eastern < earliest:
                    earliest = dt_eastern
            except (ValueError, TypeError):
                continue
    
    return earliest if earliest else default_time


def get_historical_injury_report(
    target_date: date,
    first_game_time: datetime = None,
    hours_before: float = 1.0,
) -> tuple:
    """
    Get the injury report that would have been available before games on a date.
    
    Args:
        target_date: Date to get injury report for
        first_game_time: Time of first game (defaults to 7 PM ET)
        hours_before: Hours before first game to set cutoff (default 1)
        
    Returns:
        Tuple of (injuries_list, injury_url, injury_report_available)
    """
    import pytz
    from ingest.injuries import find_injury_pdf_for_date, download_injury_pdf, parse_injury_pdf
    
    eastern = pytz.timezone('US/Eastern')
    
    # Default first game time to 7 PM ET
    if first_game_time is None:
        first_game_time = eastern.localize(datetime(
            target_date.year, target_date.month, target_date.day,
            19, 0, 0
        ))
    
    # Calculate cutoff time (1 hour before first game)
    cutoff_time = first_game_time - timedelta(hours=hours_before)
    
    print(f"  Looking for injury report before {cutoff_time.strftime('%Y-%m-%d %I:%M %p ET')}")
    
    # Find injury report
    injury_url = find_injury_pdf_for_date(
        target_date=first_game_time,
        cutoff_time=cutoff_time,
        max_hours_back=24,
    )
    
    if not injury_url:
        print(f"  No injury report found for {target_date}")
        return [], None, False
    
    print(f"  Found injury report: {injury_url}")
    
    # Download and parse
    try:
        pdf_bytes = download_injury_pdf(injury_url)
        if pdf_bytes:
            injuries = parse_injury_pdf(pdf_bytes)
            print(f"  Parsed {len(injuries)} injury entries")
            return injuries, injury_url, True
        else:
            print(f"  Failed to download injury report")
            return [], injury_url, False
    except Exception as e:
        print(f"  Error parsing injury report: {e}")
        return [], injury_url, False


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
