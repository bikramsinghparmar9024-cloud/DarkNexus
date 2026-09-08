"""
Punjab Border Geospatial Resolver & Distance Matrix.
Maps intercepted geographic locations to GPS coordinates and evaluates
proximity to the 553-km Indo-Pakistan International Border in Punjab.
Flags locations within 15 km as "CRITICAL_BORDER_CORRIDOR".
"""

from typing import Dict, Any, List, Optional
import math
import logging

logger = logging.getLogger("geo_resolver")

# Coordinates of Key Punjab Districts & Border Outposts
# [Name -> (Latitude, Longitude, DistanceToBorderKm, IsBorderDistrict)]
PUNJAB_GEO_DATABASE = {
    # ── High-Risk Border Zone (< 15 km) ─────────────────────────
    "Attari": (31.6026, 74.6033, 2.5, True),
    "Wagah": (31.6050, 74.5714, 0.5, True),
    "Khemkaran": (31.1449, 74.5684, 3.2, True),
    "Dera Baba Nanak": (31.9868, 75.0319, 4.0, True),
    "Fazilka": (30.4036, 74.0270, 7.8, True),
    "Firozpur": (30.9237, 74.6122, 11.2, True),
    "Majitha": (31.7611, 74.9547, 13.5, True),
    "Tarn Taran": (31.4520, 74.9270, 18.0, True),
    "Gurdaspur": (32.0419, 75.4053, 19.5, True),
    "Pathankot": (32.2686, 75.5529, 21.0, True),

    # ── Major Distribution & Inland Hubs ────────────────────────
    "Amritsar": (31.6340, 74.8723, 26.0, True),
    "Jalandhar": (31.3260, 75.5762, 75.0, False),
    "Ludhiana": (30.9010, 75.8573, 105.0, False),
    "Bathinda": (30.2110, 74.9455, 78.0, False),
    "Moga": (30.8165, 75.1715, 68.0, False),
    "Mohali": (30.7046, 76.7179, 195.0, False),
    "Patiala": (30.3398, 76.3869, 180.0, False),
    "Hoshiarpur": (31.5273, 75.9149, 110.0, False),
    "Kapurthala": (31.3800, 75.3800, 65.0, False),
    "Muktsar": (30.4744, 74.5166, 42.0, False),
    "Barnala": (30.3819, 75.5471, 115.0, False),
    "Rupnagar": (30.9664, 76.5331, 185.0, False),
    "Sangrur": (30.2458, 75.8421, 140.0, False)
}

# 15km threshold for international border alert
BORDER_PROXIMITY_THRESHOLD_KM = 15.0


def resolve_location(location_name: str) -> Optional[Dict[str, Any]]:
    """Lookup exact coordinates and border danger status for a named place."""
    clean_name = location_name.strip()
    for loc_key, (lat, lon, dist_km, is_border) in PUNJAB_GEO_DATABASE.items():
        if loc_key.lower() == clean_name.lower():
            in_border_zone = dist_km <= BORDER_PROXIMITY_THRESHOLD_KM
            return {
                "location": loc_key,
                "lat": lat,
                "lon": lon,
                "distance_to_border_km": dist_km,
                "is_border_district": is_border,
                "in_critical_border_corridor": in_border_zone,
                # A "threat_multiplier" of 1.5 was returned here and displayed
                # in the interface, but nothing multiplied anything by it. The
                # real border rule lives in ai/enrichment.py and moves a record
                # up one band, and only when narcotics evidence and operational
                # speech are both present. Publishing a coefficient that no
                # code applies invents a scoring mechanism for the reader.
            }
    return None


def extract_geo_markers_from_text(text: str) -> List[Dict[str, Any]]:
    """Scan text for any Punjab location mentions and return geo-coordinates."""
    found_markers = []
    text_lower = text.lower()
    for loc_key, (lat, lon, dist_km, is_border) in PUNJAB_GEO_DATABASE.items():
        if loc_key.lower() in text_lower:
            in_border_zone = dist_km <= BORDER_PROXIMITY_THRESHOLD_KM
            found_markers.append({
                "location": loc_key,
                "lat": lat,
                "lon": lon,
                "distance_to_border_km": dist_km,
                "in_critical_border_corridor": in_border_zone
            })
    return found_markers


def get_all_punjab_hotspots() -> List[Dict[str, Any]]:
    """Return complete database formatted for Leaflet.js mapping."""
    hotspots = []
    for loc_key, (lat, lon, dist_km, is_border) in PUNJAB_GEO_DATABASE.items():
        hotspots.append({
            "name": loc_key,
            "lat": lat,
            "lon": lon,
            "dist_to_border": dist_km,
            "critical_border_zone": dist_km <= BORDER_PROXIMITY_THRESHOLD_KM
        })
    return hotspots


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two coordinate pairs."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def resolve_coordinates(lat: float, lon: float) -> Dict[str, Any]:
    """
    Resolve a raw GPS fix (e.g. from image EXIF) to the nearest known Punjab
    location and estimate its distance to the international border.

    This is the counterpart to resolve_location(): that one takes a place name
    found in text, this one takes coordinates lifted off a photograph.
    """
    nearest_name = None
    nearest_km = None
    nearest_entry = None

    for loc_key, (klat, klon, dist_km, is_border) in PUNJAB_GEO_DATABASE.items():
        d = haversine_km(lat, lon, klat, klon)
        if nearest_km is None or d < nearest_km:
            nearest_km, nearest_name, nearest_entry = d, loc_key, (klat, klon, dist_km, is_border)

    _, _, ref_border_km, is_border_district = nearest_entry

    # Approximate the fix's own border distance from its nearest known town.
    # Offset by the distance to that town, floored at zero.
    estimated_border_km = max(0.0, round(ref_border_km - nearest_km, 1))         if nearest_km < ref_border_km else round(ref_border_km + nearest_km, 1)

    in_corridor = estimated_border_km <= BORDER_PROXIMITY_THRESHOLD_KM

    return {
        "lat": lat,
        "lon": lon,
        "nearest_known_location": nearest_name,
        "distance_to_nearest_km": round(nearest_km, 2),
        "location": nearest_name,
        "district": nearest_name,
        "distance_to_border_km": estimated_border_km,
        "in_critical_border_corridor": in_corridor,
        "is_border_alert": in_corridor,
        "is_border_district": is_border_district,
        "in_punjab_region": nearest_km <= 150.0,
        "source": "GPS_EXIF",
    }
