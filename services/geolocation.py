"""Offline lookup: coordinates are never persisted or sent to a geocoder."""

from functools import lru_cache
import json
import math
from pathlib import Path


@lru_cache(maxsize=1)
def district_boundaries():
    return json.loads((Path(__file__).parent.parent / "domain" / "novosibirsk-districts.geojson").read_text(encoding="utf-8"))["features"]


def in_ring(longitude, latitude, ring):
    inside = False
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        # Include points exactly on a boundary; the user confirms the result.
        cross = (longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)
        if abs(cross) < 1e-12 and min(x1, x2) <= longitude <= max(x1, x2) and min(y1, y2) <= latitude <= max(y1, y2):
            return True
        if (y1 > latitude) != (y2 > latitude):
            if longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def detect_district(latitude: float, longitude: float) -> str | None:
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    # Reject remote points without scanning the polygons.
    if not (54.6 <= latitude <= 55.4 and 82.5 <= longitude <= 83.5):
        return None
    for feature in district_boundaries():
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for polygon in polygons:
            if in_ring(longitude, latitude, polygon[0]) and not any(in_ring(longitude, latitude, hole) for hole in polygon[1:]):
                return feature["properties"]["name"]
    return None
