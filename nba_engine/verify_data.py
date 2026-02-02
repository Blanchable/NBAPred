#!/usr/bin/env python3
"""
NBA Prediction Engine - Data Verification Script

Run this to see exactly what data is being used for predictions.
Helps verify that the inputs are correct and meaningful.

Usage:
    python verify_data.py
"""

from datetime import datetime
from pprint import pprint

from ingest.schedule import (
    get_todays_games,
    get_advanced_team_stats,
    get_team_rest_days,
    get_current_season,
)
from ingest.injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
)
from model.point_system import score_game, FACTOR_WEIGHTS, FACTOR_NAMES


def main():
    print("=" * 80)
    print("NBA PREDICTION ENGINE - DATA VERIFICATION")
    print("=" * 80)
    print()
    
    # Get season
    season = get_current_season()
    print(f"Season: {season}")
    print()
    
    # Step 1: Fetch games
    print("-" * 80)
    print("STEP 1: TODAY'S GAMES")
    print("-" * 80)
    games = get_todays_games()
    
    if not games:
        print("No games found for today.")
        return
    
    for game in games:
        print(f"  {game.away_team} @ {game.home_team} - {game.start_time_utc or 'TBD'}")
    print()
    
    # Step 2: Team Stats
    print("-" * 80)
    print("STEP 2: TEAM STATISTICS (Advanced)")
    print("-" * 80)
    
    team_stats = get_advanced_team_stats(season=season)
    
    # Show stats for teams playing today
    teams_today = set()
    for game in games:
        teams_today.add(game.away_team)
        teams_today.add(game.home_team)
    
    print(f"\nStats for {len(teams_today)} teams playing today:\n")
    
    for team in sorted(teams_today):
        stats = team_stats.get(team, {})
        if stats:
            print(f"  {team}:")
            print(f"    Net Rating:    {stats.get('net_rating', 'N/A'):+.1f}")
            print(f"    Off Rating:    {stats.get('off_rating', 'N/A'):.1f}")
            print(f"    Def Rating:    {stats.get('def_rating', 'N/A'):.1f}")
            print(f"    Pace:          {stats.get('pace', 'N/A'):.1f}")
            print(f"    eFG%:          {stats.get('efg_pct', 'N/A'):.3f}")
            print(f"    3P%:           {stats.get('fg3_pct', 'N/A'):.3f}")
            print(f"    3PA Rate:      {stats.get('fg3a_rate', 'N/A'):.3f}")
            print(f"    FT Rate:       {stats.get('ft_rate', 'N/A'):.3f}")
            print(f"    TOV%:          {stats.get('tov_pct', 'N/A'):.1f}")
            print(f"    REB%:          {stats.get('reb_pct', 'N/A'):.1f}")
            print(f"    Opp 3P%:       {stats.get('opp_fg3_pct', 'N/A'):.3f}")
            print(f"    Fouls/Game:    {stats.get('pf_per_game', 'N/A'):.1f}")
            print()
        else:
            print(f"  {team}: NO DATA (using defaults)")
            print()
    
    # Step 3: Rest Days
    print("-" * 80)
    print("STEP 3: REST DAYS")
    print("-" * 80)
    
    rest_days = get_team_rest_days(list(teams_today), season=season)
    
    for team in sorted(teams_today):
        days = rest_days.get(team, "Unknown")
        print(f"  {team}: {days} day(s) rest")
    print()
    
    # Step 4: Injuries
    print("-" * 80)
    print("STEP 4: INJURIES")
    print("-" * 80)
    
    injury_url = find_latest_injury_pdf()
    injuries = []
    
    if injury_url:
        print(f"  Source: {injury_url}")
        pdf_bytes = download_injury_pdf(injury_url)
        if pdf_bytes:
            injuries = parse_injury_pdf(pdf_bytes)
            
            # Filter to teams playing today
            relevant_injuries = [i for i in injuries if i.team in teams_today]
            
            print(f"\n  Injuries affecting today's games ({len(relevant_injuries)}):\n")
            
            for team in sorted(teams_today):
                team_injuries = [i for i in injuries if i.team == team]
                if team_injuries:
                    print(f"  {team}:")
                    for inj in team_injuries:
                        print(f"    - {inj.player}: {inj.status} ({inj.reason})")
                    print()
    else:
        print("  No injury report found.")
    print()
    
    # Step 5: Factor Weights
    print("-" * 80)
    print("STEP 5: FACTOR WEIGHTS (Sum = 100)")
    print("-" * 80)
    
    for name, weight in sorted(FACTOR_WEIGHTS.items(), key=lambda x: -x[1]):
        display = FACTOR_NAMES.get(name, name)
        print(f"  {weight:3d}  {display}")
    
    print(f"\n  Total: {sum(FACTOR_WEIGHTS.values())}")
    print()
    
    # Step 6: Sample Prediction Breakdown
    print("-" * 80)
    print("STEP 6: SAMPLE PREDICTION BREAKDOWN")
    print("-" * 80)
    
    if games:
        game = games[0]
        home_rest = rest_days.get(game.home_team, 1)
        away_rest = rest_days.get(game.away_team, 1)
        
        score = score_game(
            home_team=game.home_team,
            away_team=game.away_team,
            team_stats=team_stats,
            injuries=injuries,
            player_stats={},
            home_rest_days=home_rest,
            away_rest_days=away_rest,
        )
        
        print(f"\n  Game: {game.away_team} @ {game.home_team}")
        print(f"  Predicted Winner: {score.predicted_winner}")
        print(f"  Edge Score: {score.edge_score_total:+.1f}")
        print(f"  Home Win Prob: {score.home_win_prob:.1%}")
        print(f"  Away Win Prob: {score.away_win_prob:.1%}")
        print(f"  Projected Margin: {score.projected_margin_home:+.1f}")
        print()
        
        print("  Factor Breakdown (sorted by impact):")
        print("  " + "-" * 76)
        print(f"  {'Factor':<25} {'Wt':>4} {'Signed':>8} {'Contrib':>8}  Inputs")
        print("  " + "-" * 76)
        
        for factor in sorted(score.factors, key=lambda f: abs(f.contribution), reverse=True):
            print(f"  {factor.display_name:<25} {factor.weight:>4} {factor.signed_value:>+8.3f} {factor.contribution:>+8.2f}  {factor.inputs_used[:40]}")
        
        print("  " + "-" * 76)
        print(f"  {'TOTAL':<25} {100:>4} {'':>8} {score.edge_score_total:>+8.2f}")
    
    print()
    print("=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    print()
    print("Check the data above to verify:")
    print("  1. Team stats look reasonable (Net Rating between -15 and +15)")
    print("  2. Rest days are accurate (check against NBA schedule)")
    print("  3. Injuries are current and correctly attributed to teams")
    print("  4. Factor contributions make sense given the inputs")
    print()


if __name__ == "__main__":
    main()
