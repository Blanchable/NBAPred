"""
Unit tests for factor variance fix.

Tests that:
1. Home and away stats are properly distinct
2. Fallback data has per-team variation
3. Factor calculations produce different values for different teams
"""

import pytest
import copy

from model.point_system import (
    score_game_v3, safe_get, safe_get_with_fallback,
    calc_shooting_advantage, calc_turnover_diff, calc_rebounding,
    calc_pace_control,
)
from model.factor_debug import (
    validate_distinct_stats, ensure_distinct_copies,
    DataSource, StatsWithProvenance,
)
from ingest.team_stats import get_fallback_team_strength, TeamStrength, FALLBACK_TEAM_DATA


class TestFallbackDataVariance:
    """Test that fallback data has proper per-team variation."""
    
    def test_fallback_data_has_all_teams(self):
        """Verify fallback data includes expected teams."""
        teams = get_fallback_team_strength()
        assert len(teams) >= 25, f"Expected at least 25 teams, got {len(teams)}"
        
        # Check some specific teams exist
        expected_teams = ['OKC', 'CLE', 'BOS', 'NYK', 'LAL', 'GSW', 'MIA', 'PHX']
        for team in expected_teams:
            assert team in teams, f"Team {team} missing from fallback data"
    
    def test_fallback_efg_has_variance(self):
        """Verify eFG% varies across teams."""
        teams = get_fallback_team_strength()
        efg_values = [ts.efg_pct for ts in teams.values()]
        
        assert len(set(efg_values)) > 1, "All teams have identical eFG%!"
        assert max(efg_values) - min(efg_values) > 0.01, "eFG% spread too small"
    
    def test_fallback_tov_has_variance(self):
        """Verify TOV% varies across teams."""
        teams = get_fallback_team_strength()
        tov_values = [ts.tov_pct for ts in teams.values()]
        
        assert len(set(tov_values)) > 1, "All teams have identical TOV%!"
        assert max(tov_values) - min(tov_values) > 1.0, "TOV% spread too small"
    
    def test_fallback_oreb_has_variance(self):
        """Verify OREB% varies across teams."""
        teams = get_fallback_team_strength()
        oreb_values = [ts.oreb_pct for ts in teams.values()]
        
        assert len(set(oreb_values)) > 1, "All teams have identical OREB%!"
        assert max(oreb_values) - min(oreb_values) > 1.0, "OREB% spread too small"
    
    def test_fallback_pace_has_variance(self):
        """Verify pace varies across teams."""
        teams = get_fallback_team_strength()
        pace_values = [ts.pace for ts in teams.values()]
        
        assert len(set(pace_values)) > 1, "All teams have identical pace!"
        assert max(pace_values) - min(pace_values) > 1.0, "Pace spread too small"
    
    def test_two_different_teams_have_different_stats(self):
        """Verify two specific teams have different stats."""
        teams = get_fallback_team_strength()
        
        okc = teams.get('OKC')
        was = teams.get('WAS')
        
        assert okc is not None and was is not None
        
        # These teams should have very different stats
        assert okc.efg_pct != was.efg_pct, "OKC and WAS have same eFG%"
        assert okc.tov_pct != was.tov_pct, "OKC and WAS have same TOV%"
        assert okc.net_rating != was.net_rating, "OKC and WAS have same net rating"


class TestDistinctStatsValidation:
    """Test stats validation and distinct copies."""
    
    def test_validate_same_object_reference(self):
        """Validation should detect same object reference."""
        stats = {'efg_pct': 0.52, 'tov_pct': 14.0}
        
        warnings = validate_distinct_stats("NYK", "BOS", stats, stats)
        
        assert len(warnings) > 0, "Should warn about same object"
        assert any("SAME OBJECT" in w for w in warnings)
    
    def test_validate_mostly_identical_values(self):
        """Validation should warn about mostly identical values."""
        home_stats = {'efg_pct': 0.52, 'tov_pct': 14.0, 'oreb_pct': 25.0, 
                      'pace': 100.0, 'ft_rate': 0.25, 'fg3_pct': 0.36,
                      'fg3a_rate': 0.40, 'opp_efg_pct': 0.52, 'off_rating': 110,
                      'def_rating': 110, 'net_rating': 0}
        away_stats = home_stats.copy()  # Copy but same values
        
        warnings = validate_distinct_stats("NYK", "BOS", home_stats, away_stats)
        
        assert len(warnings) > 0, "Should warn about identical values"
    
    def test_ensure_distinct_copies(self):
        """ensure_distinct_copies should create independent copies."""
        original = {'a': 1, 'b': {'nested': 2}}
        
        copy1, copy2 = ensure_distinct_copies(original, original)
        
        # Should be different objects
        assert id(copy1) != id(copy2)
        assert id(copy1) != id(original)
        
        # Modifying one should not affect the other
        copy1['a'] = 999
        copy1['b']['nested'] = 999
        
        assert copy2['a'] == 1
        assert copy2['b']['nested'] == 2


