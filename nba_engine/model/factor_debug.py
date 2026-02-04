"""
Factor Debug Module - Provenance tracking for factor computations.

Provides debug mode logging and data source tracking to help identify
when home/away stats are using fallback values or identical data.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import copy

# Debug flag - can be set via environment variable
DEBUG_FACTORS = os.environ.get("DEBUG_FACTORS", "false").lower() == "true"


class DataSource(Enum):
    """Source of data for a stat value."""
    API_LIVE = "api_live"
    API_SEASON = "api_season"
    FALLBACK_TEAM = "fallback_team"
    FALLBACK_LEAGUE_AVG = "fallback_league_avg"
    COMPUTED = "computed"
    UNKNOWN = "unknown"


@dataclass
class StatProvenance:
    """Tracks where a stat value came from."""
    stat_name: str
    raw_value: float
    source: DataSource
    fallback_used: bool = False
    team: str = ""
    
    def __repr__(self) -> str:
        fb = " (FALLBACK)" if self.fallback_used else ""
        return f"{self.stat_name}={self.raw_value:.4f} [{self.source.value}]{fb}"


@dataclass
class FactorDebugInfo:
    """Debug information for a single factor computation."""
    factor_name: str
    home_team: str
    away_team: str
    home_raw: float
    away_raw: float
    home_source: DataSource
    away_source: DataSource
    home_fallback: bool
    away_fallback: bool
    signed_value: float
    contribution: float
    inputs_description: str = ""
    
    def to_log_line(self) -> str:
        """Format as debug log line."""
        return (
            f"[FACTOR_DEBUG] {self.factor_name:20s} | "
            f"HOME {self.home_team} raw={self.home_raw:+.4f} src={self.home_source.value:15s} | "
            f"AWAY {self.away_team} raw={self.away_raw:+.4f} src={self.away_source.value:15s} | "
            f"fallback(H/A)={str(self.home_fallback).lower()}/{str(self.away_fallback).lower()} | "
            f"signed={self.signed_value:+.4f} | contrib={self.contribution:+.2f}"
        )
    
    @property
    def values_identical(self) -> bool:
        """Check if home and away raw values are identical."""
        return abs(self.home_raw - self.away_raw) < 1e-9
    
    @property
    def both_fallback(self) -> bool:
        """Check if both sides used fallback."""
        return self.home_fallback and self.away_fallback


@dataclass
class StatsWithProvenance:
    """Stats dictionary with provenance tracking."""
    team: str
    stats: dict[str, float] = field(default_factory=dict)
    sources: dict[str, DataSource] = field(default_factory=dict)
    fallbacks: dict[str, bool] = field(default_factory=dict)
    
    def get(self, key: str, default: float = 0.0) -> float:
        """Get stat value, tracking if fallback is used."""
        if key in self.stats:
            return self.stats[key]
        # Using fallback
        self.fallbacks[key] = True
        self.sources[key] = DataSource.FALLBACK_LEAGUE_AVG
        self.stats[key] = default
        return default
    
    def get_with_source(self, key: str, default: float = 0.0) -> tuple[float, DataSource, bool]:
        """Get stat value with source info."""
        if key in self.stats:
            source = self.sources.get(key, DataSource.UNKNOWN)
            fallback = self.fallbacks.get(key, False)
            return self.stats[key], source, fallback
        # Using fallback
        return default, DataSource.FALLBACK_LEAGUE_AVG, True
    
    def set(self, key: str, value: float, source: DataSource = DataSource.API_SEASON) -> None:
        """Set stat value with source."""
        self.stats[key] = value
        self.sources[key] = source
        self.fallbacks[key] = False
    
    @classmethod
    def from_dict(cls, team: str, d: dict, source: DataSource = DataSource.API_SEASON) -> 'StatsWithProvenance':
        """Create from plain dict, marking all values with given source."""
        obj = cls(team=team)
        for key, value in d.items():
            if isinstance(value, (int, float)):
                obj.stats[key] = float(value)
                obj.sources[key] = source
                obj.fallbacks[key] = False
            elif value is not None:
                try:
                    obj.stats[key] = float(value)
                    obj.sources[key] = source
                    obj.fallbacks[key] = False
                except (ValueError, TypeError):
                    pass
        return obj


def log_factor_debug(info: FactorDebugInfo) -> None:
    """Log factor debug info if debug mode is enabled."""
    if DEBUG_FACTORS:
        print(info.to_log_line())


def validate_distinct_stats(
    home_team: str,
    away_team: str,
    home_stats: dict,
    away_stats: dict,
) -> list[str]:
    """
    Validate that home and away stats are distinct.
    
    Returns list of warning messages if issues found.
    """
    warnings = []
    
    # Check for same object reference
    if id(home_stats) == id(away_stats):
        warnings.append(
            f"CRITICAL: home_stats and away_stats are the SAME OBJECT! "
            f"id={id(home_stats)}"
        )
    
    # Check for same team
    home_team_in_stats = home_stats.get('team', '')
    away_team_in_stats = away_stats.get('team', '')
    
    if home_team_in_stats and away_team_in_stats:
        if home_team_in_stats == away_team_in_stats:
            warnings.append(
                f"CRITICAL: Both stats have same team identifier: {home_team_in_stats}"
            )
    
    # Check for suspicious number of identical values
    comparable_keys = [
        'efg_pct', 'tov_pct', 'oreb_pct', 'ft_rate', 'fg3_pct', 'fg3a_rate',
        'opp_efg_pct', 'pace', 'off_rating', 'def_rating', 'net_rating'
    ]
    
    identical_count = 0
    for key in comparable_keys:
        home_val = home_stats.get(key)
        away_val = away_stats.get(key)
        if home_val is not None and away_val is not None:
            if abs(float(home_val) - float(away_val)) < 1e-9:
                identical_count += 1
    
    if len(comparable_keys) > 0:
        identical_pct = identical_count / len(comparable_keys)
        if identical_pct > 0.7:
            warnings.append(
                f"WARNING: {identical_count}/{len(comparable_keys)} stats are identical "
                f"between {home_team} and {away_team} ({identical_pct:.0%}). "
                f"Likely using fallback/default values."
            )
    
    return warnings


def ensure_distinct_copies(
    home_stats: dict,
    away_stats: dict,
) -> tuple[dict, dict]:
    """
    Ensure home and away stats are distinct deep copies.
    
    This prevents shared reference bugs.
    """
    return copy.deepcopy(home_stats), copy.deepcopy(away_stats)


def count_identical_factors(debug_infos: list[FactorDebugInfo]) -> dict:
    """
    Count statistics about identical factors.
    
    Returns dict with counts and percentages.
    """
    total = len(debug_infos)
    if total == 0:
        return {'total': 0, 'identical': 0, 'pct_identical': 0.0}
    
    # Exclude factors that are always neutral (coaching, motivation, home_court)
    excluded = {'coaching', 'motivation', 'home_court'}
    
    comparable = [d for d in debug_infos if d.factor_name not in excluded]
    comparable_total = len(comparable)
    
    if comparable_total == 0:
        return {'total': total, 'comparable': 0, 'identical': 0, 'pct_identical': 0.0}
    
    identical = sum(1 for d in comparable if d.values_identical)
    both_fallback = sum(1 for d in comparable if d.both_fallback)
    
    return {
        'total': total,
        'comparable': comparable_total,
        'identical': identical,
        'pct_identical': identical / comparable_total * 100,
        'both_fallback': both_fallback,
        'pct_fallback': both_fallback / comparable_total * 100 if comparable_total > 0 else 0,
    }


# Global storage for debug info during a prediction run
_current_run_debug: list[FactorDebugInfo] = []


def clear_debug_info() -> None:
    """Clear accumulated debug info."""
    global _current_run_debug
    _current_run_debug = []


def add_debug_info(info: FactorDebugInfo) -> None:
    """Add debug info to current run."""
    global _current_run_debug
    _current_run_debug.append(info)
    log_factor_debug(info)


def get_debug_summary() -> dict:
    """Get summary of current run's debug info."""
    global _current_run_debug
    return count_identical_factors(_current_run_debug)


def get_all_debug_info() -> list[FactorDebugInfo]:
    """Get all debug info from current run."""
    global _current_run_debug
    return list(_current_run_debug)
