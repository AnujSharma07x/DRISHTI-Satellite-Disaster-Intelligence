from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.region import RegionsResponse
from backend.app.services import supabase_service

router = APIRouter()


@router.get("/regions", response_model=RegionsResponse)
def list_regions(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    """GET /api/regions — per docs/API_CONTRACT.md."""
    try:
        regions = supabase_service.list_regions(limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch regions: {exc}")
    return {"regions": regions}
