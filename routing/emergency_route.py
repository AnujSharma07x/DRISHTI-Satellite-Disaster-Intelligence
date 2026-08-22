"""
DRISHTI — Engineer 4
Emergency Routing Module

Given a priority zone (from risk/impact.py) and a road graph with flooded
edges marked (from routing/graph.py), finds the nearest ACCESSIBLE
emergency facility (hospital, fire station, police station, relief
centre) and computes a flood-aware shortest path using Dijkstra via
NetworkX.

------------------------------------------------------------------------
ROUTING ORIGIN (Fix #4, integration round)
------------------------------------------------------------------------
The MVP routing origin is documented/implemented as:

    Priority Zone
        ↓
    Priority Zone Centroid
        ↓
    Nearest road graph node
        ↓
    Emergency facility

i.e. the computed route represents an emergency response route FROM the
selected high-risk zone TO an accessible emergency facility. The zone
centroid is derived (via `zone_centroid()`) from GeoJSON geometry that
the CALLER already has (Engineer 3's flood-extent output / Engineer 1's
PostGIS `risk_zones.geometry`) — Engineer 4 does not invent, simulate,
or fetch that geometry itself; it only computes a centroid coordinate
from geometry supplied to it. Callers may instead pass an explicit
`origin_lat`/`origin_lon` directly (e.g. if PostGIS's own `ST_Centroid`
was already used upstream) — both paths are supported.
------------------------------------------------------------------------
OUTPUT CONTRACT (Fix #5, integration round)
------------------------------------------------------------------------
{
    "scenario_id": "...",
    "priority_zone_id": "...",
    "risk_score": 87.5,
    "risk_level": "CRITICAL",
    "recommended_facility_id": "...",
    "recommended_facility_name": "...",
    "route_geometry": {
        "type": "LineString",
        "coordinates": []
    },
    "estimated_distance_km": 4.2,
    "used_flooded_road": false
}

`estimated_distance_km` (renamed from the previous ambiguous
`estimated_distance`) and `used_flooded_road` (previously only implied
via an optional `note`) are now always present as explicit, unambiguous
fields.
------------------------------------------------------------------------
FIX (facility selection): previously this module sorted candidate
facilities by straight-line (lat/lon) distance and returned the FIRST
one with any reachable, non-flooded route. That does not guarantee the
shortest actual road route — a facility 1km away as the crow flies but
12km by road could be chosen over one 2km away but only 4km by road.

The fix below still uses straight-line distance ONLY as a cheap
candidate-set pre-filter (to bound how many expensive shortest_path
calls we make on a large graph — see `MAX_CANDIDATES`), but the final
SELECTION is always based on actual computed road distance across all
reachable candidates.
------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import networkx as nx

# osmnx is only needed to snap raw lat/lon coordinates onto the nearest
# graph node (`_nearest_node`). The actual route-selection algorithm
# (`select_best_facility`) is pure networkx and must stay testable
# without osmnx installed.
try:  # pragma: no cover
    import osmnx as ox
except ImportError:  # pragma: no cover
    ox = None

try:  # pragma: no cover
    from shapely.geometry import Point, shape
except ImportError:  # pragma: no cover
    Point = None
    shape = None

try:  # pragma: no cover - support both package and flat-script imports
    from .graph import FLOODED_ATTR
except ImportError:  # pragma: no cover
    from graph import FLOODED_ATTR


@dataclass
class Facility:
    """Mirrors a row from critical_infrastructure (Engineer 1's schema),
    filtered to facility types relevant to emergency response."""

    facility_id: str
    name: str
    facility_type: str  # "Hospital" | "Fire Station" | "Police Station" | "Relief Centre"
    latitude: float
    longitude: float
    importance: Optional[int] = None


ELIGIBLE_FACILITY_TYPES = {"Hospital", "Fire Station", "Police Station", "Relief Centre"}

# Straight-line pre-filter cap: only the N nearest-by-crow-flight
# facilities are considered for expensive actual-road-distance routing.
# This keeps the module fast on regions with many facilities while still
# guaranteeing a correct minimum-road-distance pick among realistic
# candidates. Raise this if a region has unusually sparse/indirect roads
# where the Nth-nearest-by-air facility could plausibly beat the top few
# by road.
MAX_CANDIDATES = 8


def _require_osmnx():
    if ox is None:
        raise ImportError(
            "osmnx is required to resolve lat/lon coordinates to graph "
            "nodes. Install osmnx, or call select_best_facility() "
            "directly with pre-resolved node IDs (e.g. in tests)."
        )


def _nearest_node(graph: nx.MultiDiGraph, lat: float, lon: float) -> int:
    _require_osmnx()
    return ox.nearest_nodes(graph, X=lon, Y=lat)


def _chosen_edge_data(graph: nx.MultiDiGraph, u, v) -> dict:
    """MultiDiGraph may have multiple parallel edges between u and v;
    return the one shortest_path would actually have used (min weight)."""
    edge_data = graph.get_edge_data(u, v)
    return min(
        edge_data.values(), key=lambda d: d.get("routing_weight", d.get("length", 1))
    )


def _route_uses_flooded_edge(graph: nx.MultiDiGraph, route: List[int]) -> bool:
    for u, v in zip(route[:-1], route[1:]):
        if _chosen_edge_data(graph, u, v).get(FLOODED_ATTR):
            return True
    return False


def _route_to_geojson(graph: nx.MultiDiGraph, route: List[int]) -> dict:
    coords = [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in route]  # (lon, lat)
    return {"type": "LineString", "coordinates": coords}


def _route_distance_km(graph: nx.MultiDiGraph, route: List[int]) -> float:
    total_m = 0.0
    for u, v in zip(route[:-1], route[1:]):
        total_m += _chosen_edge_data(graph, u, v).get("length", 0.0)
    return round(total_m / 1000.0, 2)


def _facility_is_flooded(facility: Facility, flood_geometry) -> bool:
    """Optional safety check (Fix #4, step 1): if flood polygon geometry
    is available, exclude facilities whose point location falls inside
    it — an "accessible emergency facility" that is itself underwater is
    not a valid recommendation. Requires shapely; if unavailable or no
    flood_geometry is supplied, this check is skipped (documented
    limitation — see routing/README.md)."""
    if flood_geometry is None or Point is None:
        return False
    point = Point(facility.longitude, facility.latitude)
    return point.intersects(flood_geometry)


def zone_centroid(geometry: dict) -> Tuple[float, float]:
    """Computes the (lat, lon) centroid of a priority zone's GeoJSON-
    compatible geometry, for use as the routing origin (see the module
    docstring's ROUTING ORIGIN section, Fix #4).

    `geometry` must be supplied by the caller — this is a mathematical
    centroid of geometry Engineer 3/PostGIS already produced (flood
    extent / risk_zones.geometry), NOT a geometry invented or fetched by
    Engineer 4. Requires shapely.
    """
    if shape is None:
        raise ImportError(
            "shapely is required to compute a zone centroid from GeoJSON "
            "geometry. Install shapely, or supply origin_lat/origin_lon "
            "directly (e.g. from PostGIS's own ST_Centroid) instead of "
            "zone_geometry."
        )
    geom = shape(geometry)
    centroid = geom.centroid
    return centroid.y, centroid.x  # (lat, lon)


def select_best_facility(
    graph: nx.MultiDiGraph,
    origin_node,
    facility_nodes: List[Tuple[Facility, "object"]],
    weight: str = "routing_weight",
    avoid_flooded_hard: bool = False,
) -> Optional[dict]:
    """Core selection algorithm — pure networkx, no osmnx/shapely
    required. Testable directly with hand-built graphs and node IDs.

    `facility_nodes` is a list of (Facility, dest_node) pairs, already
    resolved to graph node IDs by the caller (find_accessible_route does
    this via osmnx; tests can pass node IDs directly).

    Workflow (per Fix #4):
        1. Compute the actual shortest-path route + distance to EVERY
           candidate facility (already pre-filtered by the caller).
        2. Discard candidates with no path at all (unreachable).
        3. Among candidates whose route does NOT touch a flooded edge,
           select the one with the minimum actual road distance.
        4. If no dry route exists to any candidate, fall back to the
           minimum-distance route that does use a flooded segment (only
           relevant when avoid_flooded_hard=False, i.e. flooded edges
           are soft-penalized rather than removed from the graph
           entirely) — flagged clearly via `used_flooded_road`.
        5. If nothing is reachable at all, return None.
    """
    dry_candidates = []
    flooded_candidates = []

    for facility, dest_node in facility_nodes:
        try:
            route = nx.shortest_path(graph, origin_node, dest_node, weight=weight)
        except nx.NetworkXNoPath:
            continue  # unreachable — discarded per Fix #4 step 2

        distance_km = _route_distance_km(graph, route)
        entry = {
            "facility": facility,
            "route_nodes": route,
            "route_geometry": _route_to_geojson(graph, route),
            "estimated_distance": distance_km,
        }

        if avoid_flooded_hard or not _route_uses_flooded_edge(graph, route):
            dry_candidates.append(entry)
        else:
            entry["used_flooded_road"] = True
            flooded_candidates.append(entry)

    if dry_candidates:
        return min(dry_candidates, key=lambda e: e["estimated_distance"])

    if flooded_candidates:
        # Last resort: every reachable facility requires crossing a
        # flooded segment. Still pick the minimum-distance one rather
        # than returning nothing, but the caller (build_response_plan)
        # surfaces `used_flooded_road` so the dashboard can warn.
        return min(flooded_candidates, key=lambda e: e["estimated_distance"])

    return None


def find_accessible_route(
    graph: nx.MultiDiGraph,
    origin_lat: float,
    origin_lon: float,
    facilities: List[Facility],
    weight: str = "routing_weight",
    avoid_flooded_hard: bool = False,
    flood_geometry=None,
    max_candidates: int = MAX_CANDIDATES,
) -> Optional[dict]:
    """Resolves lat/lon coordinates to graph nodes (requires osmnx) and
    delegates the actual selection to `select_best_facility`.

    Straight-line distance is used ONLY to pre-filter the candidate set
    down to `max_candidates` facilities before the (more expensive)
    actual-road-distance computation — final selection is always by real
    route distance, never by straight-line distance (Fix #4).
    """
    origin_node = _nearest_node(graph, origin_lat, origin_lon)

    eligible = [f for f in facilities if f.facility_type in ELIGIBLE_FACILITY_TYPES]

    if flood_geometry is not None:
        eligible = [f for f in eligible if not _facility_is_flooded(f, flood_geometry)]

    eligible.sort(
        key=lambda f: (f.latitude - origin_lat) ** 2 + (f.longitude - origin_lon) ** 2
    )
    eligible = eligible[:max_candidates]

    facility_nodes = [
        (f, _nearest_node(graph, f.latitude, f.longitude)) for f in eligible
    ]

    return select_best_facility(
        graph, origin_node, facility_nodes, weight=weight, avoid_flooded_hard=avoid_flooded_hard
    )


def build_response_plan(
    graph: nx.MultiDiGraph,
    priority_zone: dict,
    facilities: List[Facility],
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    zone_geometry: Optional[dict] = None,
    flood_geometry=None,
) -> dict:
    """Ties routing to a single priority zone (output of
    risk/impact.py::prioritize_zones) and returns the standardized
    output contract (Fix #5, integration round), ready to be stored in
    `response_plans` and served via POST /api/route.

    ROUTING ORIGIN (Fix #4): the origin is resolved as
    Priority Zone -> Priority Zone Centroid -> nearest road graph node.
    Callers can supply the origin two ways:
      - Explicit `origin_lat`/`origin_lon` (e.g. already computed
        upstream via PostGIS's ST_Centroid) — used as-is if given.
      - `zone_geometry` (or, if omitted, `priority_zone["geometry"]` —
        the pass-through field risk/impact.py now carries per Fix #3) —
        this function derives the centroid itself via `zone_centroid()`.
    Exactly one of these origin sources must resolve to a coordinate, or
    a ValueError is raised (fail loudly rather than silently routing
    from an arbitrary point).

    NOTE ON SIGNATURE: `facilities` moved before the origin parameters
    (previously `origin_lat, origin_lon, facilities`) as part of this
    integration fix, since origin is now optional/derivable. Update call
    sites accordingly.
    """
    if origin_lat is None or origin_lon is None:
        geometry = zone_geometry if zone_geometry is not None else priority_zone.get("geometry")
        if geometry is None:
            raise ValueError(
                "build_response_plan requires either origin_lat/origin_lon, "
                "or zone_geometry (or priority_zone['geometry']) to derive "
                "the routing origin via its centroid."
            )
        origin_lat, origin_lon = zone_centroid(geometry)

    result = find_accessible_route(
        graph, origin_lat, origin_lon, facilities, flood_geometry=flood_geometry
    )

    scenario_id = priority_zone.get("scenario_id")
    priority_zone_id = priority_zone.get("zone_id")
    risk_score = priority_zone.get("risk_score")
    risk_level = priority_zone.get("risk_level")

    if result is None:
        return {
            "scenario_id": scenario_id,
            "priority_zone_id": priority_zone_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommended_facility_id": None,
            "recommended_facility_name": None,
            "route_geometry": {},
            "estimated_distance_km": None,
            "used_flooded_road": False,
            "note": "No accessible facility found — all candidate routes unreachable.",
        }

    plan = {
        "scenario_id": scenario_id,
        "priority_zone_id": priority_zone_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "recommended_facility_id": result["facility"].facility_id,
        "recommended_facility_name": result["facility"].name,
        "route_geometry": result["route_geometry"],
        "estimated_distance_km": result["estimated_distance"],
        "used_flooded_road": bool(result.get("used_flooded_road", False)),
    }
    if result.get("used_flooded_road"):
        plan["note"] = (
            "No fully dry route available — recommended route crosses a "
            "flooded road segment as a last resort."
        )
    return plan
