from fastapi import APIRouter, HTTPException, Path

from backend.app.schemas.simulation import SimulationRequest, SimulationResponse
from backend.app.services import supabase_service

router = APIRouter()


@router.post("/simulation", response_model=SimulationResponse, status_code=201)
def create_simulation(payload: SimulationRequest):
    """
    POST /api/simulation — per docs/API_CONTRACT.md.

    Phase 2 scope: validates the request and creates a `simulation_scenarios`
    row with status='pending' and all impact fields null. The actual
    elevation-threshold simulation math and ST_Intersects impact calculation
    is Engineer 3's module (docs/ARCHITECTURE.md §4) — this endpoint
    deliberately does NOT invent flooded_area/population_affected/etc. values.
    """
    try:
        scenario = supabase_service.create_simulation_scenario(
            region_id=payload.region_id, flood_level=payload.flood_level
        )
    except supabase_service.RegionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create simulation scenario: {exc}")
    return scenario


@router.get("/simulation/{scenario_id}", response_model=SimulationResponse)
def get_simulation(scenario_id: str = Path(..., description="Scenario UUID")):
    """GET /api/simulation/{scenario_id} — per docs/API_CONTRACT.md."""
    try:
        scenario = supabase_service.get_simulation_scenario(scenario_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch simulation scenario: {exc}")

    if not scenario:
        raise HTTPException(status_code=404, detail=f"Simulation scenario '{scenario_id}' not found.")
    return scenario
