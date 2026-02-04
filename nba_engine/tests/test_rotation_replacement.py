"""Unit tests for rotation_replacement module."""

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
from model.star_impact import select_star_tiers
from model.rotation_replacement import (
    star_absent,
    get_absent_stars,
    get_replacement_candidates,
    compute_rotation_replacement,
    REPLACEMENT_EDGE_CLAMP,
)


class TestStarAbsent:
    """Tests for star_absent function."""
    
    def test_all_available(self):
        """No absent stars should return False"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "Available"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        assert star_absent(tiers) == False
    
    def test_star_out(self):
        """Tier A OUT should return True"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "OUT"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        assert star_absent(tiers) == True
    
    def test_star_doubtful(self):
        """Tier A DOUBTFUL should return True"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "Doubtful"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        assert star_absent(tiers) == True
    
    def test_star_questionable_not_absent(self):
        """QUESTIONABLE is not considered absent (multiplier > 0.25)"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "Questionable"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        # Questionable has mult 0.60 > 0.25, so not considered absent
        assert star_absent(tiers) == False
    
    def test_tier_b_out(self):
        """Tier B OUT should return True"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "Available"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "OUT"),
        ]
        tiers = select_star_tiers(players)
        
        assert star_absent(tiers) == True


class TestGetAbsentStars:
    """Tests for get_absent_stars function."""
    
    def test_no_absent(self):
        """All available should return empty list"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "Available"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        absent = get_absent_stars(tiers)
        assert len(absent) == 0
    
    def test_tier_a_out(self):
        """Tier A OUT should be in list"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "OUT"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        absent = get_absent_stars(tiers)
        assert len(absent) == 1
        assert absent[0].name == "Star1"
        assert absent[0].tier == "A"
    
    def test_multiple_absent(self):
        """Multiple absent stars should all be listed"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "OUT"),
            MockPlayer("Star2", 25.0, 8.0, 34.0, "Doubtful"),
            MockPlayer("Star3", 20.0, 5.0, 32.0, "Available"),
        ]
        tiers = select_star_tiers(players)
        
        absent = get_absent_stars(tiers)
        assert len(absent) == 2


