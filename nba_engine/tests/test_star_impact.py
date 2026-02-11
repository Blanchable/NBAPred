"""Unit tests for star_impact module."""

import pytest
from dataclasses import dataclass
from typing import Optional


# Mock player class for testing
@dataclass
class MockPlayer:
    player_name: str
    points_per_game: float
    assists_per_game: float
    minutes_per_game: float
    status: Optional[str] = "Available"


# Import functions to test
from model.star_impact import (
    status_multiplier,
    impact_metric,
    select_star_tiers,
    team_star_points,
    star_edge_points,
    dampened_star_edge,
    compute_star_factor,
    TIER_A_POINTS,
    TIER_B_POINTS,
    STAR_EDGE_CLAMP,
)


class TestStatusMultiplier:
    """Tests for status_multiplier function."""
    
    def test_out_status(self):
        """OUT status should return 0.0"""
        assert status_multiplier("OUT") == 0.0
        assert status_multiplier("out") == 0.0
        assert status_multiplier("O") == 0.0
        assert status_multiplier("inactive") == 0.0
    
    def test_doubtful_status(self):
        """DOUBTFUL status should return 0.25"""
        assert status_multiplier("DOUBTFUL") == 0.25
        assert status_multiplier("doubtful") == 0.25
        assert status_multiplier("D") == 0.25
    
    def test_questionable_status(self):
        """QUESTIONABLE status should return 0.60"""
        assert status_multiplier("QUESTIONABLE") == 0.60
        assert status_multiplier("Q") == 0.60
        assert status_multiplier("GTD") == 0.60
    
    def test_probable_status(self):
        """PROBABLE status should return 0.85"""
        assert status_multiplier("PROBABLE") == 0.85
        assert status_multiplier("P") == 0.85
    
    def test_available_status(self):
        """AVAILABLE status should return 1.0"""
        assert status_multiplier("Available") == 1.0
        assert status_multiplier("ACTIVE") == 1.0
        assert status_multiplier("healthy") == 1.0
        assert status_multiplier(None) == 1.0
        assert status_multiplier("") == 1.0


class TestImpactMetric:
    """Tests for impact_metric function (box-impact proxy)."""
    
    def test_ppg_and_apg(self):
        """Impact should be PTS + 1.5*AST + 1.2*REB + 2*STL + 2*BLK - 1.5*TOV"""
        player = MockPlayer("Test", points_per_game=25.0, assists_per_game=10.0, minutes_per_game=35.0)
        # 25 + 1.5*10 + 1.2*0 + 2*0 + 2*0 - 1.5*0 = 40.0
        assert impact_metric(player) == 40.0
    
    def test_ppg_only(self):
        """When APG is 0, impact should be just PPG (other stats default 0)"""
        player = MockPlayer("Test", points_per_game=20.0, assists_per_game=0.0, minutes_per_game=30.0)
        assert impact_metric(player) == 20.0


class TestSelectStarTiers:
    """Tests for select_star_tiers function."""
    
    def test_empty_players(self):
        """Empty player list should return empty tiers"""
        result = select_star_tiers([])
        assert result == {"tier_a": [], "tier_b": []}
    
    def test_single_player(self):
        """Single player should be in Tier A only"""
        player = MockPlayer("Star", points_per_game=30.0, assists_per_game=10.0, minutes_per_game=35.0)
        result = select_star_tiers([player])
        assert len(result["tier_a"]) == 1
        assert len(result["tier_b"]) == 0
    
    def test_multiple_players(self):
        """Top player in A, next 2 in B"""
        star1 = MockPlayer("Star1", points_per_game=30.0, assists_per_game=10.0, minutes_per_game=35.0)
        star2 = MockPlayer("Star2", points_per_game=25.0, assists_per_game=8.0, minutes_per_game=34.0)
        star3 = MockPlayer("Star3", points_per_game=20.0, assists_per_game=5.0, minutes_per_game=32.0)
        role = MockPlayer("Role", points_per_game=10.0, assists_per_game=2.0, minutes_per_game=25.0)
        
        result = select_star_tiers([star1, star2, star3, role])
        
        assert len(result["tier_a"]) == 1
        assert result["tier_a"][0].player_name == "Star1"
        
        assert len(result["tier_b"]) == 2
        assert result["tier_b"][0].player_name == "Star2"
        assert result["tier_b"][1].player_name == "Star3"
    
    def test_mpg_filter(self):
        """Players with MPG < 20 should be filtered unless no candidates remain"""
        star1 = MockPlayer("Star1", points_per_game=30.0, assists_per_game=10.0, minutes_per_game=35.0)
        bench = MockPlayer("Bench", points_per_game=15.0, assists_per_game=3.0, minutes_per_game=15.0)
        
        result = select_star_tiers([star1, bench])
        
        # Bench player filtered due to low MPG
        assert len(result["tier_a"]) == 1
        assert result["tier_a"][0].player_name == "Star1"


