"""
Supabase service layer — thin, reusable data-access functions shared by the
API routes in backend/app/api/. Kept intentionally simple: no repository
pattern, no ORM, no dependency-injection framework (Phase 2 scope explicitly
avoids unnecessary abstraction layers).

Read endpoints query the `*_geojson` views (database/views.sql) so that
geometry columns come back as real GeoJSON, matching docs/API_CONTRACT.md.
Writes (e.g. creating a simulation scenario) go directly against the base
tables defined in database/schema.sql — these are unaffected by the views.
"""
from typing import Any

from backend.app.database import get_supabase_client


class RegionNotFoundError(Exception):
    """Raised when a referenced region_id does not exist."""


class ScenarioNotFoundError(Exception):
    """Raised when a referenced scenario_id does not exist."""


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def check_connection() -> None:
    """
    Raises if Supabase cannot be reached or the schema hasn't been applied
    yet. Used by GET /api/health. Deliberately lightweight — a single
    limit-1 select against `regions`.
    """
    client = get_supabase_client()
    client.table("regions").select("id").limit(1).execute()


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------
def list_regions(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    client = get_supabase_client()
    result = (
        client.table("regions_geojson")
        .select("id, name, state, country, geometry, created_at")
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data or []


def region_exists(region_id: str) -> bool:
    client = get_supabase_client()
    result = client.table("regions").select("id").eq("id", region_id).limit(1).execute()
    return bool(result.data)


# ---------------------------------------------------------------------------
# Simulation scenarios
# ---------------------------------------------------------------------------
def create_simulation_scenario(region_id: str, flood_level: float) -> dict[str, Any]:
    """
    Creates a `simulation_scenarios` row with status='pending' and all impact
    fields null. This is intentionally a stub write — the actual simulation
    math (elevation-threshold inundation, ST_Intersects impact calculation)
    is Engineer 3's module (docs/ARCHITECTURE.md §4). This function does not
    invent fake simulation results; it only creates the pending record that
    Engineer 3's service will later fill in and mark 'completed'.

    Raises RegionNotFoundError if region_id does not exist.
    """
    if not region_exists(region_id):
        raise RegionNotFoundError(f"Region '{region_id}' not found.")

    client = get_supabase_client()
    insert_result = (
        client.table("simulation_scenarios")
        .insert({"region_id": region_id, "flood_level": flood_level, "status": "pending"})
        .execute()
    )
    if not insert_result.data:
        raise RuntimeError("Failed to create simulation_scenarios row.")

    scenario_id = insert_result.data[0]["id"]
    return get_simulation_scenario(scenario_id)


def get_simulation_scenario(scenario_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("simulation_scenarios_geojson")
        .select(
            "id, region_id, flood_prediction_id, scenario_name, flood_level, "
            "flooded_area, population_affected, buildings_affected, "
            "roads_affected_count, hospitals_affected, result_geometry, "
            "status, created_at"
        )
        .eq("id", scenario_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    row["scenario_id"] = row.pop("id")
    return row


# ---------------------------------------------------------------------------
# Risk zones
# ---------------------------------------------------------------------------
def list_risk_zones(
    region_id: str | None = None, scenario_id: str | None = None
) -> list[dict[str, Any]]:
    client = get_supabase_client()
    query = client.table("risk_zones_geojson").select(
        "id, region_id, scenario_id, risk_score, risk_level, "
        "population_exposed, infrastructure_exposed, geometry, created_at"
    )
    if region_id:
        query = query.eq("region_id", region_id)
    if scenario_id:
        query = query.eq("scenario_id", scenario_id)
    result = query.execute()
    return result.data or []
