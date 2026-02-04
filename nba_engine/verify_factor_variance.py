#!/usr/bin/env python3
"""
Factor Variance Verification Script

Verifies that home and away stats are properly distinct for factor calculations.
This script helps diagnose the "identical stats" bug where many factors show
the same value for home and away teams.

Usage:
    python verify_factor_variance.py [--debug] [--n NUM_GAMES]

Options:
    --debug     Enable verbose debug output
    --n NUM     Number of sample games to analyze (default: 10)
"""

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Optional

# Enable debug mode for this script
os.environ["DEBUG_FACTORS"] = "false"  # Start with false, enable via --debug

from model.point_system import score_game_v3, FactorResult
from model.factor_debug import (
    clear_debug_info, get_debug_summary, get_all_debug_info,
    validate_distinct_stats, DataSource,
)
from ingest.team_stats import get_fallback_team_strength, TeamStrength


@dataclass
class GameAnalysis:
    """Analysis results for a single game."""
    home_team: str
    away_team: str
    total_factors: int
    comparable_factors: int
    identical_factors: int
    pct_identical: float
    both_fallback_factors: int
    issues: list[str]


def analyze_game(
    home_team: str,
    away_team: str,
    home_stats: dict,
    away_stats: dict,
    verbose: bool = False,
) -> GameAnalysis:
    """
    Analyze a single game for factor variance issues.
    
    Returns GameAnalysis with statistics about identical factors.
    """
    issues = []
    
    # Check for shared reference
    if id(home_stats) == id(away_stats):
        issues.append("CRITICAL: home_stats and away_stats are same object!")
    
    # Validate stats are distinct
    warnings = validate_distinct_stats(home_team, away_team, home_stats, away_stats)
    issues.extend(warnings)
    
    # Run scoring
    clear_debug_info()
    
    score = score_game_v3(
        home_team=home_team,
        away_team=away_team,
        home_strength=None,
        away_strength=None,
        home_stats=home_stats,
        away_stats=away_stats,
    )
    
    # Analyze factors
    # Exclude factors that are always neutral
    excluded = {'coaching', 'motivation', 'home_court', 'star_impact', 
                'rotation_replacement', 'lineup_net_rating', 'off_vs_def',
                'home_road_split', 'rest_fatigue', 'rim_protection',
                'bench_depth', 'late_game_creation', 'matchup_fit'}
    
    comparable = [f for f in score.factors if f.name not in excluded]
    
    identical_count = 0
    both_fallback_count = 0
    
    for f in comparable:
        if hasattr(f, 'home_raw') and hasattr(f, 'away_raw'):
            if abs(f.home_raw - f.away_raw) < 1e-9:
                identical_count += 1
                if verbose:
                    print(f"  IDENTICAL: {f.name} home={f.home_raw:.4f} away={f.away_raw:.4f}")
            if f.home_fallback and f.away_fallback:
                both_fallback_count += 1
    
    pct_identical = (identical_count / len(comparable) * 100) if comparable else 0
    
    return GameAnalysis(
        home_team=home_team,
        away_team=away_team,
        total_factors=len(score.factors),
        comparable_factors=len(comparable),
        identical_factors=identical_count,
        pct_identical=pct_identical,
        both_fallback_factors=both_fallback_count,
        issues=issues,
    )


