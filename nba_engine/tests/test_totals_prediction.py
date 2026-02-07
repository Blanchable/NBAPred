"""
Unit tests for totals prediction module.

Tests:
1. Possession prediction with pace variations
2. PPP calculation with offense/defense matchups
3. Variance band computation
4. End-to-end totals prediction
5. Fallback handling
6. Evaluation metrics
"""

import pytest
from model.totals_prediction import (
    predict_possessions,
    predict_ppp,
    predict_points,
    compute_variance_band,
    predict_game_totals,
    evaluate_totals,
    TotalsContext,
    TotalsPrediction,
    TotalsEvaluation,
    LEAGUE_AVG_PACE,
    LEAGUE_AVG_PPP,
    PACE_MIN,
    PACE_MAX,
    PPP_MIN,
    PPP_MAX,
    BAND_LOW,
    BAND_MED,
    BAND_HIGH,
)


class TestPredictPossessions:
    """Test possession prediction logic."""
    
    def test_baseline_pace_average(self):
        """Baseline pace should be average of both teams."""
        home_stats = {'pace': 100.0}
        away_stats = {'pace': 100.0}
        
        poss, adj = predict_possessions(home_stats, away_stats)
        
        assert poss == 100.0
        assert adj == 0.0
    
    def test_different_paces_averaged(self):
        """Different paces should be averaged."""
        home_stats = {'pace': 102.0}
        away_stats = {'pace': 98.0}
        
        poss, adj = predict_possessions(home_stats, away_stats)
        
        assert poss == 100.0  # (102 + 98) / 2
        assert adj == 0.0
    
    def test_fast_pace_teams(self):
        """Fast pace teams should produce higher possessions."""
        home_stats = {'pace': 104.0}
        away_stats = {'pace': 104.0}
        
        poss, adj = predict_possessions(home_stats, away_stats)
        
        assert poss == 104.0
    
    def test_blowout_reduces_pace(self):
        """Blowout prediction should reduce pace."""
        home_stats = {'pace': 100.0}
        away_stats = {'pace': 100.0}
        context = TotalsContext(predicted_margin=12.0)
        
        poss, adj = predict_possessions(home_stats, away_stats, context)
        
        assert poss < 100.0
        assert adj < 0
    
    def test_close_game_increases_pace(self):
        """Close game prediction should slightly increase pace."""
        home_stats = {'pace': 100.0}
        away_stats = {'pace': 100.0}
        context = TotalsContext(predicted_margin=2.0)
        
        poss, adj = predict_possessions(home_stats, away_stats, context)
        
        assert poss > 100.0
        assert adj > 0
    
    def test_pace_bounded(self):
        """Predicted pace should be within bounds."""
        # Extremely high pace
        home_stats = {'pace': 120.0}
        away_stats = {'pace': 120.0}
        
        poss, _ = predict_possessions(home_stats, away_stats)
        assert poss <= PACE_MAX
        
        # Extremely low pace
        home_stats = {'pace': 80.0}
        away_stats = {'pace': 80.0}
        
        poss, _ = predict_possessions(home_stats, away_stats)
        assert poss >= PACE_MIN
    
    def test_fallback_on_missing_pace(self):
        """Should use league average when pace is missing."""
        home_stats = {}
        away_stats = {}
        fallbacks = []
        
        poss, _ = predict_possessions(
            home_stats, away_stats, 
            home_team="NYK", away_team="BOS",
            fallbacks=fallbacks
        )
        
        assert poss == LEAGUE_AVG_PACE
        assert len(fallbacks) == 2  # Both teams used fallback


