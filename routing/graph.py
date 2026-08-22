"""
DRISHTI — Engineer 4
Routing / Graph Module

Builds a road-network graph (OSMnx/NetworkX) for a region and marks edges
that intersect the simulated flood polygon as unsafe, so the routing
module can penalize or remove them before computing shortest paths.

Per the brief, this deliberately uses OSMnx + NetworkX + Dijkstra rather
than a custom routing engine — no reinvented pathfinding for a 10-day
prototype.

------------------------------------------------------------------------
NETWORK / DATA NOTE
------------------------------------------------------------------------
This module calls osmnx.graph_from_polygon(), which downloads live data
from the OpenStreetMap Overpass API. That call requires outbound network
access and is NOT executed as part of this deliverable's automated
checks — it is exercised at integration time against the region chosen
in MODULE 1 (Data Collection). The functions below are structured so
Engineer 1's ingest_osm.py can either (a) call these directly with a
live network connection, or (b) pass in a pre-built graph object (e.g.
loaded from a cached .graphml file) via `graph_from_graphml()`, keeping
this module usable offline during demos.
------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Optional

import networkx as nx

# osmnx/shapely are only needed for the OSM-download and geometry-
# intersection paths (build_road_graph, mark_flooded_edges). The pure
# graph-manipulation logic (apply_flood_penalty, remove_flooded_edges,
# flooded_edge_count, ensure_graph_crs_4326) works on any networkx graph
# and must stay importable/testable without these heavier geospatial
# dependencies installed (they are not always available in CI/dev
# sandboxes and are not needed to unit-test routing logic).
try:  # pragma: no cover - import availability, not business logic
    import osmnx as ox
except ImportError:  # pragma: no cover
    ox = None

try:  # pragma: no cover
    from shapely.geometry import shape, Polygon
    from shapely.geometry.base import BaseGeometry
except ImportError:  # pragma: no cover
    shape = Polygon = BaseGeometry = None

# Edge attribute used to flag a road segment as flood-unsafe.
FLOODED_ATTR = "flooded"
# Multiplier applied to an unsafe edge's travel weight instead of hard
# removal, when `hard_remove=False`. High enough that Dijkstra will only
# ever choose it if there is truly no alternative route.
PENALTY_MULTIPLIER = 1000

# CRS all geometry comparisons happen in. GeoJSON (RFC 7946) is always
# WGS84 / EPSG:4326, and Engineer 1's PostGIS geometry columns are stored
# in the same CRS, so this is the fixed target for road-graph coordinates
# too.
TARGET_CRS = "epsg:4326"


def _require(module, name: str):
    if module is None:
        raise ImportError(
            f"{name} is required for this operation but is not installed. "
            "Install it (see routing/README.md) or use the pure-networkx "
            "functions (apply_flood_penalty, remove_flooded_edges) if you "
            "already have flooded-edge keys computed elsewhere."
        )


def build_road_graph(
    place_name: Optional[str] = None,
    polygon: "Optional[Polygon]" = None,
    network_type: str = "drive",
) -> nx.MultiDiGraph:
    """Builds a routable road graph for a region.

    Provide either `place_name` (e.g. "Kochi, Kerala, India") or a
    `polygon` (shapely Polygon in lon/lat, matching the `regions.geometry`
    column from Engineer 1's schema). Exactly one should be supplied.
    """
    _require(ox, "osmnx")
    if polygon is not None:
        graph = ox.graph_from_polygon(polygon, network_type=network_type)
    elif place_name is not None:
        graph = ox.graph_from_place(place_name, network_type=network_type)
    else:
        raise ValueError("Provide either place_name or polygon.")

    graph = ox.add_edge_speeds(graph)
    graph = ox.add_edge_travel_times(graph)
    return graph


def graph_from_graphml(path: str) -> nx.MultiDiGraph:
    """Loads a previously cached graph (offline / demo-safe path)."""
    _require(ox, "osmnx")
    return ox.load_graphml(path)


def save_graph(graph: nx.MultiDiGraph, path: str) -> None:
    _require(ox, "osmnx")
    ox.save_graphml(graph, path)


def ensure_graph_crs_4326(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """FIX (CRS safety): previously this module *assumed* every graph was
    already EPSG:4326 in a comment, with no actual check. A cached
    .graphml file can carry a projected CRS (e.g. a local UTM zone saved
    by a different tool), and comparing its edge coordinates directly
    against WGS84 GeoJSON flood geometry would silently produce wrong
    (or zero) intersections.

    This function checks `graph.graph["crs"]` (the metadata OSMnx/
    networkx store on the graph object) and reprojects to EPSG:4326 if
    it differs, using osmnx's projection helper (pyproj under the hood).

    DOCUMENTED ASSUMPTION: if the graph has no CRS metadata at all (the
    "crs" key is missing), we assume it is already EPSG:4326. This
    matches OSMnx's default download CRS and Engineer 1's PostGIS
    columns, and keeps this check lightweight rather than attempting
    coordinate-range CRS *detection*, which is out of scope for a 10-day
    prototype. If this assumption is ever wrong for a given cached
    graph, `save_graph()` should be re-run after an explicit reprojection
    upstream.
    """
    graph_crs = graph.graph.get("crs")
    if graph_crs is None:
        return graph  # documented assumption: treat as already EPSG:4326

    crs_str = str(graph_crs).lower().replace(" ", "")
    if crs_str in (TARGET_CRS, "wgs84", "4326", "epsg:4326"):
        return graph

    _require(ox, "osmnx")
    return ox.projection.project_graph(graph, to_crs=TARGET_CRS)


def _flood_geometry_from_geojson(geojson_geometry: dict) -> "BaseGeometry":
    """Converts the GeoJSON produced by the AI flood-detection module
    (flood_predictions.geometry / flood_events.geometry) into a shapely
    geometry for intersection tests. GeoJSON is always WGS84 (RFC 7946),
    matching TARGET_CRS, so no reprojection is needed on this side."""
    _require(shape, "shapely")
    return shape(geojson_geometry)


def find_flooded_edges(graph: nx.MultiDiGraph, flood_geojson: dict) -> set:
    """Returns the set of (u, v, k) edge keys whose geometry intersects
    the flood polygon. Pure detection step — does not mutate the graph.
    Requires osmnx + shapely (geometry intersection)."""
    _require(ox, "osmnx")
    _require(shape, "shapely")

    graph = ensure_graph_crs_4326(graph)
    flood_geom = _flood_geometry_from_geojson(flood_geojson)
    edge_geoms = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    flooded = set()
    for edge_key, row in edge_geoms.iterrows():
        if row["geometry"].intersects(flood_geom):
            flooded.add(edge_key)
    return flooded


def apply_flood_penalty(
    graph: nx.MultiDiGraph, flooded_edge_keys: set, hard_remove: bool = False
) -> nx.MultiDiGraph:
    """Pure networkx logic (no osmnx/shapely needed) — given a set of
    (u, v, k) edge keys already known to be flooded, marks them and
    either penalizes or removes them. Separated from `find_flooded_edges`
    so this step (and routing on top of it) can be unit-tested with a
    hand-built graph and no geospatial dependencies installed.
    """
    for u, v, k, data in graph.edges(keys=True, data=True):
        is_flooded = (u, v, k) in flooded_edge_keys
        data[FLOODED_ATTR] = is_flooded
        base_weight = data.get("travel_time", data.get("length", 1.0))
        if is_flooded:
            data["routing_weight"] = base_weight * PENALTY_MULTIPLIER
        else:
            data["routing_weight"] = base_weight

    if hard_remove:
        graph.remove_edges_from(list(flooded_edge_keys))

    return graph


def mark_flooded_edges(
    graph: nx.MultiDiGraph, flood_geojson: dict, hard_remove: bool = False
) -> nx.MultiDiGraph:
    """Convenience wrapper: detects flooded edges via geometry
    intersection (requires osmnx + shapely) and applies the penalty/
    removal in one call. Returns the same graph object (mutated in
    place).

    `flood_geojson` is the GeoJSON geometry from the current
    simulation_scenarios / flood_predictions row (Engineer 3's output).
    """
    graph = ensure_graph_crs_4326(graph)
    flooded_keys = find_flooded_edges(graph, flood_geojson)
    return apply_flood_penalty(graph, flooded_keys, hard_remove=hard_remove)


def remove_flooded_edges(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Hard-removal variant for edges already marked via FLOODED_ATTR
    (e.g. by a prior mark_flooded_edges(..., hard_remove=False) call).
    Use this when you want routes to NEVER use a flooded road even if
    it's the only path (routing will then raise nx.NetworkXNoPath, which
    the caller should handle — see emergency_route.py)."""
    flooded_edges = [
        (u, v, k)
        for u, v, k, data in graph.edges(keys=True, data=True)
        if data.get(FLOODED_ATTR)
    ]
    graph.remove_edges_from(flooded_edges)
    return graph


def flooded_edge_count(graph: nx.MultiDiGraph) -> int:
    return sum(
        1 for _, _, data in graph.edges(data=True) if data.get(FLOODED_ATTR)
    )
