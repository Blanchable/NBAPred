"""
Date utilities for NBA Prediction Engine.

Provides date parsing, validation, and the 3-month historical limit guard.
"""

from datetime import datetime, date, timedelta
from typing import Optional, Tuple
import pytz


# Maximum months back for historical queries
MAX_MONTHS_BACK = 3

# Default max days per backfill run
DEFAULT_MAX_DAYS_PER_RUN = 30

# Eastern timezone (NBA operates on ET)
EASTERN_TZ = pytz.timezone('US/Eastern')


def get_eastern_now() -> datetime:
    """Get current datetime in Eastern timezone."""
    return datetime.now(EASTERN_TZ)


def get_eastern_date() -> date:
    """Get current date in Eastern timezone."""
    return get_eastern_now().date()


def parse_date(date_str: str) -> date:
    """
    Parse a date string in various formats.
    
    Supported formats:
    - YYYY-MM-DD
    - MM/DD/YYYY
    - MM-DD-YYYY
    
    Args:
        date_str: Date string to parse
        
    Returns:
        date object
        
    Raises:
        ValueError: If date string cannot be parsed
    """
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    raise ValueError(f"Cannot parse date: {date_str}. Use YYYY-MM-DD format.")


def format_date(d: date, fmt: str = "%Y-%m-%d") -> str:
    """Format a date object to string."""
    return d.strftime(fmt)


def get_date_limit() -> date:
    """
    Get the earliest allowed date for historical queries.
    
    Returns:
        Date that is MAX_MONTHS_BACK months ago
    """
    today = get_eastern_date()
    # Approximate 3 months as 90 days
    return today - timedelta(days=MAX_MONTHS_BACK * 30)


def enforce_date_limit(requested_date: date, months_back: int = MAX_MONTHS_BACK) -> None:
    """
    Validate that requested date is within the allowed historical range.
    
    Args:
        requested_date: The date being requested
        months_back: Maximum months back allowed (default 3)
        
    Raises:
        ValueError: If date is too far in the past
    """
    today = get_eastern_date()
    limit = today - timedelta(days=months_back * 30)
    
    if requested_date < limit:
        raise ValueError(
            f"Historical mode limited to last {months_back} months. "
            f"Requested {requested_date}, earliest allowed is {limit}."
        )
    
    if requested_date > today:
        raise ValueError(
            f"Cannot request future date {requested_date}. Today is {today}."
        )


def validate_date_range(
    start_date: date,
    end_date: date,
    max_days: int = DEFAULT_MAX_DAYS_PER_RUN,
) -> Tuple[date, date]:
    """
    Validate and potentially adjust a date range for backfill.
    
    Args:
        start_date: Start of range
        end_date: End of range
        max_days: Maximum days per run
        
    Returns:
        Tuple of (validated_start, validated_end)
        
    Raises:
        ValueError: If range is invalid
    """
    if start_date > end_date:
        raise ValueError(f"Start date {start_date} cannot be after end date {end_date}")
    
    # Enforce 3-month limit on both ends
    enforce_date_limit(start_date)
    enforce_date_limit(end_date)
    
    # Check range size
    days_in_range = (end_date - start_date).days + 1
    
    if days_in_range > max_days:
        # Adjust end_date to respect max_days
        adjusted_end = start_date + timedelta(days=max_days - 1)
        print(f"  Warning: Range of {days_in_range} days exceeds max {max_days}. "
              f"Limiting to {start_date} - {adjusted_end}.")
        return start_date, adjusted_end
    
    return start_date, end_date


def get_date_range(start_date: date, end_date: date) -> list[date]:
    """
    Generate list of dates in a range (inclusive).
    
    Args:
        start_date: Start of range
        end_date: End of range
        
    Returns:
        List of date objects
    """
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def is_today(d: date) -> bool:
    """Check if date is today (Eastern time)."""
    return d == get_eastern_date()


def days_ago(d: date) -> int:
    """Return how many days ago a date was."""
    return (get_eastern_date() - d).days


def get_season_for_date(d: date) -> str:
    """
    Get NBA season string for a date.
    
    NBA seasons span Oct-Jun. Season 2024-25 means Oct 2024 - Jun 2025.
    
    Args:
        d: Date to check
        
    Returns:
        Season string like "2024-25"
    """
    year = d.year
    month = d.month
    
    # If Oct-Dec, season starts this year
    # If Jan-Sep, season started previous year
    if month >= 10:
        start_year = year
    else:
        start_year = year - 1
    
    end_year = start_year + 1
    return f"{start_year}-{str(end_year)[-2:]}"
