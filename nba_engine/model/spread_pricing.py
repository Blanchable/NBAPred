"""
Spread pricing module for NBA Prediction Engine.

Given the model's projected margin (HOME − AWAY) and an estimated
sigma (margin volatility), this module computes:

1. Fair spread (the model line)
2. Cover probability for any given spread
3. Minimum +EV spread thresholds assuming standard −110 juice

All spreads are expressed as the HOME line by convention:
  HOME −5.5 means home must win by 6+
  HOME +3.5 means home can lose by up to 3

No external dependencies — uses math.erf for the normal CDF.
"""

from __future__ import annotations

import math

from .config import BREAKEVEN_PCT_MINUS_110, Z_BREAKEVEN_MINUS_110


# ============================================================================
# NORMAL CDF (no scipy/numpy needed)
# ============================================================================

def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ============================================================================
# COVER PROBABILITY
# ============================================================================

def cover_prob_home(mu: float, sigma: float, spread_home: float) -> float:
    """
    Probability that HOME covers a given spread.

    HOME covers when actual margin M > −spread_home.
    (If spread_home = −5.5, HOME must win by 6+, i.e. M > 5.5.)

    Args:
        mu:           Predicted margin HOME − AWAY.
        sigma:        Margin volatility (std dev).
        spread_home:  HOME line (e.g. −5.5).

    Returns:
        Probability ∈ (0, 1).
    """
    if sigma <= 0:
        return 0.5
    z = ((-spread_home) - mu) / sigma
    return 1.0 - norm_cdf(z)


def cover_prob_away(mu: float, sigma: float, spread_home: float) -> float:
    """Probability that AWAY covers (complement of HOME covering)."""
    return 1.0 - cover_prob_home(mu, sigma, spread_home)


# ============================================================================
# FAIR SPREAD
# ============================================================================

def fair_spread_home(mu: float) -> float:
    """
    Fair HOME spread where cover probability is exactly 50 %.

    Returns:
        HOME line (negative if home favoured).
    """
    return -mu


# ============================================================================
# MINIMUM +EV SPREAD THRESHOLDS (at −110)
# ============================================================================

def min_ev_spread_for_home_bet(
    mu: float,
    sigma: float,
    z: float = Z_BREAKEVEN_MINUS_110,
) -> float:
    """
    Threshold HOME line for a +EV HOME bet at −110.

    You should only bet HOME if the sportsbook HOME line is ≥ this value
    (i.e. less negative or more positive than this threshold).

    Example: mu = +6, sigma = 12 → threshold ≈ −5.3.
    HOME −5.0 is +EV; HOME −5.5 is slightly −EV.
    """
    return -(mu - z * sigma)


def min_ev_spread_for_away_bet(
    mu: float,
    sigma: float,
    z: float = Z_BREAKEVEN_MINUS_110,
) -> float:
    """
    Threshold HOME line for a +EV AWAY bet at −110.

    You should only bet AWAY if the sportsbook HOME line is ≤ this value
    (i.e. more negative than this threshold).

    Example: mu = −6 (away favoured), sigma = 12 → threshold ≈ +5.3.
    AWAY +5.5 is +EV; AWAY +5.0 is slightly −EV.
    """
    mu_away = -mu
    return mu_away - z * sigma


# ============================================================================
# FORMATTING
# ============================================================================

def format_spread(x: float) -> str:
    """Format a spread value with sign and 1 decimal."""
    return f"{x:+.1f}"


def format_spread_pick_perspective(
    mu: float,
    sigma: float,
    predicted_winner: str,
    home_team: str,
) -> dict:
    """
    Compute spread outputs from the *pick side's* perspective for display.

    Returns dict with:
        fair_line:     str   e.g. "BOS −5.5" or "WAS +6.0"
        sigma:         float
        min_ev_line:   str   e.g. "Lay ≤ −5.0" or "Take ≥ +6.5"
        fair_raw:      float (HOME line, for storage)
        min_ev_raw:    float (HOME line threshold, for storage)
    """
    fair_h = fair_spread_home(mu)
    min_ev_h_home = min_ev_spread_for_home_bet(mu, sigma)
    min_ev_h_away = min_ev_spread_for_away_bet(mu, sigma)

    pick_is_home = (predicted_winner == home_team)

    if pick_is_home:
        # Display as HOME line
        fair_display = f"{predicted_winner} {format_spread(fair_h)}"
        # "Lay no worse than X" — the threshold is min_ev_h_home
        min_ev_display = f"Lay ≤ {format_spread(min_ev_h_home)}"
        min_ev_raw = min_ev_h_home
    else:
        # Display as AWAY line (negate HOME line)
        fair_away = -fair_h
        fair_display = f"{predicted_winner} {format_spread(fair_away)}"
        # "Take at least X" — negate the away threshold
        min_ev_away = -min_ev_h_away
        min_ev_display = f"Take ≥ {format_spread(min_ev_away)}"
        min_ev_raw = min_ev_h_away  # store as HOME line for consistency

    return {
        "fair_line": fair_display,
        "sigma": round(sigma, 1),
        "min_ev_line": min_ev_display,
        "fair_spread_home": round(fair_h, 1),
        "min_ev_threshold_home": round(min_ev_raw, 1),
    }
