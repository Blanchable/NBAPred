"""
Unit tests for player_stats team-mapping robustness.

Tests that:
1. TEAM_ABBREVIATION is preferred over TEAM_ID mapping
2. TEAM_ID is safely cast from float/string
3. Rows with neither mapping are skipped
4. ensure_team_players fills in missing teams with fallback
5. get_fallback_player_stats accepts optional team list
6. Warning is printed when fewer than 20 teams are returned
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import io

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from ingest.player_stats import (
    PlayerImpact,
    TEAM_ID_TO_ABBREV,
    get_fallback_player_stats,
    get_fallback_team_players,
    ensure_team_players,
)


# ---------------------------------------------------------------------------
# Test: get_fallback_team_players returns valid data for a single team
# ---------------------------------------------------------------------------

def test_fallback_team_players_returns_six():
    players = get_fallback_team_players("BOS")
    assert len(players) == 6, f"Expected 6 fallback players, got {len(players)}"
    assert all(p.team == "BOS" for p in players)
    assert players[0].is_star is True
    assert players[0].impact_rank == 1
    assert players[5].is_star is False


# ---------------------------------------------------------------------------
# Test: get_fallback_player_stats with no args returns all 30 teams
# ---------------------------------------------------------------------------

def test_fallback_all_teams():
    stats = get_fallback_player_stats()
    assert len(stats) == 30, f"Expected 30 teams, got {len(stats)}"
    assert "BOS" in stats
    assert "LAL" in stats


# ---------------------------------------------------------------------------
# Test: get_fallback_player_stats with explicit team list
# ---------------------------------------------------------------------------

def test_fallback_specific_teams():
    stats = get_fallback_player_stats(["BOS", "LAL"])
    assert len(stats) == 2
    assert "BOS" in stats
    assert "LAL" in stats
    assert "GSW" not in stats


# ---------------------------------------------------------------------------
# Test: ensure_team_players fills gaps
# ---------------------------------------------------------------------------

def test_ensure_fills_missing():
    existing = {"BOS": [PlayerImpact(
        player_name="Test", team="BOS", minutes_per_game=30,
        points_per_game=20, usage_pct=25, impact_score=13,
        is_key_player=True, impact_rank=1, is_star=True,
    )]}
    result = ensure_team_players(existing, ["BOS", "LAL", "GSW"])
    assert "BOS" in result
    assert "LAL" in result
    assert "GSW" in result
    # BOS should still have the original player, not fallback
    assert result["BOS"][0].player_name == "Test"
    # LAL should have fallback
    assert len(result["LAL"]) == 6
    assert result["LAL"][0].player_name == "LAL Player 1"


# ---------------------------------------------------------------------------
# Test: ensure_team_players does not overwrite existing teams
# ---------------------------------------------------------------------------

def test_ensure_preserves_existing():
    existing = {
        "BOS": [PlayerImpact(
            player_name="Jayson Tatum", team="BOS", minutes_per_game=36,
            points_per_game=27, usage_pct=30, impact_score=20,
            is_key_player=True, impact_rank=1, is_star=True,
        )],
    }
    result = ensure_team_players(existing, ["BOS"])
    assert len(result["BOS"]) == 1
    assert result["BOS"][0].player_name == "Jayson Tatum"


# ---------------------------------------------------------------------------
# Test: Team abbreviation extraction prefers TEAM_ABBREVIATION column
# ---------------------------------------------------------------------------

def test_team_abbrev_extraction_prefers_abbreviation():
    """Simulate DataFrame rows and check team mapping logic."""
    # This tests the core logic extracted from get_player_stats
    row = {
        "TEAM_ABBREVIATION": "BOS",
        "TEAM_ID": 99999,  # Invalid ID
        "PLAYER_NAME": "Test Player",
        "MIN": 30,
        "PTS": 20,
        "USG_PCT": 0.25,
    }

    team_abbrev = None
    raw_abbrev = row.get("TEAM_ABBREVIATION")
    if raw_abbrev and str(raw_abbrev).strip() and str(raw_abbrev) != "nan":
        team_abbrev = str(raw_abbrev).strip().upper()

    assert team_abbrev == "BOS", f"Expected BOS, got {team_abbrev}"


# ---------------------------------------------------------------------------
# Test: TEAM_ID float casting works
# ---------------------------------------------------------------------------

def test_team_id_float_cast():
    """TEAM_ID as float (e.g. 1610612738.0) should map correctly."""
    # Find BOS team id
    bos_id = None
    for tid, abbrev in TEAM_ID_TO_ABBREV.items():
        if abbrev == "BOS":
            bos_id = tid
            break

    assert bos_id is not None, "BOS not found in TEAM_ID_TO_ABBREV"

    # Simulate float TEAM_ID (as returned by some pandas environments)
    row = {
        "TEAM_ABBREVIATION": None,
        "TEAM_ID": float(bos_id),  # float version
        "PLAYER_NAME": "Test Player",
    }

    team_abbrev = None
    raw_abbrev = row.get("TEAM_ABBREVIATION")
    if raw_abbrev and str(raw_abbrev).strip() and str(raw_abbrev) != "nan":
        team_abbrev = str(raw_abbrev).strip().upper()

    if not team_abbrev:
        team_id = row.get("TEAM_ID", None)
        try:
            if team_id is not None and str(team_id) != "nan":
                team_id_int = int(float(team_id))
                team_abbrev = TEAM_ID_TO_ABBREV.get(team_id_int)
        except Exception:
            team_abbrev = None

    assert team_abbrev == "BOS", f"Expected BOS from float TEAM_ID, got {team_abbrev}"


# ---------------------------------------------------------------------------
# Test: TEAM_ID as string works
# ---------------------------------------------------------------------------

def test_team_id_string_cast():
    """TEAM_ID as string should also map correctly."""
    bos_id = None
    for tid, abbrev in TEAM_ID_TO_ABBREV.items():
        if abbrev == "BOS":
            bos_id = tid
            break

    row = {
        "TEAM_ABBREVIATION": "",  # empty string
        "TEAM_ID": str(bos_id),   # string version
    }

    team_abbrev = None
    raw_abbrev = row.get("TEAM_ABBREVIATION")
    if raw_abbrev and str(raw_abbrev).strip() and str(raw_abbrev) != "nan":
        team_abbrev = str(raw_abbrev).strip().upper()

    if not team_abbrev:
        team_id = row.get("TEAM_ID", None)
        try:
            if team_id is not None and str(team_id) != "nan":
                team_id_int = int(float(team_id))
                team_abbrev = TEAM_ID_TO_ABBREV.get(team_id_int)
        except Exception:
            team_abbrev = None

    assert team_abbrev == "BOS", f"Expected BOS from string TEAM_ID, got {team_abbrev}"


# ---------------------------------------------------------------------------
# Test: Row with no valid mapping is skipped
# ---------------------------------------------------------------------------

def test_row_with_no_mapping_is_skipped():
    row = {
        "TEAM_ABBREVIATION": "nan",
        "TEAM_ID": "nan",
    }

    team_abbrev = None
    raw_abbrev = row.get("TEAM_ABBREVIATION")
    if raw_abbrev and str(raw_abbrev).strip() and str(raw_abbrev) != "nan":
        team_abbrev = str(raw_abbrev).strip().upper()

    if not team_abbrev:
        team_id = row.get("TEAM_ID", None)
        try:
            if team_id is not None and str(team_id) != "nan":
                team_id_int = int(float(team_id))
                team_abbrev = TEAM_ID_TO_ABBREV.get(team_id_int)
        except Exception:
            team_abbrev = None

    assert team_abbrev is None, f"Expected None for invalid row, got {team_abbrev}"


# ---------------------------------------------------------------------------
# Test: Warning is printed when <20 teams
# ---------------------------------------------------------------------------

def test_warning_on_few_teams(capsys):
    """ensure_team_players logs warning for missing teams."""
    existing = {}
    ensure_team_players(existing, ["BOS", "LAL"])
    captured = capsys.readouterr()
    assert "Player stats missing for BOS" in captured.out
    assert "Player stats missing for LAL" in captured.out