class TestPredictPPP:
    """Test points per possession prediction."""
    
    def test_league_average_matchup(self):
        """League average offense vs defense should produce ~league PPP."""
        team_stats = {'off_rating': 114.0, 'tov_pct': 14.0, 'ft_rate': 0.25, 'efg_pct': 0.52}
        opp_stats = {'def_rating': 114.0, 'opp_tov_pct': 14.0, 'opp_ft_rate': 0.25, 'opp_efg_pct': 0.52}
        
        ppp, adj = predict_ppp(team_stats, opp_stats)
        
        # Should be close to league average
        assert abs(ppp - LEAGUE_AVG_PPP) < 0.05
    
    def test_strong_offense_increases_ppp(self):
        """Strong offense should produce higher PPP."""
        strong_off = {'off_rating': 120.0, 'tov_pct': 12.0, 'ft_rate': 0.28, 'efg_pct': 0.55}
        avg_def = {'def_rating': 114.0, 'opp_tov_pct': 14.0, 'opp_ft_rate': 0.25, 'opp_efg_pct': 0.52}
        
        ppp, _ = predict_ppp(strong_off, avg_def)
        
        assert ppp > LEAGUE_AVG_PPP
    
    def test_strong_defense_decreases_ppp(self):
        """Strong opponent defense should decrease PPP relative to weak defense."""
        avg_off = {'off_rating': 114.0, 'tov_pct': 14.0, 'ft_rate': 0.25, 'efg_pct': 0.52}
        strong_def = {'def_rating': 106.0, 'opp_tov_pct': 16.0, 'opp_ft_rate': 0.22, 'opp_efg_pct': 0.48}
        weak_def = {'def_rating': 118.0, 'opp_tov_pct': 12.0, 'opp_ft_rate': 0.30, 'opp_efg_pct': 0.56}
        
        ppp_vs_strong, _ = predict_ppp(avg_off, strong_def)
        ppp_vs_weak, _ = predict_ppp(avg_off, weak_def)
        
        # PPP against strong defense should be lower than against weak defense
        assert ppp_vs_strong < ppp_vs_weak
    
    def test_ppp_bounded(self):
        """PPP should be within realistic bounds."""
        # Extreme offense vs weak defense
        extreme_off = {'off_rating': 130.0, 'tov_pct': 10.0, 'ft_rate': 0.35, 'efg_pct': 0.60}
        weak_def = {'def_rating': 120.0, 'opp_tov_pct': 12.0, 'opp_ft_rate': 0.30, 'opp_efg_pct': 0.56}
        
        ppp, _ = predict_ppp(extreme_off, weak_def)
        assert ppp <= PPP_MAX
        
        # Weak offense vs strong defense
        weak_off = {'off_rating': 100.0, 'tov_pct': 18.0, 'ft_rate': 0.20, 'efg_pct': 0.46}
        extreme_def = {'def_rating': 100.0, 'opp_tov_pct': 18.0, 'opp_ft_rate': 0.20, 'opp_efg_pct': 0.46}
        
        ppp, _ = predict_ppp(weak_off, extreme_def)
        assert ppp >= PPP_MIN


class TestPredictPoints:
    """Test points prediction with game-state adjustments."""
    
    def test_basic_points_calculation(self):
        """Points should be possessions × PPP."""
        poss = 100.0
        ppp_home = 1.15
        ppp_away = 1.10
        
        home_pts, away_pts, total, adj = predict_points(poss, ppp_home, ppp_away)
        
        assert abs(home_pts - 115.0) < 1.0
        assert abs(away_pts - 110.0) < 1.0
        assert abs(total - 225.0) < 2.0
    
    def test_blowout_reduces_total(self):
        """Blowout should reduce total points."""
        poss = 100.0
        ppp_home = 1.15
        ppp_away = 1.10
        context = TotalsContext(win_prob=0.80, predicted_margin=15.0)
        
        home_pts, away_pts, total, adj = predict_points(poss, ppp_home, ppp_away, context)
        
        raw_total = poss * (ppp_home + ppp_away)
        assert total < raw_total
        assert adj < 0
    
    def test_close_game_increases_total(self):
        """Close game should increase total (late-game fouls)."""
        poss = 100.0
        ppp_home = 1.12
        ppp_away = 1.12
        context = TotalsContext(predicted_margin=1.0)
        
        home_pts, away_pts, total, adj = predict_points(poss, ppp_home, ppp_away, context)
        
        raw_total = poss * (ppp_home + ppp_away)
        assert total > raw_total
        assert adj > 0


