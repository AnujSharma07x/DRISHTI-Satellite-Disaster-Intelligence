from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.geometry import GeoJSONGeometry


class SimulationRequest(BaseModel):
    region_id: str
    flood_level: float = Field(ge=0, description="Flood level in metres — see docs/DATA_FORMATS.md §3")


class SimulationResponse(BaseModel):
    scenario_id: str
    region_id: str
    flood_level: float
    status: str  # pending | running | completed | failed — docs/DATA_FORMATS.md §4
    flooded_area: float | None = None  # km²
    population_affected: int | None = None
    buildings_affected: int | None = None  # null unless optional `buildings` table adopted
    roads_affected_count: int | None = None  # always a count, never a length
    hospitals_affected: int | None = None
    result_geometry: GeoJSONGeometry | None = None
    created_at: datetime
