"""
Sanity check tests for availability normalization.

These tests ensure that personal reasons, rest, suspension, etc.
are properly treated as OUT, not AVAILABLE.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.availability import (
    CanonicalStatus,
    normalize_availability,
    normalize_player_name,
    names_match,
)


def test_personal_reasons_is_out():
    """Out with personal reasons must be OUT."""
    status = normalize_availability("Out", "Personal Reasons")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Personal Reasons' -> OUT")


def test_rest_is_out():
    """Rest/load management must be OUT."""
    status = normalize_availability("Out", "Rest")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Rest' -> OUT")
    
    status = normalize_availability("Out", "Injury/Illness - Load Management")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Load Management' -> OUT")


def test_inactive_is_out():
    """Inactive status must be OUT."""
    status = normalize_availability("Inactive", "")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Inactive' -> OUT")


def test_suspended_is_out():
    """Suspension must be OUT."""
    status = normalize_availability("Out", "Suspended - One Game")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Suspended' -> OUT")


def test_g_league_is_out():
    """G League assignment must be OUT."""
    status = normalize_availability("Out", "G League - Two-Way")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'G League' -> OUT")


def test_illness_is_out():
    """Illness must be OUT."""
    status = normalize_availability("Out", "Illness")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Illness' -> OUT")


def test_health_safety_protocol_is_out():
    """Health and Safety Protocol must be OUT."""
    status = normalize_availability("Out", "Health and Safety Protocols")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Health and Safety Protocols' -> OUT")


def test_not_with_team_is_out():
    """Not with team must be OUT."""
    status = normalize_availability("Out", "Not With Team")
    assert status == CanonicalStatus.OUT, f"Expected OUT, got {status}"
    print("✓ 'Out' + 'Not With Team' -> OUT")


def test_questionable_stays_questionable():
    """Questionable injury stays QUESTIONABLE."""
    status = normalize_availability("Questionable", "Left Ankle Sprain")
    assert status == CanonicalStatus.QUESTIONABLE, f"Expected QUESTIONABLE, got {status}"
    print("✓ 'Questionable' + injury -> QUESTIONABLE")


def test_doubtful_stays_doubtful():
    """Doubtful injury stays DOUBTFUL."""
    status = normalize_availability("Doubtful", "Right Knee Soreness")
    assert status == CanonicalStatus.DOUBTFUL, f"Expected DOUBTFUL, got {status}"
    print("✓ 'Doubtful' + injury -> DOUBTFUL")


def test_probable_stays_probable():
    """Probable injury stays PROBABLE."""
    status = normalize_availability("Probable", "Back Tightness")
    assert status == CanonicalStatus.PROBABLE, f"Expected PROBABLE, got {status}"
    print("✓ 'Probable' + injury -> PROBABLE")


def test_available_default():
    """Empty/unknown status defaults to AVAILABLE."""
    status = normalize_availability("", "")
    assert status == CanonicalStatus.AVAILABLE, f"Expected AVAILABLE, got {status}"
    print("✓ Empty status -> AVAILABLE")


def test_name_normalization():
    """Test player name normalization."""
    # Test suffix removal
    assert normalize_player_name("LeBron James Jr.") == "lebron james"
    print("✓ 'LeBron James Jr.' -> 'lebron james'")
    
    # Test accent removal
    assert normalize_player_name("Nikola Jokić") == "nikola jokic"
    print("✓ 'Nikola Jokić' -> 'nikola jokic'")
    
    # Test punctuation removal
    assert normalize_player_name("Shai Gilgeous-Alexander") == "shai gilgeousalexander"
    print("✓ Punctuation removed")


def test_name_matching():
    """Test player name matching."""
    # Exact match
    assert names_match("James Harden", "James Harden")
    print("✓ Exact match works")
    
    # Case insensitive
    assert names_match("JAMES HARDEN", "james harden")
    print("✓ Case insensitive match works")
    
    # Last name match with first initial
    assert names_match("James Harden", "J. Harden")
    print("✓ Last name + initial match works")
    
    # Suffix handling
    assert names_match("Gary Trent Jr.", "Gary Trent")
    print("✓ Suffix ignored in matching")


def run_all_tests():
    """Run all sanity check tests."""
    print("=" * 50)
    print("AVAILABILITY SANITY CHECK TESTS")
    print("=" * 50)
    print()
    
    tests = [
        test_personal_reasons_is_out,
        test_rest_is_out,
        test_inactive_is_out,
        test_suspended_is_out,
        test_g_league_is_out,
        test_illness_is_out,
        test_health_safety_protocol_is_out,
        test_not_with_team_is_out,
        test_questionable_stays_questionable,
        test_doubtful_stays_doubtful,
        test_probable_stays_probable,
        test_available_default,
        test_name_normalization,
        test_name_matching,
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
    print("=" * 50)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
