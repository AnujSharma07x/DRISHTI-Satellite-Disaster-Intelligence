from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.geometry import GeoJSONGeometry


class RiskZone(BaseModel):
    id: str
    region_id: str
    scenario_id: str | None = None
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_level: str | None = None  # LOW | MODERATE | HIGH | VERY_HIGH | CRITICAL
    population_exposed: int | None = None
    infrastructure_exposed: int | None = None
    geometry: GeoJSONGeometry
    created_at: datetime


class RiskZonesResponse(BaseModel):
    risk_zones: list[RiskZone]
