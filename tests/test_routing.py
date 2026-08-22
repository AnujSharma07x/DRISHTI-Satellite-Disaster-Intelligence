"""
DRISHTI — Engineer 4
Lightweight tests for the routing module.

These tests use hand-built networkx MultiDiGraphs and therefore do NOT
require osmnx or shapely to be installed — they exercise the pure-graph
logic (apply_flood_penalty, select_best_facility) directly, which is
exactly the algorithmic part that needed fixing (Fix #4, #5, #6). The
osmnx-dependent lat/lon-to-node snapping (find_accessible_route,
build_road_graph) is integration-tested separately once a live network
connection / cached .graphml is available — see routing/README.md.

Run with:

    python3 tests/test_routing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx

from routing.graph import apply_flood_penalty, ensure_graph_crs_4326, FLOODED_ATTR
import routing.emergency_route as er
from routing.emergency_route import Facility, select_best_facility, build_response_plan


class _FakeOx:
    """Minimal stand-in for osmnx.nearest_nodes, used only so
    build_response_plan()/find_accessible_route() can be exercised in
    this offline test suite without osmnx installed. Snaps to the
    nearest node by simple squared-distance on (x, y) — sufficient for
    the small hand-built graphs used here."""

    @staticmethod
    def nearest_nodes(graph, X, Y):
        best, best_d = None, None
        for n, data in graph.nodes(data=True):
            d = (data["x"] - X) ** 2 + (data["y"] - Y) ** 2
            if best_d is None or d < best_d:
                best, best_d = n, d
        return best


def _fake_shape(geojson_geometry):
    """Minimal stand-in for shapely.geometry.shape, supporting only what
    zone_centroid() needs: a `.centroid` with `.x`/`.y` on a Polygon's
    exterior ring, computed as a simple coordinate average (fine for the
    small test squares used here — not a real area-weighted centroid)."""

    class _Point:
        def __init__(self, x, y):
            self.x, self.y = x, y

    class _Geom:
        def __init__(self, ring):
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            self.centroid = _Point(sum(xs) / len(xs), sum(ys) / len(ys))

    return _Geom(geojson_geometry["coordinates"][0])


def _simple_facility(fid, name, lat, lon):
    return Facility(fid, name, "Hospital", latitude=lat, longitude=lon)


def test_dry_route_exists():
    g = nx.MultiDiGraph()
    g.add_node(0, x=0.0, y=0.0)
    g.add_node(1, x=0.01, y=0.0)
    g.add_edge(0, 1, key=0, length=1000.0, routing_weight=1000.0, flooded=False)

    facility = _simple_facility("f1", "Dry Hospital", 0.0, 0.01)
    result = select_best_facility(g, origin_node=0, facility_nodes=[(facility, 1)])

    assert result is not None
    assert result["estimated_distance"] == 1.0
    assert not result.get("used_flooded_road", False)


def test_flooded_route_exists_but_dry_alternative_exists():
    g = nx.MultiDiGraph()
    g.add_node(0, x=0.0, y=0.0)
    g.add_node(1, x=0.01, y=0.0)   # facility
    g.add_node(2, x=0.005, y=0.005)  # detour node

    # Direct (flooded, heavily penalized) 1km path
    g.add_edge(0, 1, key=0, length=1000.0, routing_weight=1000.0 * 1000, flooded=True)
    # Dry detour path, 3km total
    g.add_edge(0, 2, key=0, length=1500.0, routing_weight=1500.0, flooded=False)
    g.add_edge(2, 1, key=0, length=1500.0, routing_weight=1500.0, flooded=False)

    facility = _simple_facility("f1", "Hospital", 0.0, 0.01)
    result = select_best_facility(g, origin_node=0, facility_nodes=[(facility, 1)])

    assert result is not None
    assert result["estimated_distance"] == 3.0, "must route around the flooded edge"
    assert not result.get("used_flooded_road", False)


def test_no_accessible_route_returns_none():
    g = nx.MultiDiGraph()
    g.add_node(0, x=0.0, y=0.0)
    g.add_node(1, x=1.0, y=1.0)  # disconnected — no edge at all

    facility = _simple_facility("f1", "Isolated Hospital", 1.0, 1.0)
    result = select_best_facility(g, origin_node=0, facility_nodes=[(facility, 1)])

    assert result is None


def test_flooded_only_reachable_facility_used_as_last_resort():
    """When soft-avoid is on (avoid_flooded_hard=False) and there is
    truly no dry path to ANY candidate, the module should still return
    the best (minimum-distance) flooded route rather than nothing, but
    must flag it via used_flooded_road so the caller can warn."""
    g = nx.MultiDiGraph()
    g.add_node(0, x=0.0, y=0.0)
    g.add_node(1, x=0.01, y=0.0)
    # Only route available is flooded.
    g.add_edge(0, 1, key=0, length=1000.0, routing_weight=1000.0 * 1000, flooded=True)

    facility = _simple_facility("f1", "Only Hospital", 0.0, 0.01)
    result = select_best_facility(g, origin_node=0, facility_nodes=[(facility, 1)])

    assert result is not None
    assert result.get("used_flooded_road") is True


def test_facility_selection_uses_actual_road_distance_not_straight_line():
    """Regression test for Fix #4.

    Facility A: straight-line CLOSE, but the only road route is a long
    12km detour.
    Facility B: straight-line FARTHER, but the road route is a direct
    4km path.

    The system MUST select Facility B (minimum actual road distance).
    """
    g = nx.MultiDiGraph()
    g.add_node(0, x=0.0, y=0.0)     # origin
    g.add_node(1, x=0.01, y=0.0)    # facility A location (close by air)
    g.add_node(2, x=0.02, y=0.0)    # waypoint toward B
    g.add_node(3, x=0.05, y=0.0)    # facility B location (far by air)

    g.add_edge(0, 1, key=0, length=12_000.0, routing_weight=12_000.0, flooded=False)
    g.add_edge(0, 2, key=0, length=2_000.0, routing_weight=2_000.0, flooded=False)
    g.add_edge(2, 3, key=0, length=2_000.0, routing_weight=2_000.0, flooded=False)

    facility_a = _simple_facility("fa", "Facility A", 0.0, 0.01)
    facility_b = _simple_facility("fb", "Facility B", 0.0, 0.05)

    result = select_best_facility(
        g, origin_node=0, facility_nodes=[(facility_a, 1), (facility_b, 3)]
    )

    assert result["facility"].name == "Facility B", (
        f"Fix #4 regression: expected Facility B (shorter road route), "
        f"got {result['facility'].name}"
    )
    assert result["estimated_distance"] == 4.0


def test_apply_flood_penalty_marks_and_weights_edges():
    g = nx.MultiDiGraph()
    g.add_edge(1, 2, key=0, length=100.0)
    g.add_edge(2, 3, key=0, length=100.0)

    g = apply_flood_penalty(g, {(1, 2, 0)})

    assert g.edges[1, 2, 0][FLOODED_ATTR] is True
    assert g.edges[1, 2, 0]["routing_weight"] == 100.0 * 1000
    assert g.edges[2, 3, 0][FLOODED_ATTR] is False
    assert g.edges[2, 3, 0]["routing_weight"] == 100.0


def test_apply_flood_penalty_hard_remove():
    g = nx.MultiDiGraph()
    g.add_edge(1, 2, key=0, length=100.0)
    g.add_edge(2, 3, key=0, length=100.0)

    g = apply_flood_penalty(g, {(1, 2, 0)}, hard_remove=True)

    assert not g.has_edge(1, 2)
    assert g.has_edge(2, 3)


def test_crs_passthrough_when_no_metadata():
    """Fix #6: a graph with no CRS metadata is assumed EPSG:4326
    (documented assumption) and passed through unchanged rather than
    silently mis-handled."""
    g = nx.MultiDiGraph()
    out = ensure_graph_crs_4326(g)
    assert out is g


def test_crs_passthrough_when_already_4326():
    g = nx.MultiDiGraph()
    g.graph["crs"] = "epsg:4326"
    out = ensure_graph_crs_4326(g)
    assert out is g


def test_crs_mismatch_without_osmnx_raises_instead_of_silently_wrong():
    """If the graph declares a non-4326 CRS and osmnx (needed to
    reproject) isn't available, we must raise rather than silently
    comparing mismatched coordinate systems."""
    import routing.graph as graph_module

    if graph_module.ox is not None:
        # osmnx is installed in this environment — reprojection would
        # actually be attempted instead of raising. Skip this specific
        # no-osmnx-available assertion in that case.
        print("  (osmnx installed — skipping no-osmnx CRS-mismatch check)")
        return

    g = nx.MultiDiGraph()
    g.graph["crs"] = "epsg:32643"  # some UTM zone, not 4326
    try:
        ensure_graph_crs_4326(g)
        raised = False
    except ImportError:
        raised = True
    assert raised, "expected ImportError when osmnx is unavailable to reproject a non-4326 graph"


def test_build_response_plan_output_contract_explicit_origin():
    """Regression test for Fix #5 (standardized output contract) with
    an explicit origin_lat/origin_lon (Fix #4's alternate origin path)."""
    original_ox = er.ox
    er.ox = _FakeOx()
    try:
        g = nx.MultiDiGraph()
        g.add_node(0, x=0.0, y=0.0)
        g.add_node(1, x=0.01, y=0.0)
        g.add_edge(0, 1, key=0, length=1000.0, routing_weight=1000.0, flooded=False)

        facility = Facility("fac_1", "District Hospital", "Hospital", 0.0, 0.01)
        priority_zone = {
            "zone_id": "zone_a",
            "scenario_id": "scn_001",
            "risk_score": 87.5,
            "risk_level": "CRITICAL",
        }

        plan = build_response_plan(g, priority_zone, [facility], origin_lat=0.0, origin_lon=0.0)

        expected_keys = {
            "scenario_id", "priority_zone_id", "risk_score", "risk_level",
            "recommended_facility_id", "recommended_facility_name",
            "route_geometry", "estimated_distance_km", "used_flooded_road",
        }
        assert expected_keys.issubset(plan.keys()), f"missing keys: {expected_keys - plan.keys()}"
        assert "estimated_distance" not in plan, "must use estimated_distance_km, not the old ambiguous name"
        assert "priority_zone" not in plan, "must use priority_zone_id, not the old display-name field"
        assert "recommended_facility" not in plan, "must split into recommended_facility_id/_name"

        assert plan["scenario_id"] == "scn_001"
        assert plan["priority_zone_id"] == "zone_a"
        assert plan["risk_score"] == 87.5
        assert plan["risk_level"] == "CRITICAL"
        assert plan["recommended_facility_id"] == "fac_1"
        assert plan["recommended_facility_name"] == "District Hospital"
        assert plan["estimated_distance_km"] == 1.0
        assert plan["used_flooded_road"] is False
        assert plan["route_geometry"]["type"] == "LineString"
    finally:
        er.ox = original_ox


def test_build_response_plan_centroid_derived_origin():
    """Regression test for Fix #4 (routing origin): priority-zone
    geometry -> centroid -> nearest graph node, when no explicit
    origin_lat/origin_lon is supplied."""
    original_ox, original_shape = er.ox, er.shape
    er.ox = _FakeOx()
    er.shape = _fake_shape
    try:
        g = nx.MultiDiGraph()
        g.add_node(0, x=0.0, y=0.0)    # nearest to centroid of the square below
        g.add_node(1, x=0.01, y=0.0)   # facility
        g.add_edge(0, 1, key=0, length=1000.0, routing_weight=1000.0, flooded=False)

        facility = Facility("fac_1", "District Hospital", "Hospital", 0.0, 0.01)
        # Square centered at (0,0) -> centroid (lat=0, lon=0)
        zone_geometry = {
            "type": "Polygon",
            "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]],
        }
        priority_zone = {
            "zone_id": "zone_a",
            "scenario_id": "scn_001",
            "risk_score": 87.5,
            "risk_level": "CRITICAL",
            "geometry": zone_geometry,  # Fix #3 pass-through field from risk/impact.py
        }

        plan = build_response_plan(g, priority_zone, [facility])

        assert plan["recommended_facility_id"] == "fac_1"
        assert plan["estimated_distance_km"] == 1.0
    finally:
        er.ox, er.shape = original_ox, original_shape


def test_build_response_plan_missing_origin_raises():
    """No origin_lat/origin_lon AND no geometry anywhere -> fail loudly,
    never silently route from an arbitrary point."""
    g = nx.MultiDiGraph()
    facility = Facility("fac_1", "District Hospital", "Hospital", 0.0, 0.01)
    priority_zone = {"zone_id": "zone_a"}  # no "geometry" key

    raised = False
    try:
        build_response_plan(g, priority_zone, [facility])
    except ValueError:
        raised = True
    assert raised, "expected ValueError when no origin source is available"


def test_build_response_plan_no_facility_reachable_uses_new_contract():
    original_ox = er.ox
    er.ox = _FakeOx()
    try:
        g = nx.MultiDiGraph()
        g.add_node(0, x=0.0, y=0.0)
        g.add_node(1, x=1.0, y=1.0)  # disconnected — unreachable

        facility = Facility("fac_1", "Isolated Hospital", "Hospital", 1.0, 1.0)
        priority_zone = {
            "zone_id": "zone_a",
            "scenario_id": "scn_001",
            "risk_score": 40.0,
            "risk_level": "HIGH",
        }
        plan = build_response_plan(g, priority_zone, [facility], origin_lat=0.0, origin_lon=0.0)

        assert plan["recommended_facility_id"] is None
        assert plan["recommended_facility_name"] is None
        assert plan["route_geometry"] == {}
        assert plan["estimated_distance_km"] is None
        assert plan["used_flooded_road"] is False
        assert "note" in plan
    finally:
        er.ox = original_ox


TESTS = [
    test_dry_route_exists,
    test_flooded_route_exists_but_dry_alternative_exists,
    test_no_accessible_route_returns_none,
    test_flooded_only_reachable_facility_used_as_last_resort,
    test_facility_selection_uses_actual_road_distance_not_straight_line,
    test_apply_flood_penalty_marks_and_weights_edges,
    test_apply_flood_penalty_hard_remove,
    test_crs_passthrough_when_no_metadata,
    test_crs_passthrough_when_already_4326,
    test_crs_mismatch_without_osmnx_raises_instead_of_silently_wrong,
    test_build_response_plan_output_contract_explicit_origin,
    test_build_response_plan_centroid_derived_origin,
    test_build_response_plan_missing_origin_raises,
    test_build_response_plan_no_facility_reachable_uses_new_contract,
]


def run():
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {test.__name__}: {e}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} tests passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    run()
