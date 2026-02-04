"""
Storage utilities for NBA Prediction Engine.

Simplified storage - main tracking is now done via Excel (tracking/excel_tracker.py).
This module provides basic file utilities.
"""

from pathlib import Path


# Base paths
BASE_DIR = Path(__file__).parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"

# Ensure directories exist
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
