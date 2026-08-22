from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.risk import RiskZonesResponse
from backend.app.services import supabase_service

router = APIRouter()


@router.get("/risk-zones", response_model=RiskZonesResponse)
def get_risk_zones(
    region_id: str | None = Query(None, description="Filter by region UUID"),
    scenario_id: str | None = Query(None, description="Filter by simulation scenario UUID"),
):
    """GET /api/risk-zones — per docs/API_CONTRACT.md. Both filters optional."""
    try:
        zones = supabase_service.list_risk_zones(region_id=region_id, scenario_id=scenario_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch risk zones: {exc}")
    return {"risk_zones": zones}