class TestTeamStarPoints:
    """Tests for team_star_points function."""
    
    def test_full_strength(self):
        """All stars available should get max points"""
        star1 = MockPlayer("Star1", points_per_game=30.0, assists_per_game=10.0, minutes_per_game=35.0, status="Available")
        star2 = MockPlayer("Star2", points_per_game=25.0, assists_per_game=8.0, minutes_per_game=34.0, status="Available")
        star3 = MockPlayer("Star3", points_per_game=20.0, assists_per_game=5.0, minutes_per_game=32.0, status="Available")
        
        points, details = team_star_points([star1, star2, star3])
        
        # Tier A (4.0) + 2 x Tier B (2.0) = 8.0
        assert points == 8.0
    
    def test_star_out(self):
        """Star OUT should reduce points"""
        star1 = MockPlayer("Star1", points_per_game=30.0, assists_per_game=10.0, minutes_per_game=35.0, status="OUT")
        star2 = MockPlayer("Star2", points_per_game=25.0, assists_per_game=8.0, minutes_per_game=34.0, status="Available")
        star3 = MockPlayer("Star3", points_per_game=20.0, assists_per_game=5.0, minutes_per_game=32.0, status="Available")
        
        points, details = team_star_points([star1, star2, star3])
        
        # Tier A out (0) + 2 x Tier B (2.0) = 4.0
        assert points == 4.0
    
    def test_star_questionable(self):
        """Star QUESTIONABLE should get partial points"""
        star1 = MockPlayer("Star1", points_per_game=30.0, assists_per_game=10.0, minutes_per_game=35.0, status="Questionable")
        star2 = MockPlayer("Star2", points_per_game=25.0, assists_per_game=8.0, minutes_per_game=34.0, status="Available")
        star3 = MockPlayer("Star3", points_per_game=20.0, assists_per_game=5.0, minutes_per_game=32.0, status="Available")
        
        points, details = team_star_points([star1, star2, star3])
        
        # Tier A (4.0 * 0.6 = 2.4) + 2 x Tier B (2.0) = 6.4
        assert abs(points - 6.4) < 0.01


