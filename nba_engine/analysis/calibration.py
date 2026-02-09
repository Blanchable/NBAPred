"""
Confidence calibration module for NBA Prediction Engine.

Measures how well the model's raw Conf% matches actual win rates,
fits a monotonic calibration mapping, and provides functions to
transform raw confidence into calibrated confidence.

The calibration artefact is persisted as JSON so the GUI can load
it without refitting every time.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ============================================================================
# CONSTANTS
# ============================================================================

# Minimum graded games before calibration is used
MIN_CALIBRATION_SAMPLES = 200

# Default lookback window (days)
DEFAULT_LOOKBACK_DAYS = 60

# Default bin edges (percent, right-exclusive except last)
DEFAULT_BIN_EDGES = [50, 52, 55, 58, 62, 66, 70, 75, 80, 100]

# Calibrated bucket thresholds
CAL_BUCKET_HIGH = 62.0
CAL_BUCKET_MED = 55.0

# Clamp range for displayed calibrated confidence
CAL_CONF_MIN = 50.0
CAL_CONF_MAX = 95.0

# Persistence path
_CALIBRATION_DIR = Path(__file__).resolve().parent.parent / "data" / "calibration"
CALIBRATION_FILE = _CALIBRATION_DIR / "calibration_mapping.json"


# ============================================================================
# 2A) LOAD GRADED GAMES FROM DB
# ============================================================================

def load_graded_games(since_days: int = DEFAULT_LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """
    Load graded (W/L) picks from the SQLite database within the lookback
    window.

    Returns:
        List of dicts with keys: slate_date, game_id, pick_side, conf_pct,
        bucket, result, away_team, home_team, away_score, home_score.
    """
    from storage.db import connect

    cutoff = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")

    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT dp.slate_date, dp.game_id, dp.pick_side,
               dp.conf_pct, dp.bucket, dp.result,
               g.away_team, g.home_team, g.away_score, g.home_score
        FROM daily_picks dp
        JOIN games g ON dp.game_id = g.game_id
        WHERE dp.result IN ('W', 'L')
          AND dp.slate_date >= ?
        ORDER BY dp.slate_date
    """, (cutoff,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ============================================================================
# 2B) BIN CONSTRUCTION
# ============================================================================

def make_conf_bins(
    bin_edges: Optional[List[float]] = None,
) -> List[Tuple[float, float]]:
    """
    Create confidence bins from edge list.

    Returns:
        List of (low, high) tuples.  The last bin's high is inclusive.
    """
    edges = bin_edges or DEFAULT_BIN_EDGES
    bins = []
    for i in range(len(edges) - 1):
        bins.append((edges[i], edges[i + 1]))
    return bins


# ============================================================================
# 2C) BIN STATISTICS
# ============================================================================

def compute_bin_stats(
    rows: List[Dict[str, Any]],
    bins: Optional[List[Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """
    Compute per-bin and overall calibration statistics.

    Returns dict with:
        bins: list of {low, high, n, wins, losses, win_rate, avg_conf, brier}
        overall_n, overall_wins, overall_win_rate, overall_brier, avg_abs_error
    """
    if bins is None:
        bins = make_conf_bins()

    # Initialise accumulators
    bin_data = []
    for low, high in bins:
        bin_data.append({
            "low": low, "high": high,
            "n": 0, "wins": 0, "losses": 0,
            "conf_sum": 0.0, "brier_sum": 0.0,
        })

    overall_brier_sum = 0.0
    overall_n = 0
    overall_wins = 0

    for row in rows:
        conf = float(row.get("conf_pct", 50))
        result = row.get("result", "")
        if result not in ("W", "L"):
            continue
        y = 1.0 if result == "W" else 0.0
        p = max(conf, 50.0) / 100.0  # clamp below 50

        brier = (p - y) ** 2
        overall_brier_sum += brier
        overall_n += 1
        if y == 1.0:
            overall_wins += 1

        # Assign to bin
        for bd in bin_data:
            if bd["low"] <= conf < bd["high"] or (bd["high"] == 100 and conf >= bd["low"]):
                bd["n"] += 1
                if y == 1.0:
                    bd["wins"] += 1
                else:
                    bd["losses"] += 1
                bd["conf_sum"] += conf
                bd["brier_sum"] += brier
                break

    # Compute rates
    result_bins = []
    abs_errors = []
    for bd in bin_data:
        n = bd["n"]
        win_rate = (bd["wins"] / n) if n > 0 else None
        avg_conf = (bd["conf_sum"] / n) if n > 0 else (bd["low"] + bd["high"]) / 2
        brier = (bd["brier_sum"] / n) if n > 0 else None

        if win_rate is not None:
            abs_errors.append(abs(win_rate * 100 - avg_conf))

        result_bins.append({
            "low": bd["low"],
            "high": bd["high"],
            "n": n,
            "wins": bd["wins"],
            "losses": bd["losses"],
            "win_rate": round(win_rate * 100, 1) if win_rate is not None else None,
            "avg_conf": round(avg_conf, 1),
            "brier": round(brier, 4) if brier is not None else None,
        })

    overall_brier = (overall_brier_sum / overall_n) if overall_n > 0 else None
    overall_win_rate = (overall_wins / overall_n * 100) if overall_n > 0 else None
    avg_abs_error = (sum(abs_errors) / len(abs_errors)) if abs_errors else None

    return {
        "bins": result_bins,
        "overall_n": overall_n,
        "overall_wins": overall_wins,
        "overall_win_rate": round(overall_win_rate, 1) if overall_win_rate is not None else None,
        "overall_brier": round(overall_brier, 4) if overall_brier is not None else None,
        "avg_abs_error": round(avg_abs_error, 1) if avg_abs_error is not None else None,
    }


# ============================================================================
# 2D) FIT CALIBRATION MAPPING (Isotonic or PAV fallback)
# ============================================================================

def _pool_adjacent_violators(x: List[float], y: List[float]) -> List[float]:
    """
    Simple Pool Adjacent Violators (PAV) to enforce monotonicity.

    Operates on sorted (x, y) pairs (ascending x) and returns
    monotonically non-decreasing y values.
    """
    n = len(y)
    if n == 0:
        return []
    result = list(y)
    # weights (equal)
    w = [1.0] * n
    i = 0
    while i < n - 1:
        if result[i] > result[i + 1]:
            # Pool i and i+1
            new_val = (result[i] * w[i] + result[i + 1] * w[i + 1]) / (w[i] + w[i + 1])
            new_w = w[i] + w[i + 1]
            result[i] = new_val
            w[i] = new_w
            result.pop(i + 1)
            w.pop(i + 1)
            n -= 1
            # Step back to check previous
            if i > 0:
                i -= 1
        else:
            i += 1
    # Expand back
    return result


def fit_calibration_mapping(
    rows: List[Dict[str, Any]],
) -> Tuple[Optional[Callable[[float], float]], Dict[str, Any]]:
    """
    Fit a monotonic calibration function from graded games.

    Tries sklearn IsotonicRegression first; falls back to bin-based PAV.

    Args:
        rows: Graded game dicts with conf_pct and result.

    Returns:
        (mapping_fn, metadata_dict)
        mapping_fn: callable  f(p_raw_0to1) -> p_cal_0to1 , or None if
                    not enough samples.
        metadata_dict: info for persistence (method, mapping_points, etc.)
    """
    # Filter and build arrays
    xs = []
    ys = []
    for row in rows:
        result = row.get("result", "")
        if result not in ("W", "L"):
            continue
        conf = float(row.get("conf_pct", 50))
        p = max(conf, 50.0) / 100.0
        y = 1.0 if result == "W" else 0.0
        xs.append(p)
        ys.append(y)

    if len(xs) < MIN_CALIBRATION_SAMPLES:
        return None, {"method": "none", "reason": f"only {len(xs)} samples (need {MIN_CALIBRATION_SAMPLES})"}

    # Try sklearn
    try:
        from sklearn.isotonic import IsotonicRegression
        ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        ir.fit(xs, ys)

        # Extract mapping points for persistence
        x_pts = sorted(set(xs))
        y_pts = [float(ir.predict([x])[0]) for x in x_pts]

        return ir.predict, {
            "method": "isotonic",
            "mapping_points": list(zip(x_pts, y_pts)),
            "sample_size": len(xs),
        }
    except ImportError:
        pass

    # Fallback: bin-based PAV
    bins = make_conf_bins()
    bin_xs = []
    bin_ys = []
    for low, high in bins:
        in_bin = [(x, y) for x, y in zip(xs, ys)
                  if (low / 100) <= x < (high / 100) or (high == 100 and x >= low / 100)]
        if in_bin:
            avg_x = sum(bx for bx, _ in in_bin) / len(in_bin)
            avg_y = sum(by for _, by in in_bin) / len(in_bin)
            bin_xs.append(avg_x)
            bin_ys.append(avg_y)

    if len(bin_xs) < 2:
        return None, {"method": "none", "reason": "too few populated bins"}

    # Enforce monotonicity
    pav_ys = _pool_adjacent_violators(bin_xs, bin_ys)

    # Build piecewise-linear interpolator
    mapping_points = list(zip(bin_xs, pav_ys))

    def _piecewise(p_raw: float) -> float:
        if p_raw <= mapping_points[0][0]:
            return mapping_points[0][1]
        if p_raw >= mapping_points[-1][0]:
            return mapping_points[-1][1]
        for i in range(len(mapping_points) - 1):
            x0, y0 = mapping_points[i]
            x1, y1 = mapping_points[i + 1]
            if x0 <= p_raw <= x1:
                t = (p_raw - x0) / (x1 - x0) if x1 != x0 else 0
                return y0 + t * (y1 - y0)
        return p_raw  # shouldn't reach

    return _piecewise, {
        "method": "bin_pav",
        "mapping_points": mapping_points,
        "sample_size": len(xs),
    }


# ============================================================================
# 2E-F) APPLY CALIBRATION + BUCKET
# ============================================================================

def apply_calibration(conf_pct_raw: float, mapping_fn: Callable) -> float:
    """
    Apply calibration mapping to a raw confidence percentage.

    Args:
        conf_pct_raw: Raw model confidence (50-100 scale).
        mapping_fn:   Callable f(p_0to1) -> p_cal_0to1.

    Returns:
        Calibrated confidence percentage, clamped to [50, 95].
    """
    p_raw = max(conf_pct_raw, 50.0) / 100.0
    p_cal = mapping_fn(p_raw)
    conf_cal = p_cal * 100.0
    return max(CAL_CONF_MIN, min(CAL_CONF_MAX, round(conf_cal, 1)))


def compute_calibrated_bucket(conf_pct_cal: float) -> str:
    """Assign calibrated confidence to a bucket."""
    if conf_pct_cal >= CAL_BUCKET_HIGH:
        return "HIGH"
    elif conf_pct_cal >= CAL_BUCKET_MED:
        return "MEDIUM"
    else:
        return "LOW"


# ============================================================================
# 3) PERSISTENCE
# ============================================================================

def save_calibration(
    bin_stats: Dict[str, Any],
    mapping_meta: Dict[str, Any],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> Path:
    """Save calibration artefact to JSON."""
    _CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

    artifact = {
        "generated_at": datetime.now().isoformat(),
        "lookback_days": lookback_days,
        "sample_size": mapping_meta.get("sample_size", 0),
        "method": mapping_meta.get("method", "none"),
        "bin_edges": DEFAULT_BIN_EDGES,
        "per_bin_stats": bin_stats.get("bins", []),
        "mapping_points": mapping_meta.get("mapping_points", []),
        "overall_brier": bin_stats.get("overall_brier"),
        "overall_win_rate": bin_stats.get("overall_win_rate"),
        "avg_abs_error": bin_stats.get("avg_abs_error"),
    }

    with open(CALIBRATION_FILE, "w") as f:
        json.dump(artifact, f, indent=2)

    return CALIBRATION_FILE


def load_calibration() -> Optional[Dict[str, Any]]:
    """Load calibration artefact from JSON, or None if missing / corrupt."""
    if not CALIBRATION_FILE.exists():
        return None
    try:
        with open(CALIBRATION_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def build_mapping_fn_from_artifact(
    artifact: Dict[str, Any],
) -> Optional[Callable[[float], float]]:
    """
    Reconstruct a mapping function from a persisted calibration artefact.

    Returns None if artefact has no valid mapping_points or too few samples.
    """
    if artifact.get("sample_size", 0) < MIN_CALIBRATION_SAMPLES:
        return None

    points = artifact.get("mapping_points", [])
    if len(points) < 2:
        return None

    # Convert to list of tuples
    pts = [(float(p[0]), float(p[1])) for p in points]

    def _interp(p_raw: float) -> float:
        if p_raw <= pts[0][0]:
            return pts[0][1]
        if p_raw >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            if x0 <= p_raw <= x1:
                t = (p_raw - x0) / (x1 - x0) if x1 != x0 else 0
                return y0 + t * (y1 - y0)
        return p_raw

    return _interp


# ============================================================================
# 6) END-TO-END CALIBRATION REFRESH
# ============================================================================

def refresh_calibration(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    force: bool = False,
) -> Dict[str, Any]:
    """
    End-to-end calibration refresh.

    1. Load graded games from DB.
    2. Compute bin stats.
    3. Fit mapping.
    4. Save artefact.
    5. Return summary.

    If not enough samples, saves a stub artefact with method="none".

    Args:
        lookback_days: How far back to look.
        force: If False, skip if artefact is < 24h old and no new
               graded games (heuristic: same sample_size).

    Returns:
        Summary dict with sample_size, brier, etc.
    """
    # Quick skip if not forced and artefact is fresh
    if not force:
        existing = load_calibration()
        if existing:
            gen_at = existing.get("generated_at", "")
            try:
                gen_dt = datetime.fromisoformat(gen_at)
                age_hours = (datetime.now() - gen_dt).total_seconds() / 3600
                if age_hours < 24:
                    return {
                        "skipped": True,
                        "reason": f"artefact is {age_hours:.0f}h old",
                        **existing,
                    }
            except (ValueError, TypeError):
                pass  # Can't parse — regenerate

    rows = load_graded_games(since_days=lookback_days)

    bins = make_conf_bins()
    bin_stats = compute_bin_stats(rows, bins)

    mapping_fn, mapping_meta = fit_calibration_mapping(rows)

    save_calibration(bin_stats, mapping_meta, lookback_days)

    sample_size = mapping_meta.get("sample_size", len(rows))
    method = mapping_meta.get("method", "none")
    brier = bin_stats.get("overall_brier")
    avg_err = bin_stats.get("avg_abs_error")

    print(f"  Calibration updated: {sample_size} samples, "
          f"method={method}, Brier={brier}, avg_abs_err={avg_err}")

    return {
        "skipped": False,
        "sample_size": sample_size,
        "method": method,
        "overall_brier": brier,
        "avg_abs_error": avg_err,
        "overall_win_rate": bin_stats.get("overall_win_rate"),
    }


def get_active_mapping_fn() -> Tuple[Optional[Callable], bool]:
    """
    Get the currently-active calibration mapping function.

    Returns:
        (mapping_fn_or_None, is_calibrated)
    """
    artifact = load_calibration()
    if artifact is None:
        return None, False
    fn = build_mapping_fn_from_artifact(artifact)
    return fn, fn is not None
