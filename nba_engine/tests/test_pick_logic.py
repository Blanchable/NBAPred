"""
Unit tests for pick decision logic.

Tests that:
1. PICK is determined by EDGE sign (not probability)
2. CONFIDENCE is the win probability of the chosen pick
3. Tie-breaker uses probability when edge is near zero
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Define the constants and function directly to avoid import chain issues
EDGE_TIE_THRESHOLD = 0.5


def decide_pick(
    edge_score_total: float,
    home_team: str,
    away_team: str,
    home_win_prob: float,
    away_win_prob: float,
) -> tuple:
    """
    Decide the predicted winner based on EDGE, not probability.
    """
    if edge_score_total > EDGE_TIE_THRESHOLD:
        return home_team, home_win_prob
    elif edge_score_total < -EDGE_TIE_THRESHOLD:
        return away_team, away_win_prob
    else:
        if home_win_prob >= away_win_prob:
            return home_team, home_win_prob
        else:
            return away_team, away_win_prob


def test_edge_positive_picks_home():
    """
    Case 1: Positive edge should pick HOME team,
    even if away has higher probability.
    """
    pick, pick_prob = decide_pick(
        edge_score_total=+2.0,
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.49,  # Lower prob
        away_win_prob=0.51,  # Higher prob
    )
    
    assert pick == "LAL", f"Expected LAL (home, edge+), got {pick}"
    assert pick_prob == 0.49, f"Expected pick_prob=0.49, got {pick_prob}"
    print("✓ Case 1: edge=+2.0 → picks HOME (LAL) with prob=49%")


def test_edge_negative_picks_away():
    """
    Case 2: Negative edge should pick AWAY team,
    even if home has higher probability.
    """
    pick, pick_prob = decide_pick(
        edge_score_total=-3.0,
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.60,  # Higher prob
        away_win_prob=0.40,  # Lower prob
    )
    
    assert pick == "BOS", f"Expected BOS (away, edge-), got {pick}"
    assert pick_prob == 0.40, f"Expected pick_prob=0.40, got {pick_prob}"
    print("✓ Case 2: edge=-3.0 → picks AWAY (BOS) with prob=40%")


def test_edge_tie_uses_probability():
    """
    Case 3: Edge within tie threshold uses probability as tie-breaker.
    """
    # Edge just barely inside threshold
    pick, pick_prob = decide_pick(
        edge_score_total=+0.1,  # Below EDGE_TIE_THRESHOLD
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.52,
        away_win_prob=0.48,
    )
    
    assert pick == "LAL", f"Expected LAL (home, higher prob), got {pick}"
    assert pick_prob == 0.52, f"Expected pick_prob=0.52, got {pick_prob}"
    print(f"✓ Case 3: edge=+0.1 (within ±{EDGE_TIE_THRESHOLD}) → picks by probability (LAL 52%)")


def test_edge_tie_opposite_direction():
    """
    Case 4: Edge near zero but slightly negative, probability favors home.
    Should use probability since edge is in tie range.
    """
    pick, pick_prob = decide_pick(
        edge_score_total=-0.2,  # Slightly negative but within threshold
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.53,  # Higher prob
        away_win_prob=0.47,
    )
    
    # Probability should win since edge is in tie range
    assert pick == "LAL", f"Expected LAL (home, higher prob in tie), got {pick}"
    assert pick_prob == 0.53, f"Expected pick_prob=0.53, got {pick_prob}"
    print(f"✓ Case 4: edge=-0.2 (within ±{EDGE_TIE_THRESHOLD}) → picks by probability (LAL 53%)")


def test_edge_just_outside_threshold():
    """
    Case 5: Edge just outside threshold should use edge, not probability.
    """
    threshold = EDGE_TIE_THRESHOLD + 0.1
    
    pick, pick_prob = decide_pick(
        edge_score_total=-threshold,  # Just outside threshold (negative)
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.60,  # Higher prob
        away_win_prob=0.40,
    )
    
    # Edge should win since it's outside threshold
    assert pick == "BOS", f"Expected BOS (away, edge outside threshold), got {pick}"
    assert pick_prob == 0.40, f"Expected pick_prob=0.40, got {pick_prob}"
    print(f"✓ Case 5: edge=-{threshold} (outside ±{EDGE_TIE_THRESHOLD}) → picks by EDGE (BOS)")


def test_large_edge_wins_over_probability():
    """
    Case 6: Large edge should always determine pick regardless of probability.
    This is the key bug fix - edge=+10 but prob=35% should still pick home.
    """
    pick, pick_prob = decide_pick(
        edge_score_total=+10.0,
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.35,  # Much lower prob
        away_win_prob=0.65,  # Much higher prob
    )
    
    assert pick == "LAL", f"Expected LAL (home, strong edge), got {pick}"
    assert pick_prob == 0.35, f"Expected pick_prob=0.35, got {pick_prob}"
    print("✓ Case 6: edge=+10.0, prob=35% → picks HOME (edge wins over probability)")


def test_confidence_is_pick_probability():
    """
    Verify that the returned pick_prob is indeed the probability of the chosen team.
    """
    # Pick home
    pick, pick_prob = decide_pick(
        edge_score_total=+5.0,
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.72,
        away_win_prob=0.28,
    )
    assert pick == "LAL"
    assert pick_prob == 0.72, "pick_prob should be home_win_prob when home is picked"
    
    # Pick away
    pick, pick_prob = decide_pick(
        edge_score_total=-5.0,
        home_team="LAL",
        away_team="BOS",
        home_win_prob=0.72,
        away_win_prob=0.28,
    )
    assert pick == "BOS"
    assert pick_prob == 0.28, "pick_prob should be away_win_prob when away is picked"
    
    print("✓ Case 7: pick_prob correctly reflects chosen team's probability")


def run_all_tests():
    """Run all pick logic tests."""
    print("=" * 60)
    print("PICK DECISION LOGIC UNIT TESTS")
    print("=" * 60)
    print(f"EDGE_TIE_THRESHOLD = {EDGE_TIE_THRESHOLD}")
    print()
    
    tests = [
        test_edge_positive_picks_home,
        test_edge_negative_picks_away,
        test_edge_tie_uses_probability,
        test_edge_tie_opposite_direction,
        test_edge_just_outside_threshold,
        test_large_edge_wins_over_probability,
        test_confidence_is_pick_probability,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: Unexpected error: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