class TestStarEdgePoints:
    """Tests for star_edge_points function."""
    
    def test_equal_teams(self):
        """Equal teams should have zero edge"""
        home = [MockPlayer("H1", 30.0, 10.0, 35.0), MockPlayer("H2", 25.0, 8.0, 34.0)]
        away = [MockPlayer("A1", 30.0, 10.0, 35.0), MockPlayer("A2", 25.0, 8.0, 34.0)]
        
        edge, detail = star_edge_points(home, away)
        
        assert edge == 0.0
        assert detail["home_points"] == detail["away_points"]
    
    def test_home_advantage(self):
        """Home team with star out vs healthy away should be negative"""
        home = [MockPlayer("H1", 30.0, 10.0, 35.0, "OUT"), MockPlayer("H2", 25.0, 8.0, 34.0)]
        away = [MockPlayer("A1", 30.0, 10.0, 35.0), MockPlayer("A2", 25.0, 8.0, 34.0)]
        
        edge, detail = star_edge_points(home, away)
        
        # Home has 2.0 (tier B only), away has 6.0 (tier A + tier B)
        # Edge = 2.0 - 6.0 = -4.0
        assert edge == -4.0
        assert detail["home_points"] < detail["away_points"]
    
    def test_away_disadvantage(self):
        """Away team with star out should give positive edge"""
        home = [MockPlayer("H1", 30.0, 10.0, 35.0), MockPlayer("H2", 25.0, 8.0, 34.0)]
        away = [MockPlayer("A1", 30.0, 10.0, 35.0, "OUT"), MockPlayer("A2", 25.0, 8.0, 34.0)]
        
        edge, detail = star_edge_points(home, away)
        
        # Home has 6.0, away has 2.0
        # Edge = 6.0 - 2.0 = 4.0
        assert edge == 4.0
        assert detail["home_points"] > detail["away_points"]
    
    def test_edge_clamp(self):
        """Edge should be clamped to [-6, +6]"""
        # This tests the clamp works even if theoretical edge is extreme
        home = [MockPlayer("H1", 30.0, 10.0, 35.0), MockPlayer("H2", 25.0, 8.0, 34.0), MockPlayer("H3", 20.0, 5.0, 32.0)]
        away = []  # No players = 0 points
        
        edge, detail = star_edge_points(home, away)
        
        assert -STAR_EDGE_CLAMP <= edge <= STAR_EDGE_CLAMP


class TestDampenedStarEdge:
    """Tests for dampened_star_edge function."""
    
    def test_default_dampening(self):
        """No context should use 0.60 multiplier"""
        dampened, detail = dampened_star_edge(4.0)
        
        assert detail["multiplier"] == 0.60
        assert dampened == 2.4  # 4.0 * 0.6
    
    def test_small_sample_full_value(self):
        """Small sample (<=10 games) should use full value"""
        dampened, detail = dampened_star_edge(4.0, context={"lineup_games_used": 5})
        
        assert detail["multiplier"] == 1.0
        assert dampened == 4.0
    
    def test_large_sample_dampened(self):
        """Large sample (>10 games) should dampen"""
        dampened, detail = dampened_star_edge(4.0, context={"lineup_games_used": 20})
        
        assert detail["multiplier"] == 0.35
        assert dampened == 1.4  # 4.0 * 0.35


class TestIntegration:
    """Integration tests for full star factor calculation."""
    
    def test_no_star_out_returns_small_contribution(self):
        """When all stars are available, edge should be 0"""
        home = [MockPlayer("H1", 30.0, 10.0, 35.0), MockPlayer("H2", 25.0, 8.0, 34.0)]
        away = [MockPlayer("A1", 30.0, 10.0, 35.0), MockPlayer("A2", 25.0, 8.0, 34.0)]
        
        signed, edge, detail = compute_star_factor(home, away)
        
        assert signed == 0.0
    
    def test_star_out_produces_negative_signed(self):
        """Home star out should produce negative signed value"""
        home = [MockPlayer("H1", 30.0, 10.0, 35.0, "OUT"), MockPlayer("H2", 25.0, 8.0, 34.0)]
        away = [MockPlayer("A1", 30.0, 10.0, 35.0), MockPlayer("A2", 25.0, 8.0, 34.0)]
        
        signed, edge, detail = compute_star_factor(home, away)
        
        assert signed < 0
    
    def test_role_player_out_minimal_impact(self):
        """Role player out should not be in tiers, minimal impact"""
        # Tier A and B are all available
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0),  # Tier A
            MockPlayer("H2", 25.0, 8.0, 34.0),   # Tier B
            MockPlayer("H3", 20.0, 5.0, 32.0),   # Tier B
            MockPlayer("Role", 10.0, 2.0, 25.0, "OUT"),  # Role player OUT
        ]
        away = [MockPlayer("A1", 30.0, 10.0, 35.0), MockPlayer("A2", 25.0, 8.0, 34.0)]
        
        signed, edge, detail = compute_star_factor(home, away)
        
        # Home still has full star points (8.0), role player not in tiers
        # Impact should be minimal
        assert detail["home_points"] == 8.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
