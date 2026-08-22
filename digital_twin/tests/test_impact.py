"""
tests/test_impact.py — unit tests for impact.py's query-building and
control-flow logic, against a fake DB-API connection (tests/fakes.py).

None of these tests require rasterio/shapely/pyproj/psycopg2 or a live
Supabase/Postgres connection — impact.py itself has no such dependency
(it only type-hints a DBConnection Protocol), so these run anywhere numpy
does.

What's intentionally NOT tested here: whether the SQL is valid Postgres/
PostGIS syntax, or whether ST_Intersects behaves correctly against real
geometry — that requires a real PostGIS instance and belongs in a separate
integration-test suite (not part of this unit-test pass).
"""

import pytest

from digital_twin import impact
from .fakes import FakeConnection, FakeCursor


# ---------------------------------------------------------------------------
# calculate_population_affected
# ---------------------------------------------------------------------------

def test_calculate_population_affected_returns_scalar_sum():
    cur = FakeCursor(fetchone_results=[(27431,)])
    conn = FakeConnection(cur)

    result = impact.calculate_population_affected(
        conn, region_id="region-123", flood_wkt="MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))"
    )

    assert result == 27431


def test_calculate_population_affected_query_shape_and_params():
    cur = FakeCursor(fetchone_results=[(0,)])
    conn = FakeConnection(cur)

    impact.calculate_population_affected(conn, region_id="region-123", flood_wkt="WKT")

    assert len(cur.executed_queries) == 1
    query, params = cur.executed_queries[0]
    assert "population_zones" in query
    assert "ST_Intersects" in query
    assert "region_id" in query
    assert params == ("region-123", "WKT")


def test_calculate_population_affected_null_sum_becomes_zero():
    """COALESCE(SUM(...), 0) means an empty result set is 0, not an error."""
    cur = FakeCursor(fetchone_results=[(0,)])
    conn = FakeConnection(cur)
    result = impact.calculate_population_affected(conn, "region-x", "WKT")
    assert result == 0


# ---------------------------------------------------------------------------
# calculate_roads_affected_count
# ---------------------------------------------------------------------------

def test_calculate_roads_affected_count_returns_integer_count():
    cur = FakeCursor(fetchone_results=[(31,)])
    conn = FakeConnection(cur)

    result = impact.calculate_roads_affected_count(conn, "region-123", "WKT")

    assert result == 31
    assert isinstance(result, int)


def test_calculate_roads_affected_count_query_filters_by_region_and_intersects():
    cur = FakeCursor(fetchone_results=[(0,)])
    conn = FakeConnection(cur)

    impact.calculate_roads_affected_count(conn, region_id="region-123", flood_wkt="WKT")

    query, params = cur.executed_queries[0]
    assert "roads" in query
    assert "region_id" in query
    assert "ST_Intersects" in query
    assert "COUNT(*)" in query
    assert params == ("region-123", "WKT")


# ---------------------------------------------------------------------------
# calculate_hospitals_affected
# ---------------------------------------------------------------------------

def test_calculate_hospitals_affected_filters_by_type_hospital():
    cur = FakeCursor(fetchone_results=[(3,)])
    conn = FakeConnection(cur)

    result = impact.calculate_hospitals_affected(conn, "region-123", "WKT")

    assert result == 3
    query, _ = cur.executed_queries[0]
    assert "critical_infrastructure" in query
    assert "type = 'hospital'" in query
    assert "ST_Intersects" in query


# ---------------------------------------------------------------------------
# calculate_infrastructure_breakdown
# ---------------------------------------------------------------------------

def test_calculate_infrastructure_breakdown_converts_rows_to_dict():
    cur = FakeCursor(fetchall_results=[[("hospital", 3), ("school", 5), ("bridge", 1)]])
    conn = FakeConnection(cur)

    result = impact.calculate_infrastructure_breakdown(conn, "region-123", "WKT")

    assert result == {"hospital": 3, "school": 5, "bridge": 1}


def test_calculate_infrastructure_breakdown_empty_result_is_empty_dict():
    cur = FakeCursor(fetchall_results=[[]])
    conn = FakeConnection(cur)

    result = impact.calculate_infrastructure_breakdown(conn, "region-123", "WKT")

    assert result == {}