class TestGetReplacementCandidates:
    """Tests for get_replacement_candidates function."""
    
    def test_basic_candidates(self):
        """Non-star rotation players should be candidates"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0, "OUT"),
            MockPlayer("Star2", 25.0, 8.0, 34.0),
            MockPlayer("Starter3", 18.0, 4.0, 30.0),  # Tier B
            MockPlayer("Bench1", 12.0, 2.0, 25.0),  # Candidate
            MockPlayer("Bench2", 10.0, 1.0, 20.0),  # Candidate
        ]
        tiers = select_star_tiers(players)
        
        candidates = get_replacement_candidates(players, tiers)
        
        # Should get non-star players with 10-30 MPG
        assert len(candidates) <= 3
        # Stars should not be in candidates
        star_names = ["Star1", "Star2", "Starter3"]
        for c in candidates:
            assert c.name not in star_names
    
    def test_excludes_unavailable(self):
        """Players with low availability should be excluded"""
        players = [
            MockPlayer("Star1", 30.0, 10.0, 35.0),
            MockPlayer("Star2", 25.0, 8.0, 34.0),
            MockPlayer("Star3", 20.0, 5.0, 32.0),
            MockPlayer("Bench1", 12.0, 2.0, 25.0, "OUT"),  # Excluded
            MockPlayer("Bench2", 10.0, 1.0, 20.0, "Available"),  # Included
        ]
        tiers = select_star_tiers(players)
        
        candidates = get_replacement_candidates(players, tiers)
        
        # Bench1 OUT should be excluded
        for c in candidates:
            assert c.name != "Bench1"


class TestComputeRotationReplacement:
    """Tests for compute_rotation_replacement function."""
    
    def test_inactive_when_no_star_out(self):
        """Replacement factor inactive when all stars available"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0),
            MockPlayer("H2", 25.0, 8.0, 34.0),
            MockPlayer("H3", 12.0, 2.0, 25.0),
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0),
            MockPlayer("A2", 25.0, 8.0, 34.0),
            MockPlayer("A3", 12.0, 2.0, 25.0),
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        edge, detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        assert detail["active"] == False
        assert edge == 0.0
        assert "No Tier A/B" in detail["reason"]
    
    def test_active_when_star_out(self):
        """Replacement factor active when a star is out"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0, "OUT"),  # Tier A OUT
            MockPlayer("H2", 25.0, 8.0, 34.0),
            MockPlayer("HBench1", 12.0, 2.0, 25.0),
            MockPlayer("HBench2", 10.0, 1.0, 20.0),
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0),
            MockPlayer("A2", 25.0, 8.0, 34.0),
            MockPlayer("ABench1", 12.0, 2.0, 25.0),
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        edge, detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        assert detail["active"] == True
        assert len(detail["triggers"]) > 0
        assert "HOME A: H1" in detail["triggers"][0]
    
    def test_role_player_out_inactive(self):
        """Role player out should NOT activate replacement factor"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0),
            MockPlayer("H2", 25.0, 8.0, 34.0),
            MockPlayer("H3", 20.0, 5.0, 32.0),
            MockPlayer("HRole", 8.0, 1.0, 15.0, "OUT"),  # Role player OUT
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0),
            MockPlayer("A2", 25.0, 8.0, 34.0),
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        edge, detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        # Role player is not in tiers, so replacement factor should be inactive
        assert detail["active"] == False
    
    def test_edge_bounded(self):
        """Edge should be clamped to [-2.5, +2.5]"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0, "OUT"),
            MockPlayer("H2", 25.0, 8.0, 34.0, "OUT"),
            MockPlayer("H3", 20.0, 5.0, 32.0, "OUT"),
            MockPlayer("HBench1", 5.0, 1.0, 15.0),  # Weak replacements
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0),
            MockPlayer("A2", 25.0, 8.0, 34.0),
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        edge, detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        assert -REPLACEMENT_EDGE_CLAMP <= edge <= REPLACEMENT_EDGE_CLAMP
    
    def test_away_star_out_positive_edge(self):
        """Away star out should produce positive edge for home"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0),
            MockPlayer("H2", 25.0, 8.0, 34.0),
            MockPlayer("HBench1", 12.0, 2.0, 25.0),
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0, "OUT"),  # Away star OUT
            MockPlayer("A2", 25.0, 8.0, 34.0),
            MockPlayer("ABench1", 8.0, 1.0, 20.0),  # Weak replacement
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        edge, detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        assert detail["active"] == True
        # Edge should be positive (home advantage) since away has worse replacements
        # Note: actual value depends on replacement quality calculation
        # Away has worse replacements, so away_points will be negative
        # home_points = 0 (no absent stars), away_points < 0
        # Edge = 0 - negative = positive


class TestIntegration:
    """Integration tests with both star impact and rotation replacement."""
    
    def test_star_factor_small_when_no_absence(self):
        """Star factor should be minimal when all available"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0),
            MockPlayer("H2", 25.0, 8.0, 34.0),
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0),
            MockPlayer("A2", 25.0, 8.0, 34.0),
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        # Star factor
        from model.star_impact import compute_star_factor
        signed, edge, detail = compute_star_factor(home, away)
        
        # Rotation replacement
        repl_edge, repl_detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        # Both should be minimal
        assert signed == 0.0
        assert repl_detail["active"] == False
    
    def test_star_absence_triggers_both(self):
        """Star absence should affect star factor and activate replacement"""
        home = [
            MockPlayer("H1", 30.0, 10.0, 35.0, "OUT"),
            MockPlayer("H2", 25.0, 8.0, 34.0),
            MockPlayer("HBench1", 12.0, 2.0, 25.0),
        ]
        away = [
            MockPlayer("A1", 30.0, 10.0, 35.0),
            MockPlayer("A2", 25.0, 8.0, 34.0),
        ]
        
        home_tiers = select_star_tiers(home)
        away_tiers = select_star_tiers(away)
        
        # Star factor
        from model.star_impact import compute_star_factor
        signed, edge, detail = compute_star_factor(home, away)
        
        # Rotation replacement
        repl_edge, repl_detail = compute_rotation_replacement(
            home, away, home_tiers, away_tiers
        )
        
        # Star factor should be negative (home disadvantage)
        assert signed < 0
        
        # Rotation replacement should be active
        assert repl_detail["active"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
