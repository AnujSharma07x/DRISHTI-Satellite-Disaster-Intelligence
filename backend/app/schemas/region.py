from datetime import datetime

from pydantic import BaseModel

from backend.app.schemas.geometry import GeoJSONGeometry


class Region(BaseModel):
    id: str
    name: str
    state: str | None = None
    country: str | None = None
    geometry: GeoJSONGeometry
    created_at: datetime


class RegionsResponse(BaseModel):
    regions: list[Region]