def test_calculate_infrastructure_breakdown_groups_by_type():
    cur = FakeCursor(fetchall_results=[[]])
    conn = FakeConnection(cur)
    impact.calculate_infrastructure_breakdown(conn, "region-123", "WKT")
    query, _ = cur.executed_queries[0]
    assert "GROUP BY type" in query


# ---------------------------------------------------------------------------
# buildings_table_exists
# ---------------------------------------------------------------------------

def test_buildings_table_exists_true():
    cur = FakeCursor(fetchone_results=[(True,)])
    conn = FakeConnection(cur)
    assert impact.buildings_table_exists(conn) is True


def test_buildings_table_exists_false():
    cur = FakeCursor(fetchone_results=[(False,)])
    conn = FakeConnection(cur)
    assert impact.buildings_table_exists(conn) is False


def test_buildings_table_exists_constrains_to_current_schema():
    cur = FakeCursor(fetchone_results=[(False,)])
    conn = FakeConnection(cur)
    impact.buildings_table_exists(conn)
    query, _ = cur.executed_queries[0]
    assert "information_schema.tables" in query
    assert "current_schema()" in query


# ---------------------------------------------------------------------------
# calculate_buildings_affected — the three documented cases
# ---------------------------------------------------------------------------

def test_buildings_affected_table_missing_returns_none():
    """Case: `buildings` table does not exist at all -> None."""
    cur = FakeCursor(fetchone_results=[(False,)])  # EXISTS check
    conn = FakeConnection(cur)

    result = impact.calculate_buildings_affected(conn, "region-123", "WKT")

    assert result is None
    # Only the EXISTS check should have run — no further queries once we
    # know the table doesn't exist.
    assert len(cur.executed_queries) == 1


def test_buildings_affected_table_exists_no_rows_for_region_returns_none():
    """Case: table exists, but has zero rows for this region -> None (not 0)."""
    cur = FakeCursor(fetchone_results=[(0,)])  # "has rows" check: COUNT = 0
    conn = FakeConnection(cur)

    result = impact.calculate_buildings_affected(
        conn, "region-123", "WKT", table_exists=True
    )

    assert result is None
    assert len(cur.executed_queries) == 1
    query, _ = cur.executed_queries[0]
    assert "LIMIT 1" in query


def test_buildings_affected_table_exists_with_rows_returns_count():
    """Case: table exists and has rows for this region -> actual intersect count."""
    cur = FakeCursor(fetchone_results=[(5,), (42,)])  # has-rows check, then real count
    conn = FakeConnection(cur)

    result = impact.calculate_buildings_affected(
        conn, "region-123", "WKT", table_exists=True
    )

    assert result == 42
    assert len(cur.executed_queries) == 2


def test_buildings_affected_skips_exists_check_when_table_exists_passed():
    """Passing table_exists=True/False must skip the information_schema round-trip."""
    cur = FakeCursor(fetchone_results=[(0,)])
    conn = FakeConnection(cur)

    impact.calculate_buildings_affected(conn, "region-123", "WKT", table_exists=False)

    # table_exists=False short-circuits before any query runs at all
    assert len(cur.executed_queries) == 0


# ---------------------------------------------------------------------------
# calculate_all_impacts — integration of the above within one call
# ---------------------------------------------------------------------------

def test_calculate_all_impacts_assembles_impact_result():
    cur = FakeCursor(
        fetchone_results=[
            (100,),   # population_affected
            (7,),     # roads_affected_count
            (2,),     # hospitals_affected
            # buildings_exists=False passed explicitly -> no buildings queries
        ],
        fetchall_results=[[("hospital", 2), ("school", 1)]],
    )
    conn = FakeConnection(cur)

    result = impact.calculate_all_impacts(
        conn, "region-123", "WKT", buildings_exists=False
    )

    assert isinstance(result, impact.ImpactResult)
    assert result.population_affected == 100
    assert result.roads_affected_count == 7
    assert result.hospitals_affected == 2
    assert result.buildings_affected is None
    assert result.infrastructure_types_affected == {"hospital": 2, "school": 1}


# ---------------------------------------------------------------------------
# save_simulation_scenario
# ---------------------------------------------------------------------------

def _sample_impact_result(buildings_affected=None):
    return impact.ImpactResult(
        population_affected=100,
        roads_affected_count=5,
        hospitals_affected=1,
        buildings_affected=buildings_affected,
        infrastructure_types_affected={"hospital": 1},
    )


