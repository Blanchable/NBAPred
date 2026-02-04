"""
Date utilities for NBA Prediction Engine.

Simplified date handling - engine only supports today's slate.
"""

from datetime import datetime, date
import pytz


def get_eastern_now() -> datetime:
    """Get current datetime in Eastern timezone."""
    eastern = pytz.timezone('US/Eastern')
    return datetime.now(eastern)


def get_eastern_date() -> date:
    """Get current date in Eastern timezone."""
    return get_eastern_now().date()


def get_today_str() -> str:
    """Get today's date as YYYY-MM-DD string."""
    return get_eastern_date().strftime("%Y-%m-%d")


def format_timestamp() -> str:
    """Get current timestamp as YYYY-MM-DD HH:MM:SS string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
