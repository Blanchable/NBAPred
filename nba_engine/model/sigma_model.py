"""
Margin volatility (sigma) estimator for NBA Prediction Engine.

Produces a per-game estimate of the standard deviation of the actual
margin around the model's predicted margin.  Used by spread_pricing
to compute cover probabilities and +EV thresholds.

Two sources:
1. Signal-based sigma  — always available, derived from game context
   (pace, variance flags, instability, injuries).
2. Empirical sigma     — available once enough graded games exist;
   computed as std(actual_margin − predicted_margin) from history.

When both are available they are blended (70 % empirical / 30 % signal).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import (
    SIGMA_BASE,
    SIGMA_MIN,
    SIGMA_MAX,
    SIGMA_EMPIRICAL_BLEND,
    SIGMA_MIN_SAMPLES,
)


# ============================================================================
# SIGNAL-BASED SIGMA
# ============================================================================

@dataclass
class SigmaContext:
    """Contextual inputs for per-game sigma estimation."""
    exp_poss: float = 99.0               # expected possessions for the game
    home_fg3a_rate: float = 0.40         # home 3PA rate (proxy for variance)
    away_fg3a_rate: float = 0.40
    instability_home: float = 0.0
    instability_away: float = 0.0
    questionable_count: int = 0          # total Q/DTD players across both teams
    tier1_creator_out: bool = False      # any T1 creator OUT?
    variance_score: float = 0.0          # totals variance score (0–1)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def sigma_signal(ctx: SigmaContext) -> float:
    """
    Estimate margin sigma from game-context signals.

    Starts at SIGMA_BASE (12.0) and adjusts for:
    - Pace (faster games → more variance)
    - 3P reliance (high FG3A rate → more variance)
    - Roster instability (unstable teams → harder to predict)
    - Questionable players (more uncertainty)
    - T1 creator OUT (replacement-level offence is noisier)
    """
    sigma = SIGMA_BASE

    # Pace effect: ±0.6 for ±8 possessions from league average
    sigma += 0.08 * (ctx.exp_poss - 99.0)

    # 3P reliance — both teams' rates above 0.42 bump variance
    avg_fg3a = (ctx.home_fg3a_rate + ctx.away_fg3a_rate) / 2
    if avg_fg3a > 0.42:
        sigma += 1.0
    elif avg_fg3a > 0.38:
        sigma += 0.4

    # Roster instability
    worst_inst = max(ctx.instability_home, ctx.instability_away)
    if worst_inst >= 0.30:
        sigma += 1.0
    elif worst_inst >= 0.10:
        sigma += 0.4

    # Questionable players
    sigma += min(1.2, 0.3 * ctx.questionable_count)

    # T1 creator OUT
    if ctx.tier1_creator_out:
        sigma += 0.8

    # Totals variance score (0–1 scale from totals_prediction)
    if ctx.variance_score > 0.6:
        sigma += 0.5

    return _clamp(sigma, SIGMA_MIN, SIGMA_MAX)


# ============================================================================
# EMPIRICAL SIGMA (from graded prediction history)
# ============================================================================

def load_empirical_sigma() -> Optional[float]:
    """
    Load the empirical margin-error std dev from the calibration artefact.

    Returns None if not available or not enough samples.
    """
    try:
        from analysis.calibration import load_calibration
        artifact = load_calibration()
        if artifact is None:
            return None
        if artifact.get("sample_size", 0) < SIGMA_MIN_SAMPLES:
            return None
        sigma_emp = artifact.get("margin_error_std")
        if sigma_emp is not None and sigma_emp > 0:
            return float(sigma_emp)
    except Exception:
        pass
    return None


# ============================================================================
# BLENDED SIGMA (final output)
# ============================================================================

def compute_sigma(ctx: SigmaContext) -> float:
    """
    Compute the final per-game margin sigma.

    Blends empirical (70 %) and signal-based (30 %) sigma when empirical
    is available; otherwise falls back to signal-only.
    """
    sig_signal = sigma_signal(ctx)

    sig_emp = load_empirical_sigma()
    if sig_emp is not None:
        blended = SIGMA_EMPIRICAL_BLEND * sig_emp + (1 - SIGMA_EMPIRICAL_BLEND) * sig_signal
        return _clamp(blended, SIGMA_MIN, SIGMA_MAX)

    return sig_signal