def test_save_simulation_scenario_inserts_expected_columns():
    cur = FakeCursor(fetchone_results=[("scenario-uuid-123",)])
    conn = FakeConnection(cur)

    scenario_id = impact.save_simulation_scenario(
        conn,
        region_id="region-abc",
        scenario_name="Scenario 3.0m",
        flood_level=3.0,
        flooded_area_km2=12.5,
        impact=_sample_impact_result(),
        result_geometry_wkt="MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))",
    )

    assert scenario_id == "scenario-uuid-123"

    assert len(cur.executed_queries) == 1
    query, params = cur.executed_queries[0]

    # Exact simulation_scenarios columns per DATABASE_SCHEMA.md §7 —
    # verified against the locked schema doc, not guessed.
    for column in (
        "region_id",
        "flood_prediction_id",
        "scenario_name",
        "flood_level",
        "flooded_area",
        "population_affected",
        "buildings_affected",
        "roads_affected_count",
        "hospitals_affected",
        "result_geometry",
        "status",
    ):
        assert column in query, f"expected column '{column}' in INSERT"

    assert params == (
        "region-abc",           # region_id
        None,                   # flood_prediction_id
        "Scenario 3.0m",        # scenario_name
        3.0,                    # flood_level
        12.5,                   # flooded_area
        100,                    # population_affected
        None,                   # buildings_affected
        5,                      # roads_affected_count
        1,                      # hospitals_affected
        "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))",  # result_geometry (x2 for CASE WHEN)
        "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))",
    )


def test_save_simulation_scenario_uses_epsg_4326():
    cur = FakeCursor(fetchone_results=[("id",)])
    conn = FakeConnection(cur)

    impact.save_simulation_scenario(
        conn,
        region_id="region-abc",
        scenario_name="Scenario",
        flood_level=3.0,
        flooded_area_km2=1.0,
        impact=_sample_impact_result(),
        result_geometry_wkt="MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))",
    )

    query, _ = cur.executed_queries[0]
    assert "ST_GeomFromText" in query
    assert "4326" in query


def test_save_simulation_scenario_status_completed():
    cur = FakeCursor(fetchone_results=[("id",)])
    conn = FakeConnection(cur)

    impact.save_simulation_scenario(
        conn,
        region_id="region-abc",
        scenario_name="Scenario",
        flood_level=3.0,
        flooded_area_km2=1.0,
        impact=_sample_impact_result(),
        result_geometry_wkt=None,
    )

    query, _ = cur.executed_queries[0]
    assert "'completed'" in query


def test_save_simulation_scenario_commits_on_success():
    cur = FakeCursor(fetchone_results=[("id",)])
    conn = FakeConnection(cur)

    impact.save_simulation_scenario(
        conn,
        region_id="region-abc",
        scenario_name="Scenario",
        flood_level=3.0,
        flooded_area_km2=1.0,
        impact=_sample_impact_result(),
        result_geometry_wkt=None,
    )

    assert conn.committed is True
    assert conn.rolled_back is False


def test_save_simulation_scenario_rolls_back_on_insert_failure():
    cur = FakeCursor(raise_on_execute=RuntimeError("simulated DB failure"))
    conn = FakeConnection(cur)

    with pytest.raises(RuntimeError):
        impact.save_simulation_scenario(
            conn,
            region_id="region-abc",
            scenario_name="Scenario",
            flood_level=3.0,
            flooded_area_km2=1.0,
            impact=_sample_impact_result(),
            result_geometry_wkt=None,
        )

    assert conn.rolled_back is True
    assert conn.committed is False


def test_save_simulation_scenario_null_geometry_when_no_inundation():
    """A zero-inundation scenario (result_geometry_wkt=None) must persist NULL
    geometry, not an error and not an empty-string geometry."""
    cur = FakeCursor(fetchone_results=[("id",)])
    conn = FakeConnection(cur)

    impact.save_simulation_scenario(
        conn,
        region_id="region-abc",
        scenario_name="Scenario 0.5m",
        flood_level=0.5,
        flooded_area_km2=0.0,
        impact=_sample_impact_result(),
        result_geometry_wkt=None,
    )

    _, params = cur.executed_queries[0]
    assert params[-1] is None
    assert params[-2] is None