class TestComputeVarianceBand:
    """Test variance band calculation."""
    
    def test_average_variance(self):
        """Average stats should produce medium band."""
        home_stats = {'fg3a_rate': 0.40, 'tov_pct': 14.0, 'ft_rate': 0.25}
        away_stats = {'fg3a_rate': 0.40, 'tov_pct': 14.0, 'ft_rate': 0.25}
        
        variance, band = compute_variance_band(home_stats, away_stats, 99.5)
        
        assert band == BAND_MED
    
    def test_high_3pa_increases_variance(self):
        """High 3PA rate should increase variance."""
        home_stats = {'fg3a_rate': 0.50, 'tov_pct': 14.0, 'ft_rate': 0.25}
        away_stats = {'fg3a_rate': 0.50, 'tov_pct': 14.0, 'ft_rate': 0.25}
        
        variance, band = compute_variance_band(home_stats, away_stats, 99.5)
        
        # High 3PA should increase variance
        assert variance > 0
    
    def test_high_ft_decreases_variance(self):
        """High FT rate should decrease variance (more predictable)."""
        # Low variance: low 3PA, low TOV, high FT
        low_var_stats = {'fg3a_rate': 0.30, 'tov_pct': 11.0, 'ft_rate': 0.32}
        
        variance, band = compute_variance_band(low_var_stats, low_var_stats, 99.5)
        
        # Should have lower variance
        assert variance < 0


class TestPredictGameTotals:
    """End-to-end totals prediction tests."""
    
    def test_complete_prediction(self):
        """Should produce complete prediction with all fields."""
        home_stats = {
            'pace': 100.0,
            'off_rating': 115.0,
            'def_rating': 110.0,
            'tov_pct': 13.0,
            'ft_rate': 0.26,
            'efg_pct': 0.54,
            'fg3a_rate': 0.42,
            'opp_tov_pct': 15.0,
            'opp_efg_pct': 0.50,
        }
        away_stats = {
            'pace': 98.0,
            'off_rating': 112.0,
            'def_rating': 112.0,
            'tov_pct': 14.0,
            'ft_rate': 0.24,
            'efg_pct': 0.52,
            'fg3a_rate': 0.40,
            'opp_tov_pct': 14.0,
            'opp_efg_pct': 0.52,
        }
        
        result = predict_game_totals(
            home_team="NYK",
            away_team="BOS",
            home_stats=home_stats,
            away_stats=away_stats,
            predicted_margin=3.0,
            win_prob=0.58,
        )
        
        # Verify all required fields exist
        assert isinstance(result, TotalsPrediction)
        assert result.expected_possessions > 0
        assert result.ppp_home > 0
        assert result.ppp_away > 0
        assert result.predicted_home_points > 0
        assert result.predicted_away_points > 0
        assert result.predicted_total > 0
        assert result.total_range_low < result.predicted_total
        assert result.total_range_high > result.predicted_total
        assert result.band_width in [BAND_LOW, BAND_MED, BAND_HIGH]
    
    def test_display_properties(self):
        """Display properties should work correctly."""
        home_stats = {'pace': 100.0, 'off_rating': 115.0, 'def_rating': 110.0}
        away_stats = {'pace': 100.0, 'off_rating': 112.0, 'def_rating': 112.0}
        
        result = predict_game_totals(
            home_team="NYK",
            away_team="BOS",
            home_stats=home_stats,
            away_stats=away_stats,
        )
        
        # Display values should be integers
        assert isinstance(result.display_home_points, int)
        assert isinstance(result.display_away_points, int)
        assert isinstance(result.display_total, int)
        
        # Display total should equal sum of team displays
        assert result.display_total == result.display_home_points + result.display_away_points
    
    def test_altitude_adjustment(self):
        """Denver home games should have slight pace reduction."""
        home_stats = {'pace': 100.0, 'off_rating': 115.0, 'def_rating': 110.0}
        away_stats = {'pace': 100.0, 'off_rating': 112.0, 'def_rating': 112.0}
        
        result_denver = predict_game_totals(
            home_team="DEN",  # Altitude game
            away_team="LAL",
            home_stats=home_stats,
            away_stats=away_stats,
        )
        
        result_normal = predict_game_totals(
            home_team="NYK",  # Normal game
            away_team="LAL",
            home_stats=home_stats,
            away_stats=away_stats,
        )
        
        # Denver should have slightly lower possessions
        assert result_denver.expected_possessions < result_normal.expected_possessions
    
    def test_fallback_logged(self):
        """Missing stats should be logged to fallbacks."""
        home_stats = {}  # All missing
        away_stats = {'pace': 100.0}
        
        result = predict_game_totals(
            home_team="NYK",
            away_team="BOS",
            home_stats=home_stats,
            away_stats=away_stats,
        )
        
        # Should still produce result
        assert result.predicted_total > 0
        # Should have logged fallbacks
        assert len(result.fallbacks_used) > 0


