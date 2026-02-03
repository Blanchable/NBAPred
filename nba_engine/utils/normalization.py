"""
Normalization utilities for the NBA prediction engine.
"""

from typing import Optional


def clamp(value: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
    """
    Clamp a value to a range.
    
    Args:
        value: Value to clamp.
        min_val: Minimum value (default -1).
        max_val: Maximum value (default 1).
    
    Returns:
        Clamped value.
    """
    return max(min_val, min(max_val, value))


def normalize_to_range(
    value: float,
    src_min: float,
    src_max: float,
    dst_min: float = 0.0,
    dst_max: float = 1.0,
) -> float:
    """
    Normalize a value from source range to destination range.
    
    Args:
        value: Value to normalize.
        src_min: Source range minimum.
        src_max: Source range maximum.
        dst_min: Destination range minimum (default 0).
        dst_max: Destination range maximum (default 1).
    
    Returns:
        Normalized value.
    """
    if src_max == src_min:
        return (dst_min + dst_max) / 2
    
    normalized = (value - src_min) / (src_max - src_min)
    return dst_min + normalized * (dst_max - dst_min)


def z_score(value: float, mean: float, std: float) -> float:
    """
    Calculate z-score (standard score).
    
    Args:
        value: Value to score.
        mean: Population mean.
        std: Population standard deviation.
    
    Returns:
        Z-score.
    """
    if std == 0:
        return 0.0
    return (value - mean) / std


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero.
    """
    if denominator == 0:
        return default
    return numerator / denominator


def safe_get(data: dict, key: str, default: float = 0.0) -> float:
    """
    Safely get a numeric value from a dict.
    """
    val = data.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
