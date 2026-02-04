"""
Enhanced team statistics module with home/road splits and recent form.

Provides lineup-adjusted, context-aware team strength calculations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import time

from nba_api.stats.endpoints import leaguedashteamstats, teamgamelog
from nba_api.stats.static import teams as nba_teams


# Custom headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
}

# Team abbreviation to ID mapping
TEAM_ABBREV_TO_ID = {team['abbreviation']: team['id'] for team in nba_teams.get_teams()}


@dataclass
class TeamStrength:
    """Comprehensive team strength data."""
    team: str
    
    # Season overall stats
    net_rating: float = 0.0
    off_rating: float = 110.0
    def_rating: float = 110.0
    pace: float = 100.0
    
    # Home/Road splits
    home_net_rating: float = 0.0
    road_net_rating: float = 0.0
    
    # Recent form (net ratings)
    last_15_net: float = 0.0
    last_5_net: float = 0.0
    
    # Blended net rating (season + recent form)
    blended_net_rating: float = 0.0
    
    # Strength of schedule
    sos_adjustment: float = 0.0
    
    # Advanced stats
    efg_pct: float = 0.52
    tov_pct: float = 14.0
    oreb_pct: float = 25.0
    ft_rate: float = 0.25
    fg3_pct: float = 0.36
    fg3a_rate: float = 0.40
    
    # Defense
    opp_efg_pct: float = 0.52
    opp_tov_pct: float = 14.0
    opp_oreb_pct: float = 25.0
    
    # Volatility indicators
    volatility_score: float = 0.5  # 0 = stable, 1 = volatile
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'team': self.team,
            'net_rating': self.net_rating,
            'off_rating': self.off_rating,
            'def_rating': self.def_rating,
            'pace': self.pace,
            'home_net_rating': self.home_net_rating,
            'road_net_rating': self.road_net_rating,
            'last_15_net': self.last_15_net,
            'last_5_net': self.last_5_net,
            'blended_net_rating': self.blended_net_rating,
            'sos_adjustment': self.sos_adjustment,
            'efg_pct': self.efg_pct,
            'tov_pct': self.tov_pct,
            'oreb_pct': self.oreb_pct,
            'ft_rate': self.ft_rate,
            'fg3_pct': self.fg3_pct,
            'fg3a_rate': self.fg3a_rate,
            'opp_efg_pct': self.opp_efg_pct,
            'opp_tov_pct': self.opp_tov_pct,
            'opp_oreb_pct': self.opp_oreb_pct,
            'volatility_score': self.volatility_score,
        }


def get_comprehensive_team_stats(
    season: str = "2024-25",
    timeout: int = 60,
) -> dict[str, TeamStrength]:
    """
    Fetch comprehensive team stats including home/road splits.
    
    Returns:
        Dict mapping team abbreviation to TeamStrength object.
    """
    print("  Fetching comprehensive team stats...")
    
    teams = {}
    
    # 1. Get overall season stats
    overall = _fetch_team_stats(season, location=None, timeout=timeout)
    
    # If API failed, use fallback data
    if not overall:
        print("  API failed, using fallback team data...")
        return get_fallback_team_strength()
    
    # 2. Get home stats (optional - don't fail if this doesn't work)
    home_stats = _fetch_team_stats(season, location="Home", timeout=timeout)
    
    # 3. Get road stats (optional)
    road_stats = _fetch_team_stats(season, location="Road", timeout=timeout)
    
    # Combine into TeamStrength objects
    for abbrev, stats in overall.items():
        ts = TeamStrength(
            team=abbrev,
            net_rating=stats.get('net_rating', 0),
            off_rating=stats.get('off_rating', 110),
            def_rating=stats.get('def_rating', 110),
            pace=stats.get('pace', 100),
            efg_pct=stats.get('efg_pct', 0.52),
            tov_pct=stats.get('tov_pct', 14),
            oreb_pct=stats.get('oreb_pct', 25),
            ft_rate=stats.get('ft_rate', 0.25),
            fg3_pct=stats.get('fg3_pct', 0.36),
            fg3a_rate=stats.get('fg3a_rate', 0.40),
        )
        
        # Add home/road splits
        if abbrev in home_stats:
            ts.home_net_rating = home_stats[abbrev].get('net_rating', ts.net_rating)
        else:
            ts.home_net_rating = ts.net_rating + 2  # Default home boost
        
        if abbrev in road_stats:
            ts.road_net_rating = road_stats[abbrev].get('net_rating', ts.net_rating)
        else:
            ts.road_net_rating = ts.net_rating - 2  # Default road penalty
        
        # Calculate volatility (high 3PAr + high TOV = volatile)
        ts.volatility_score = min(1.0, (ts.fg3a_rate - 0.35) * 2 + (ts.tov_pct - 12) * 0.05)
        ts.volatility_score = max(0.0, ts.volatility_score)
        
        # Initial blended rating (will be updated with recent form)
        ts.blended_net_rating = ts.net_rating
        
        teams[abbrev] = ts
    
    # If we still got 0 teams somehow, use fallback
    if not teams:
        print("  No teams loaded, using fallback data...")
        return get_fallback_team_strength()
    
    print(f"  Loaded stats for {len(teams)} teams.")
    return teams


def _fetch_team_stats(
    season: str,
    location: Optional[str] = None,
    timeout: int = 60,
) -> dict[str, dict]:
    """Fetch team stats, optionally filtered by location."""
    try:
        kwargs = {
            'season': season,
            'season_type_all_star': "Regular Season",
            'per_mode_detailed': "Per100Possessions",
            'timeout': timeout,
            'headers': HEADERS,
        }
        
        if location:
            kwargs['location_nullable'] = location
        
        stats = leaguedashteamstats.LeagueDashTeamStats(**kwargs)
        df = stats.get_data_frames()[0]
        
        result = {}
        for _, row in df.iterrows():
            abbrev = row["TEAM_ABBREVIATION"]
            
            fga = float(row.get("FGA", 80) or 80)
            fg3a = float(row.get("FG3A", 30) or 30)
            fta = float(row.get("FTA", 20) or 20)
            tov = float(row.get("TOV", 14) or 14)
            oreb = float(row.get("OREB", 10) or 10)
            
            # Calculate derived stats
            poss_est = fga + 0.44 * fta + tov
            
            result[abbrev] = {
                'net_rating': float(row.get("NET_RATING", 0) or 0),
                'off_rating': float(row.get("OFF_RATING", 110) or 110),
                'def_rating': float(row.get("DEF_RATING", 110) or 110),
                'pace': float(row.get("PACE", 100) or 100),
                'efg_pct': float(row.get("EFG_PCT", 0.52) or 0.52),
                'tov_pct': (tov / poss_est * 100) if poss_est > 0 else 14.0,
                'oreb_pct': float(row.get("OREB_PCT", 25) or 25) if row.get("OREB_PCT") else 25.0,
                'ft_rate': fta / fga if fga > 0 else 0.25,
                'fg3_pct': float(row.get("FG3_PCT", 0.36) or 0.36),
                'fg3a_rate': fg3a / fga if fga > 0 else 0.40,
            }
        
        return result
        
    except Exception as e:
        print(f"  Stats fetch failed ({location or 'overall'}): {e}")
        return {}


def get_recent_form(
    team: str,
    season: str = "2024-25",
    timeout: int = 30,
) -> tuple[float, float]:
    """
    Get recent form (last 15 and last 5 games net rating proxy).
    
    Returns:
        Tuple of (last_15_net, last_5_net)
    """
    try:
        team_id = TEAM_ABBREV_TO_ID.get(team)
        if not team_id:
            return 0.0, 0.0
        
        game_log = teamgamelog.TeamGameLog(
            team_id=team_id,
            season=season,
            timeout=timeout,
            headers=HEADERS,
        )
        
        df = game_log.get_data_frames()[0]
        
        if len(df) == 0:
            return 0.0, 0.0
        
        # Calculate point differential as net rating proxy
        def calc_net_proxy(games_df):
            if len(games_df) == 0:
                return 0.0
            pts = games_df["PTS"].astype(float).mean()
            # WL column contains W or L
            # We need opponent points - approximate from matchup
            # Simpler: use plus_minus if available
            if "PLUS_MINUS" in games_df.columns:
                return games_df["PLUS_MINUS"].astype(float).mean()
            return 0.0
        
        last_15 = df.head(15)
        last_5 = df.head(5)
        
        last_15_net = calc_net_proxy(last_15)
        last_5_net = calc_net_proxy(last_5)
        
        return last_15_net, last_5_net
        
    except Exception as e:
        return 0.0, 0.0


def calculate_blended_rating(
    season_net: float,
    last_15_net: float,
    last_5_net: float,
    max_shift: float = 3.0,
) -> float:
    """
    Calculate blended net rating from season and recent form.
    
    Blend: 60% season, 30% last 15, 10% last 5
    Cap: Recent form can shift by at most ±3 points.
    """
    # Weighted blend
    blended = 0.6 * season_net + 0.3 * last_15_net + 0.1 * last_5_net
    
    # Apply cap
    shift = blended - season_net
    capped_shift = max(-max_shift, min(max_shift, shift))
    
    return season_net + capped_shift


def calculate_sos_adjustment(
    opp_avg_net: float,
    max_adjustment: float = 2.0,
) -> float:
    """
    Calculate strength of schedule adjustment.
    
    Negative opponent average = easier schedule = reduce rating
    Positive opponent average = harder schedule = boost rating
    """
    adjustment = -(opp_avg_net / 5.0)
    return max(-max_adjustment, min(max_adjustment, adjustment))


def get_team_rest_days(
    teams: list[str],
    season: str = "2024-25",
    timeout: int = 30,
) -> dict[str, int]:
    """
    Get days since last game for each team.
    """
    from datetime import datetime
    
    rest_days = {team: 1 for team in teams}
    today = datetime.now().date()
    
    for team in teams:
        try:
            team_id = TEAM_ABBREV_TO_ID.get(team)
            if not team_id:
                continue
            
            game_log = teamgamelog.TeamGameLog(
                team_id=team_id,
                season=season,
                timeout=timeout,
                headers=HEADERS,
            )
            
            df = game_log.get_data_frames()[0]
            
            if len(df) > 0:
                last_game_str = df.iloc[0]["GAME_DATE"]
                try:
                    last_game = datetime.strptime(last_game_str, "%b %d, %Y").date()
                    days = (today - last_game).days
                    rest_days[team] = max(0, days)
                except:
                    pass
                    
        except Exception:
            pass
    
    return rest_days


# Comprehensive fallback data with per-team advanced stats
# Format: (net, off, def, pace, efg, tov, oreb, ft_rate, fg3, fg3a_rate, opp_efg, opp_tov, opp_oreb)
FALLBACK_TEAM_DATA = {
    # Team: (net_rtg, off_rtg, def_rtg, pace, efg%, tov%, oreb%, ft_rate, fg3%, fg3a_rate, opp_efg%, opp_tov%, opp_oreb%)
    "OKC": (11.0, 118.5, 107.5, 99.2, 0.558, 12.1, 27.8, 0.282, 0.378, 0.425, 0.498, 15.2, 23.1),
    "CLE": (9.6, 117.8, 108.2, 97.5, 0.562, 12.8, 26.2, 0.268, 0.392, 0.418, 0.502, 14.8, 24.5),
    "BOS": (9.4, 120.2, 110.8, 100.8, 0.572, 13.2, 24.8, 0.258, 0.398, 0.468, 0.512, 14.2, 25.2),
    "HOU": (7.3, 113.5, 106.2, 98.8, 0.535, 13.5, 29.5, 0.298, 0.352, 0.402, 0.495, 15.8, 22.8),
    "MEM": (6.3, 115.8, 109.5, 101.2, 0.542, 13.8, 28.2, 0.275, 0.348, 0.385, 0.508, 14.5, 24.2),
    "NYK": (5.7, 116.2, 110.5, 98.2, 0.548, 12.5, 26.8, 0.288, 0.368, 0.398, 0.515, 14.2, 25.8),
    "DEN": (5.3, 116.8, 111.5, 99.5, 0.555, 13.2, 25.5, 0.262, 0.382, 0.392, 0.522, 13.8, 26.2),
    "LAL": (4.7, 114.5, 109.8, 100.5, 0.545, 13.8, 27.2, 0.278, 0.358, 0.405, 0.512, 14.5, 25.5),
    "MIN": (4.3, 112.8, 108.5, 97.8, 0.538, 12.8, 25.8, 0.255, 0.368, 0.412, 0.502, 15.2, 24.8),
    "GSW": (4.0, 115.2, 111.2, 100.2, 0.552, 14.2, 24.2, 0.248, 0.395, 0.445, 0.518, 13.8, 26.5),
    "MIL": (3.6, 114.8, 111.2, 99.8, 0.548, 13.5, 26.5, 0.285, 0.372, 0.408, 0.515, 14.2, 25.2),
    "DAL": (3.3, 116.5, 113.2, 99.2, 0.555, 12.2, 24.8, 0.265, 0.388, 0.438, 0.525, 13.5, 26.8),
    "LAC": (2.7, 113.2, 110.5, 98.5, 0.542, 13.2, 25.2, 0.272, 0.375, 0.415, 0.512, 14.8, 25.5),
    "DET": (2.3, 112.5, 110.2, 98.2, 0.528, 14.2, 28.5, 0.268, 0.342, 0.385, 0.508, 14.2, 24.8),
    "MIA": (1.8, 111.8, 110.0, 97.5, 0.532, 13.8, 26.2, 0.258, 0.362, 0.402, 0.515, 14.5, 25.2),
    "SAC": (1.4, 114.2, 112.8, 101.5, 0.545, 13.5, 25.5, 0.275, 0.378, 0.425, 0.522, 13.2, 26.5),
    "IND": (1.3, 116.8, 115.5, 103.2, 0.552, 13.2, 26.8, 0.282, 0.385, 0.432, 0.532, 13.5, 27.2),
    "PHX": (1.0, 113.5, 112.5, 98.8, 0.538, 13.5, 25.2, 0.268, 0.372, 0.408, 0.518, 14.2, 26.2),
    "ATL": (0.8, 115.0, 114.2, 100.2, 0.542, 14.5, 24.8, 0.265, 0.382, 0.422, 0.528, 13.8, 27.5),
    "ORL": (0.5, 108.5, 108.0, 96.8, 0.518, 13.2, 28.8, 0.245, 0.338, 0.368, 0.498, 15.5, 23.5),
    "SAS": (-0.3, 111.2, 111.5, 99.5, 0.525, 14.8, 27.2, 0.258, 0.352, 0.395, 0.512, 14.2, 25.8),
    "CHI": (-0.7, 111.8, 112.5, 98.8, 0.528, 14.2, 26.5, 0.262, 0.358, 0.398, 0.518, 13.8, 26.2),
    "BKN": (-1.3, 110.5, 111.8, 99.2, 0.522, 14.5, 25.8, 0.255, 0.365, 0.415, 0.522, 14.2, 26.8),
    "POR": (-2.0, 109.2, 111.2, 100.5, 0.518, 15.2, 26.2, 0.248, 0.348, 0.425, 0.528, 13.5, 27.2),
    "TOR": (-2.4, 110.8, 113.2, 99.8, 0.525, 14.8, 25.5, 0.252, 0.362, 0.412, 0.532, 13.8, 27.5),
    "PHI": (-3.0, 109.5, 112.5, 97.2, 0.518, 14.5, 27.5, 0.268, 0.345, 0.388, 0.525, 14.5, 26.5),
    "NOP": (-4.3, 109.2, 113.5, 98.5, 0.515, 15.2, 28.2, 0.255, 0.338, 0.378, 0.535, 14.2, 27.8),
    "CHA": (-6.3, 107.5, 113.8, 100.2, 0.508, 15.8, 27.8, 0.248, 0.332, 0.402, 0.538, 13.2, 28.2),
    "UTA": (-7.3, 108.2, 115.5, 99.8, 0.512, 15.5, 26.8, 0.252, 0.342, 0.418, 0.542, 13.5, 28.5),
    "WAS": (-11.7, 106.5, 118.2, 101.5, 0.498, 16.2, 25.5, 0.245, 0.328, 0.412, 0.555, 12.8, 29.2),
}


def get_fallback_team_strength(team: str = None) -> dict[str, TeamStrength]:
    """
    Return fallback team strength data with full advanced stats.
    
    Args:
        team: If provided, returns dict with only that team. Otherwise returns all teams.
    
    Returns:
        Dict mapping team abbreviation to TeamStrength object with complete stats.
    """
    teams = {}
    
    for abbrev, data in FALLBACK_TEAM_DATA.items():
        if team is not None and abbrev != team:
            continue
            
        (net, off, def_, pace, efg, tov, oreb, ft_rate, 
         fg3, fg3a_rate, opp_efg, opp_tov, opp_oreb) = data
        
        ts = TeamStrength(
            team=abbrev,
            net_rating=net,
            off_rating=off,
            def_rating=def_,
            pace=pace,
            home_net_rating=net + 2,
            road_net_rating=net - 2,
            blended_net_rating=net,
            # Advanced offensive stats
            efg_pct=efg,
            tov_pct=tov,
            oreb_pct=oreb,
            ft_rate=ft_rate,
            fg3_pct=fg3,
            fg3a_rate=fg3a_rate,
            # Defensive stats
            opp_efg_pct=opp_efg,
            opp_tov_pct=opp_tov,
            opp_oreb_pct=opp_oreb,
            # Volatility based on 3PA rate and TOV
            volatility_score=min(1.0, max(0.0, (fg3a_rate - 0.35) * 2 + (tov - 12) * 0.05)),
        )
        teams[abbrev] = ts
    
    if not teams:
        # If team not found in fallback, create with league averages
        print(f"  WARNING: Team '{team}' not in fallback data, using league averages")
        ts = TeamStrength(
            team=team or "UNK",
            net_rating=0.0,
            off_rating=110.0,
            def_rating=110.0,
            pace=99.0,
        )
        teams[team or "UNK"] = ts
    
    return teams
