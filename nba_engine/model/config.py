"""
Configuration constants for recency blending and roster instability.

All tuning knobs for the trade-aware recency and instability system
live here so they are easy to find and adjust.
"""

# ============================================================================
# RECENCY BLENDING
# ============================================================================

# How much weight to give the last-N-game metrics vs full season.
# The actual weight used per-team is dynamically adjusted based on
# roster instability (higher instability -> more recency weight).

RECENCY_BASE_WEIGHT = 0.20          # 20 % last-N, 80 % season (default)
RECENCY_MAX_WEIGHT  = 0.40          # cap at 40 % last-N during instability
RECENCY_MIN_WEIGHT  = 0.10          # floor (never go below this)

RECENT_GAMES_N = 10                 # use last 10 games for recent metrics


# ============================================================================
# ROSTER INSTABILITY THRESHOLDS
# ============================================================================

INSTABILITY_LOOKBACK_DAYS = 14      # how far back to compare rotation sigs

INSTABILITY_LOW_THRESHOLD  = 0.10   # 10 % rotation change -> "LOW"
INSTABILITY_HIGH_THRESHOLD = 0.30   # 30 % rotation change -> "HIGH"


# ============================================================================
# INSTABILITY PENALTIES / MODIFIERS
# ============================================================================

# Confidence compression multipliers (applied to (conf - 50) range)
INSTABILITY_CONFIDENCE_MULT_LOW  = 0.97   # mild compression
INSTABILITY_CONFIDENCE_MULT_HIGH = 0.93   # stronger compression

# Net-rating dominance dampeners (applied to the favored side's net delta)
INSTABILITY_NETRATING_MULT_LOW   = 0.95
INSTABILITY_NETRATING_MULT_HIGH  = 0.90

# Maximum points to subtract from the favored side edge score for
# bucket / confidence purposes only (does NOT change pick direction).
INSTABILITY_SCORE_PENALTY_MAX = 2.5
