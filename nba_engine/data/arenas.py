"""
Approximate NBA arena coordinates (lat, lon) for travel-distance estimation.

Coordinates are approximate city-centre positions.  Precision beyond
~10 km is irrelevant for the schedule-stress model.
"""

from math import radians, sin, cos, sqrt, atan2

# team abbreviation -> (latitude, longitude)
ARENA_COORDS = {
    "ATL": (33.757, -84.396),
    "BOS": (42.366, -71.062),
    "BKN": (40.683, -73.975),
    "CHA": (35.225, -80.839),
    "CHI": (41.881, -87.674),
    "CLE": (41.496, -81.688),
    "DAL": (32.790, -96.810),
    "DEN": (39.749, -105.008),
    "DET": (42.341, -83.055),
    "GSW": (37.768, -122.388),
    "HOU": (29.751, -95.362),
    "IND": (39.764, -86.156),
    "LAC": (33.944, -118.341),
    "LAL": (34.043, -118.267),
    "MEM": (35.138, -90.051),
    "MIA": (25.781, -80.187),
    "MIL": (43.045, -87.917),
    "MIN": (44.980, -93.276),
    "NOP": (29.949, -90.082),
    "NYK": (40.751, -73.994),
    "OKC": (35.463, -97.515),
    "ORL": (28.539, -81.384),
    "PHI": (39.901, -75.172),
    "PHX": (33.446, -112.071),
    "POR": (45.532, -122.667),
    "SAC": (38.580, -121.500),
    "SAS": (29.427, -98.438),
    "TOR": (43.643, -79.379),
    "UTA": (40.768, -111.901),
    "WAS": (38.898, -77.021),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def travel_distance_km(from_team: str, to_team: str) -> float:
    """Return approximate travel distance in km between two team cities."""
    c1 = ARENA_COORDS.get(from_team)
    c2 = ARENA_COORDS.get(to_team)
    if c1 is None or c2 is None:
        return 0.0
    return haversine_km(c1[0], c1[1], c2[0], c2[1])