class TestEvaluateTotals:
    """Test evaluation metrics calculation."""
    
    def test_perfect_predictions(self):
        """Perfect predictions should have 0 MAE."""
        predictions = [
            {
                'predicted_total': 220,
                'actual_total': 220,
                'total_range_low': 210,
                'total_range_high': 230,
                'predicted_home_points': 115,
                'actual_home_points': 115,
                'predicted_away_points': 105,
                'actual_away_points': 105,
            }
        ]
        
        result = evaluate_totals(predictions)
        
        assert result.n_games == 1
        assert result.mae_total == 0.0
        assert result.mae_home == 0.0
        assert result.mae_away == 0.0
        assert result.bias_total == 0.0
        assert result.pct_within_range == 100.0
    
    def test_within_range_calculation(self):
        """Within range should be calculated correctly."""
        predictions = [
            {  # Within range
                'predicted_total': 220,
                'actual_total': 215,
                'total_range_low': 210,
                'total_range_high': 230,
                'predicted_home_points': 115,
                'actual_home_points': 112,
                'predicted_away_points': 105,
                'actual_away_points': 103,
            },
            {  # Outside range (too low)
                'predicted_total': 220,
                'actual_total': 200,
                'total_range_low': 210,
                'total_range_high': 230,
                'predicted_home_points': 115,
                'actual_home_points': 105,
                'predicted_away_points': 105,
                'actual_away_points': 95,
            },
        ]
        
        result = evaluate_totals(predictions)
        
        assert result.n_games == 2
        assert result.pct_within_range == 50.0  # 1 out of 2
    
    def test_bias_calculation(self):
        """Bias should show directional error."""
        predictions = [
            {  # Over-predicted by 10
                'predicted_total': 230,
                'actual_total': 220,
                'total_range_low': 220,
                'total_range_high': 240,
                'predicted_home_points': 120,
                'actual_home_points': 115,
                'predicted_away_points': 110,
                'actual_away_points': 105,
            },
            {  # Over-predicted by 10
                'predicted_total': 220,
                'actual_total': 210,
                'total_range_low': 210,
                'total_range_high': 230,
                'predicted_home_points': 115,
                'actual_home_points': 110,
                'predicted_away_points': 105,
                'actual_away_points': 100,
            },
        ]
        
        result = evaluate_totals(predictions)
        
        # Average bias should be +10
        assert result.bias_total == 10.0
    
    def test_empty_predictions(self):
        """Empty predictions should return zero evaluation."""
        result = evaluate_totals([])
        
        assert result.n_games == 0
        assert result.mae_total == 0.0


class TestIntegration:
    """Integration tests with realistic scenarios."""
    
    def test_high_scoring_game(self):
        """High-scoring teams should produce higher totals."""
        high_scoring = {
            'pace': 104.0,
            'off_rating': 120.0,
            'def_rating': 115.0,
            'tov_pct': 12.0,
            'ft_rate': 0.28,
            'efg_pct': 0.56,
            'fg3a_rate': 0.45,
        }
        low_scoring = {
            'pace': 95.0,
            'off_rating': 105.0,
            'def_rating': 105.0,
            'tov_pct': 16.0,
            'ft_rate': 0.22,
            'efg_pct': 0.48,
            'fg3a_rate': 0.35,
        }
        
        result_high = predict_game_totals(
            home_team="GSW",
            away_team="IND",
            home_stats=high_scoring,
            away_stats=high_scoring,
        )
        
        result_low = predict_game_totals(
            home_team="ORL",
            away_team="MIA",
            home_stats=low_scoring,
            away_stats=low_scoring,
        )
        
        assert result_high.predicted_total > result_low.predicted_total
    
    def test_totals_dict_export(self):
        """to_dict should produce valid export format."""
        home_stats = {'pace': 100.0, 'off_rating': 115.0, 'def_rating': 110.0}
        away_stats = {'pace': 100.0, 'off_rating': 112.0, 'def_rating': 112.0}
        
        result = predict_game_totals(
            home_team="NYK",
            away_team="BOS",
            home_stats=home_stats,
            away_stats=away_stats,
        )
        
        d = result.to_dict()
        
        assert 'expected_possessions' in d
        assert 'ppp_home' in d
        assert 'ppp_away' in d
        assert 'predicted_total' in d
        assert 'total_range_low' in d
        assert 'total_range_high' in d


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
