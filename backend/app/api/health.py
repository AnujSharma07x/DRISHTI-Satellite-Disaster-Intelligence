from fastapi import APIRouter, HTTPException

from backend.app.database import SupabaseNotConfiguredError
from backend.app.services import supabase_service

router = APIRouter()


@router.get("/health")
def health_check():
    """
    GET /api/health — per docs/API_CONTRACT.md.
    Verifies both that the API process is up and that Supabase/PostGIS is
    reachable with the schema applied (a lightweight select against `regions`).
    """
    try:
        supabase_service.check_connection()
    except SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Supabase unreachable or schema not applied: {exc}",
        )

    return {"status": "ok"}
