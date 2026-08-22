from typing import Any

from pydantic import BaseModel


class GeoJSONGeometry(BaseModel):
    """
    Raw GeoJSON geometry object (not a Feature) — per docs/DATA_FORMATS.md §1.
    Always WGS84 / EPSG:4326. `coordinates` is typed loosely since its nesting
    depth varies by geometry type (Point vs Polygon vs MultiPolygon, etc.).
    """
    type: str
    coordinates: Any
