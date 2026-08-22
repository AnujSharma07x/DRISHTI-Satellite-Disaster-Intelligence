"""
schema.py
=========
Shapes this module's output to exactly match the `flood_predictions` table
contract owned by Engineer 1 (DATABASE_SCHEMA.md #3) and the
`GET /api/flood/{event_id}` response shape (API_CONTRACT.md).

IMPORTANT (per the Engineer 2 brief): this module does NOT write to
Supabase/PostGIS itself and does NOT define its own schema. It only builds a
plain dict matching the agreed contract, for Engineer 1 to insert (directly,
or via a thin FastAPI endpoint that calls into `ai/`).

flood_predictions columns (DATABASE_SCHEMA.md #3):
    id                          -> left out; DB assigns via gen_random_uuid()
    region_id                   -> caller-supplied
    flood_event_id              -> nullable, left None unless caller supplies one
    satellite_observation_id    -> nullable, caller-supplied if known
    model_version                -> from the model that produced the mask
    confidence                  -> float 0.0-1.0
    flood_area                  -> float, km2
    mask_storage_path           -> Supabase Storage path (flood-masks/...), nullable
    geometry                    -> GeoJSON MultiPolygon, EPSG:4326
    status                      -> 'processing' | 'completed' | 'failed'
    created_at                  -> left out; DB default now()
"""

from __future__ import annotations

from typing import Optional


VALID_STATUSES = {"processing", "completed", "failed"}


def build_flood_prediction_payload(
    region_id: str,
    model_version: str,
    confidence: float,
    flood_area_km2: Optional[float],
    geometry: Optional[dict],
    mask_storage_path: Optional[str] = None,
    flood_event_id: Optional[str] = None,
    satellite_observation_id: Optional[str] = None,
    status: str = "completed",
) -> dict:
    """Build a dict matching the `flood_predictions` row contract.

    Raises ValueError if inputs violate the locked contract (fail fast
    rather than silently handing Engineer 1 a malformed row).
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")

    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be in [0.0, 1.0], got {confidence}")

    if geometry is not None and geometry.get("type") not in ("MultiPolygon", "Polygon"):
        raise ValueError(
            f"geometry must be a MultiPolygon (or Polygon, auto-wrapped upstream), "
            f"got type={geometry.get('type')!r}"
        )

    if status == "completed" and flood_area_km2 is None:
        raise ValueError("status='completed' requires flood_area_km2 to be set.")

    # geometry may legitimately be None with status='completed' when the
    # model detected no flooded pixels at all (flood_area_km2 == 0.0) -
    # that is a valid, successful prediction, not a failure.

    return {
        "region_id": region_id,
        "flood_event_id": flood_event_id,
        "satellite_observation_id": satellite_observation_id,
        "model_version": model_version,
        "confidence": round(float(confidence), 4),
        "flood_area": flood_area_km2,
        "mask_storage_path": mask_storage_path,
        "geometry": geometry,
        "status": status,
    }