def run_verification(n_games: int = 10, verbose: bool = False) -> dict:
    """
    Run verification across multiple simulated games.
    
    Uses fallback data to ensure we have stats for all teams.
    """
    print("=" * 70)
    print("Factor Variance Verification")
    print("=" * 70)
    
    # Get fallback data (this should have per-team variation now)
    all_teams = get_fallback_team_strength()
    team_list = list(all_teams.keys())
    
    if len(team_list) < 2:
        print("ERROR: Not enough teams in fallback data")
        return {'error': 'insufficient teams'}
    
    print(f"\nLoaded {len(team_list)} teams from fallback data")
    print(f"Analyzing {n_games} sample games...\n")
    
    results = []
    
    # Generate sample matchups
    import random
    random.seed(42)  # Reproducible
    
    for i in range(n_games):
        home_team, away_team = random.sample(team_list, 2)
        
        home_ts = all_teams[home_team]
        away_ts = all_teams[away_team]
        
        home_stats = home_ts.to_dict()
        away_stats = away_ts.to_dict()
        
        if verbose:
            print(f"\n--- Game {i+1}: {away_team} @ {home_team} ---")
        
        analysis = analyze_game(home_team, away_team, home_stats, away_stats, verbose)
        results.append(analysis)
        
        status = "PASS" if analysis.pct_identical < 30 else "FAIL"
        print(f"Game {i+1}: {away_team:3s} @ {home_team:3s} | "
              f"Identical: {analysis.identical_factors}/{analysis.comparable_factors} "
              f"({analysis.pct_identical:.0f}%) | {status}")
        
        if analysis.issues:
            for issue in analysis.issues:
                print(f"  ! {issue}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_comparable = sum(r.comparable_factors for r in results)
    total_identical = sum(r.identical_factors for r in results)
    avg_pct_identical = sum(r.pct_identical for r in results) / len(results) if results else 0
    games_with_issues = sum(1 for r in results if r.issues)
    games_passing = sum(1 for r in results if r.pct_identical < 30)
    
    print(f"Games analyzed: {len(results)}")
    print(f"Games passing (<30% identical): {games_passing}/{len(results)} ({games_passing/len(results)*100:.0f}%)")
    print(f"Total comparable factors: {total_comparable}")
    print(f"Total identical factors: {total_identical}")
    print(f"Average % identical: {avg_pct_identical:.1f}%")
    print(f"Games with validation issues: {games_with_issues}")
    
    # Check acceptance criteria
    print("\n" + "-" * 70)
    print("ACCEPTANCE TEST RESULTS")
    print("-" * 70)
    
    # A) At least 70% of games should have < 30% identical factors
    criteria_a_pass = (games_passing / len(results) * 100) >= 70
    print(f"[{'PASS' if criteria_a_pass else 'FAIL'}] A) 70%+ games with diverse factors: "
          f"{games_passing}/{len(results)} ({games_passing/len(results)*100:.0f}%)")
    
    # B) Average identical factors should be < 50%
    criteria_b_pass = avg_pct_identical < 50
    print(f"[{'PASS' if criteria_b_pass else 'FAIL'}] B) Average identical < 50%: {avg_pct_identical:.1f}%")
    
    # C) No critical validation issues
    criteria_c_pass = games_with_issues == 0
    print(f"[{'PASS' if criteria_c_pass else 'FAIL'}] C) No validation issues: {games_with_issues} games with issues")
    
    overall_pass = criteria_a_pass and criteria_b_pass and criteria_c_pass
    print(f"\nOVERALL: {'PASS' if overall_pass else 'FAIL'}")
    
    return {
        'games_analyzed': len(results),
        'games_passing': games_passing,
        'avg_pct_identical': avg_pct_identical,
        'games_with_issues': games_with_issues,
        'overall_pass': overall_pass,
        'results': results,
    }


def verify_team_data_variance():
    """
    Verify that fallback team data has variance across teams.
    """
    print("\n" + "=" * 70)
    print("Team Data Variance Check")
    print("=" * 70)
    
    teams = get_fallback_team_strength()
    
    stats_to_check = ['efg_pct', 'tov_pct', 'oreb_pct', 'ft_rate', 'fg3_pct', 
                      'fg3a_rate', 'pace', 'opp_efg_pct']
    
    for stat in stats_to_check:
        values = []
        for team, ts in teams.items():
            d = ts.to_dict()
            if stat in d:
                values.append(d[stat])
        
        if values:
            min_val = min(values)
            max_val = max(values)
            spread = max_val - min_val
            unique = len(set(values))
            
            status = "OK" if unique > 1 and spread > 0.001 else "WARN"
            print(f"[{status}] {stat:12s}: min={min_val:.4f} max={max_val:.4f} "
                  f"spread={spread:.4f} unique={unique}/{len(values)}")


def main():
    parser = argparse.ArgumentParser(description="Verify factor variance")
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--n', type=int, default=10, help='Number of games to analyze')
    args = parser.parse_args()
    
    if args.debug:
        os.environ["DEBUG_FACTORS"] = "true"
    
    # First check team data variance
    verify_team_data_variance()
    
    # Then run full verification
    results = run_verification(n_games=args.n, verbose=args.debug)
    
    sys.exit(0 if results.get('overall_pass', False) else 1)


if __name__ == "__main__":
    main()