class TestFactorCalculations:
    """Test that factor calculations work correctly with different inputs."""
    
    def test_shooting_advantage_different_inputs(self):
        """Shooting advantage should differ for different eFG/3P values."""
        # Home better at shooting
        result1 = calc_shooting_advantage(0.55, 0.50, 0.38, 0.35)
        # Away better at shooting  
        result2 = calc_shooting_advantage(0.50, 0.55, 0.35, 0.38)
        
        assert result1.signed_value > 0, "Home better should be positive"
        assert result2.signed_value < 0, "Away better should be negative"
        assert result1.home_raw == 0.55  # eFG is stored as home_raw
        assert result1.away_raw == 0.50
    
    def test_shooting_advantage_fallback_tracking(self):
        """Shooting advantage should track fallback usage."""
        result = calc_shooting_advantage(0.55, 0.50, 0.38, 0.35, home_fallback=True, away_fallback=False)
        
        assert result.home_fallback is True
        assert result.away_fallback is False
        assert "[FB]" in result.inputs_used
    
    def test_turnover_diff_different_inputs(self):
        """Turnover diff should differ for different TOV values."""
        result1 = calc_turnover_diff(12.0, 16.0)  # Home better (lower TOV)
        result2 = calc_turnover_diff(16.0, 12.0)  # Away better
        
        assert result1.signed_value > 0, "Lower home TOV should be positive"
        assert result2.signed_value < 0, "Lower away TOV should be negative"
    
    def test_pace_control_different_inputs(self):
        """Pace control should differ for different pace values."""
        result1 = calc_pace_control(102.0, 98.0)  # Home faster
        result2 = calc_pace_control(98.0, 102.0)  # Away faster
        
        assert result1.signed_value > 0
        assert result2.signed_value < 0
        assert result1.home_raw == 102.0
        assert result1.away_raw == 98.0


class TestScoreGameV3Integration:
    """Integration tests for score_game_v3."""
    
    def test_score_game_with_distinct_teams(self):
        """Scoring should produce different results for different team matchups."""
        teams = get_fallback_team_strength()
        
        okc_stats = teams['OKC'].to_dict()
        was_stats = teams['WAS'].to_dict()
        bos_stats = teams['BOS'].to_dict()
        
        # OKC vs WAS
        score1 = score_game_v3(
            home_team='OKC',
            away_team='WAS',
            home_strength=None,
            away_strength=None,
            home_stats=okc_stats,
            away_stats=was_stats,
        )
        
        # WAS vs OKC (reversed)
        score2 = score_game_v3(
            home_team='WAS',
            away_team='OKC',
            home_strength=None,
            away_strength=None,
            home_stats=was_stats,
            away_stats=okc_stats,
        )
        
        # Results should be different (home team changed)
        assert score1.edge_score_total != score2.edge_score_total
        
        # OKC at home vs WAS should favor OKC
        assert score1.predicted_winner == 'OKC', "OKC should be favored at home vs WAS"
    
    def test_score_game_factors_have_variance(self):
        """Factors in a game should not all be identical."""
        teams = get_fallback_team_strength()
        
        home_stats = teams['BOS'].to_dict()
        away_stats = teams['CHA'].to_dict()
        
        score = score_game_v3(
            home_team='BOS',
            away_team='CHA',
            home_strength=None,
            away_strength=None,
            home_stats=home_stats,
            away_stats=away_stats,
        )
        
        # Check factors with raw values
        factors_with_raw = [f for f in score.factors 
                          if hasattr(f, 'home_raw') and f.home_raw != 0]
        
        # Count identical factors
        identical = sum(1 for f in factors_with_raw 
                       if abs(f.home_raw - f.away_raw) < 1e-9)
        
        # Should have fewer than 50% identical
        assert len(factors_with_raw) > 0, "Should have factors with raw values"
        pct_identical = identical / len(factors_with_raw) * 100
        assert pct_identical < 50, f"Too many identical factors: {pct_identical:.0f}%"
    
    def test_score_game_ensures_distinct_stats(self):
        """score_game_v3 should handle same object input safely."""
        teams = get_fallback_team_strength()
        
        # Intentionally pass same object (bug scenario)
        shared_stats = teams['NYK'].to_dict()
        
        # This should NOT crash and should make copies internally
        score = score_game_v3(
            home_team='NYK',
            away_team='BOS',
            home_strength=None,
            away_strength=None,
            home_stats=shared_stats,
            away_stats=shared_stats,  # Same object!
        )
        
        # Should still produce a result (even if suboptimal)
        assert score is not None
        assert score.home_team == 'NYK'
        assert score.away_team == 'BOS'


class TestSafeGetWithFallback:
    """Test the safe_get_with_fallback function."""
    
    def test_returns_value_when_present(self):
        """Should return actual value when key exists."""
        stats = {'efg_pct': 0.548}
        
        value, fallback_used, source = safe_get_with_fallback(stats, 'efg_pct', 0.52)
        
        assert value == 0.548
        assert fallback_used is False
    
    def test_returns_default_when_missing(self):
        """Should return default and mark fallback when key missing."""
        stats = {}
        
        value, fallback_used, source = safe_get_with_fallback(stats, 'efg_pct', 0.52)
        
        assert value == 0.52
        assert fallback_used is True
        assert 'fallback' in source
    
    def test_returns_default_when_none(self):
        """Should return default and mark fallback when value is None."""
        stats = {'efg_pct': None}
        
        value, fallback_used, source = safe_get_with_fallback(stats, 'efg_pct', 0.52)
        
        assert value == 0.52
        assert fallback_used is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
