"""
impact.py — Spatial impact calculation and simulation_scenarios persistence.

Owner: Engineer 3.

Per ENGG_3.txt and DATA_FORMATS.md §7, impact numbers are computed with
PostGIS spatial queries (ST_Intersects), not application-level geometry math,
and this module does NOT duplicate the database — it reads the shared
reference layers (`roads`, `critical_infrastructure`, `population_zones`,
optionally `buildings`) that Engineer 1 owns the schema for, and writes only
to `simulation_scenarios`, which Engineer 3 owns.

Connection handling: this module accepts an already-open DB-API connection
(e.g. psycopg2) rather than constructing one itself, so it stays independent
of however Engineer 1 wires up the Supabase Postgres connection string in
the FastAPI backend. Never hardcode credentials here (see COMMON.txt #11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


class DBConnection(Protocol):
    """Minimal DB-API-style connection protocol (e.g. psycopg2.connection)."""

    def cursor(self): ...
    def commit(self): ...


@dataclass
class ImpactResult:
    population_affected: int
    roads_affected_count: int
    hospitals_affected: int
    buildings_affected: Optional[int]  # None if `buildings` table isn't populated (optional table)
    infrastructure_types_affected: dict  # e.g. {"hospital": 3, "school": 5, ...}


def _fetch_scalar(cursor, query: str, params: tuple) -> int:
    cursor.execute(query, params)
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def calculate_population_affected(
    conn: DBConnection, region_id: str, flood_wkt: str
) -> int:
    """
    Sum population of `population_zones` polygons that intersect the flood
    extent, within the given region.

    NOTE (documented assumption, per COMMON.txt #16): this sums the *entire*
    population of any zone that intersects the flood polygon at all, rather
    than area-weighting partial overlap. This is a deliberate MVP
    simplification — an area-weighted version (ST_Intersection + area ratio)
    is a straightforward upgrade if time and demo needs allow, but is not
    required for the 10-day prototype.
    """
    query = """
        SELECT COALESCE(SUM(population), 0)
        FROM population_zones
        WHERE region_id = %s
          AND ST_Intersects(geometry, ST_GeomFromText(%s, 4326))
    """
    with conn.cursor() as cur:
        return _fetch_scalar(cur, query, (region_id, flood_wkt))


def calculate_roads_affected_count(
    conn: DBConnection, region_id: str, flood_wkt: str
) -> int:
    """
    Count of `roads` LineString features intersected by the flood extent.

    Always an integer count of road segments/features — never a length/
    distance value (locked in DATA_FORMATS.md §3 / API_CONTRACT.md).
    """
    query = """
        SELECT COUNT(*)
        FROM roads
        WHERE region_id = %s
          AND ST_Intersects(geometry, ST_GeomFromText(%s, 4326))
    """
    with conn.cursor() as cur:
        return _fetch_scalar(cur, query, (region_id, flood_wkt))


def calculate_hospitals_affected(
    conn: DBConnection, region_id: str, flood_wkt: str
) -> int:
    """Count of `critical_infrastructure` rows of type='hospital' intersected."""
    query = """
        SELECT COUNT(*)
        FROM critical_infrastructure
        WHERE region_id = %s
          AND type = 'hospital'
          AND ST_Intersects(geometry, ST_GeomFromText(%s, 4326))
    """
    with conn.cursor() as cur:
        return _fetch_scalar(cur, query, (region_id, flood_wkt))


def calculate_infrastructure_breakdown(
    conn: DBConnection, region_id: str, flood_wkt: str
) -> dict:
    """
    Count of affected `critical_infrastructure` rows grouped by type
    (hospital, school, police_station, fire_station, relief_centre, bridge).
    Useful for the response-engine handoff (Engineer 4) and dashboard detail,
    beyond the single `hospitals_affected` column required by the schema.
    """
    query = """
        SELECT type, COUNT(*)
        FROM critical_infrastructure
        WHERE region_id = %s
          AND ST_Intersects(geometry, ST_GeomFromText(%s, 4326))
        GROUP BY type
    """
    with conn.cursor() as cur:
        cur.execute(query, (region_id, flood_wkt))
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def buildings_table_exists(conn: DBConnection) -> bool:
    """
    Check once whether the optional `buildings` table exists in this schema.

    Constrained to `current_schema()` (rather than an unqualified table-name
    lookup across all schemas) so this can't return a false positive from an
    unrelated `buildings` table living in a different schema (e.g. an
    extension or a stale table left over from another project sharing the
    same Postgres instance). `current_schema()` is used rather than
    hardcoding `'public'` so this keeps working if the project's Supabase
    connection is ever configured with a non-default search_path — no doc
    in this project specifies a schema other than the connection's default,
    so hardcoding one would be inventing a constraint that isn't there.

    Split out from calculate_buildings_affected() so a caller looping over
    several scenarios (see example_scenario.py) can check this a single time
    and pass the result in, instead of re-querying information_schema on
    every scenario.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'buildings'
                  AND table_schema = current_schema()
            )
            """
        )
        return bool(cur.fetchone()[0])


def calculate_buildings_affected(
    conn: DBConnection,
    region_id: str,
    flood_wkt: str,
    table_exists: Optional[bool] = None,
) -> Optional[int]:
    """
    Count of `buildings` polygons intersected — `buildings` is an OPTIONAL
    table (DATABASE_SCHEMA.md). Returns None (-> stored as NULL) if the
    table doesn't exist or isn't populated for this region, so the caller
    never has to guess whether 0 means "no buildings affected" vs.
    "buildings layer not adopted yet".

    Parameters
    ----------
    table_exists : bool, optional
        Pass a pre-computed result of buildings_table_exists() to skip the
        information_schema round-trip when calling this repeatedly (e.g.
        once per scenario in a loop). If omitted, checked fresh each call.
    """
    with conn.cursor() as cur:
        if table_exists is None:
            table_exists = buildings_table_exists(conn)
        if not table_exists:
            return None

        cur.execute(
            "SELECT COUNT(*) FROM buildings WHERE region_id = %s LIMIT 1",
            (region_id,),
        )
        has_rows = cur.fetchone()[0] > 0
        if not has_rows:
            return None

        query = """
            SELECT COUNT(*)
            FROM buildings
            WHERE region_id = %s
              AND ST_Intersects(geometry, ST_GeomFromText(%s, 4326))
        """
        return _fetch_scalar(cur, query, (region_id, flood_wkt))


def calculate_all_impacts(
    conn: DBConnection,
    region_id: str,
    flood_wkt: str,
    buildings_exists: Optional[bool] = None,
) -> ImpactResult:
    """
    Run all impact queries for a single simulated flood extent.

    Pass `buildings_exists` (from buildings_table_exists()) when calling
    this in a loop across multiple scenarios for the same region, to avoid
    re-checking information_schema every time.
    """
    return ImpactResult(
        population_affected=calculate_population_affected(conn, region_id, flood_wkt),
        roads_affected_count=calculate_roads_affected_count(conn, region_id, flood_wkt),
        hospitals_affected=calculate_hospitals_affected(conn, region_id, flood_wkt),
        buildings_affected=calculate_buildings_affected(
            conn, region_id, flood_wkt, table_exists=buildings_exists
        ),
        infrastructure_types_affected=calculate_infrastructure_breakdown(
            conn, region_id, flood_wkt
        ),
    )


def save_simulation_scenario(
    conn: DBConnection,
    region_id: str,
    scenario_name: str,
    flood_level: float,
    flooded_area_km2: float,
    impact: ImpactResult,
    result_geometry_wkt: Optional[str],
    flood_prediction_id: Optional[str] = None,
) -> str:
    """
    Insert one completed scenario row into `simulation_scenarios` and return
    its new id. `status` is set to 'completed' since, for the MVP, simulation
    runs synchronously (see API_CONTRACT.md `POST /api/simulation` notes).

    On any database error, the transaction is rolled back before the
    exception is re-raised, so the connection is left in a clean state for
    the caller to retry or continue with the next scenario — we don't
    swallow the error, just don't leave a half-open transaction behind.
    """
    query = """
        INSERT INTO simulation_scenarios (
            region_id, flood_prediction_id, scenario_name, flood_level,
            flooded_area, population_affected, buildings_affected,
            roads_affected_count, hospitals_affected, result_geometry, status
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            CASE WHEN %s IS NULL THEN NULL ELSE ST_GeomFromText(%s, 4326) END,
            'completed'
        )
        RETURNING id
    """
    params = (
        region_id,
        flood_prediction_id,
        scenario_name,
        flood_level,
        flooded_area_km2,
        impact.population_affected,
        impact.buildings_affected,
        impact.roads_affected_count,
        impact.hospitals_affected,
        result_geometry_wkt,
        result_geometry_wkt,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            new_id = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return str(new_id)
