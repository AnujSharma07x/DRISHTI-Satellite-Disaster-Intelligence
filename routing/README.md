# Routing Module — DRISHTI (Engineer 4)

Flood-aware emergency routing: builds a road network, marks flooded
roads as unsafe, and finds the nearest ACCESSIBLE emergency facility
using Dijkstra shortest-path via NetworkX. This README reflects the
state after the Engineer 4 Fix Prompt (see "Fixes applied" below).

## Files

| File | Purpose |
|---|---|
| `graph.py` | Builds/loads the road graph (OSMnx) and marks edges intersecting the flood polygon. |
| `emergency_route.py` | Finds the nearest reachable, minimum-road-distance facility and computes the route. |

## Stack (unchanged, per project constraint)

- **OpenStreetMap** — road network source (via OSMnx's Overpass API calls).
- **OSMnx** — graph construction, geocoding helpers, edge speed/travel-time enrichment, CRS reprojection.
- **NetworkX** — the graph data structure and `shortest_path` (Dijkstra by default with a numeric `weight`).

No custom pathfinding, no alternative routing API, no hydrodynamic
modelling.

## Package usage

```python
# From project root:
from routing.graph import build_road_graph, mark_flooded_edges, apply_flood_penalty
from routing.emergency_route import find_accessible_route, build_response_plan, select_best_facility

# Or run/import as flat scripts inside routing/ — both modes work via a
# try/except relative-import shim in emergency_route.py.
```

## Dependency layering (important for testability)

`osmnx` and `shapely` are only imported where strictly necessary
(OSM download, lat/lon→node snapping, geometry intersection). They are
guarded with `try/except ImportError`, so the **pure NetworkX algorithm
code** — `apply_flood_penalty`, `select_best_facility`,
`ensure_graph_crs_4326` (no-CRS-metadata path) — imports and runs with
just `networkx` installed. This is what makes `tests/test_routing.py`
runnable without a live network connection or the full geospatial stack.

## Workflow

```
Road Network (OSMnx)
        ↓
ensure_graph_crs_4326() — normalize to EPSG:4326 before any geometry comparison
        ↓
find_flooded_edges() — intersect edges with flood polygon (GeoJSON from Engineer 3)
        ↓
apply_flood_penalty() — penalize (soft) or remove (hard) unsafe edges
        ↓
select_best_facility() — actual road-distance shortest path to every eligible,
        ↓                 reachable facility; picks the true minimum
Nearest accessible facility + route
```

Two avoidance modes are supported:

- **Soft-avoid (default)** — flooded edges get `routing_weight` multiplied
  by 1000 (`PENALTY_MULTIPLIER`), so Dijkstra strongly prefers dry roads.
  `select_best_facility` additionally checks whether the winning route to
  each candidate actually touches a flooded edge, and only falls back to
  a flooded route if **no** candidate has a fully dry path (see Fix #4).
- **Hard-avoid** — call `graph.remove_flooded_edges()` or
  `apply_flood_penalty(..., hard_remove=True)` first; flooded roads are
  deleted from the graph entirely. Unreachable facilities are then
  correctly discarded via `nx.NetworkXNoPath` handling.

## Routing origin (Priority Zone → Emergency Facility)

The MVP routing origin follows:

```
Priority Zone
      ↓
Priority Zone Centroid
      ↓
Nearest road graph node
      ↓
Emergency facility
```

The computed route represents an emergency response route **from** the
selected high-risk zone **to** an accessible emergency facility.
`build_response_plan()` supports two ways to supply the origin:

- **Explicit** `origin_lat`/`origin_lon` — used as-is (e.g. if PostGIS's
  own `ST_Centroid` was already computed upstream).
- **Zone geometry** — pass `zone_geometry`, or simply leave it out and
  rely on `priority_zone["geometry"]` (the pass-through field
  `risk/impact.py`'s `ZoneCandidate`/`prioritize_zones()` now carries).
  `zone_centroid()` computes the centroid via shapely.

Engineer 4 does not invent, simulate, or fetch zone geometry — it only
derives a centroid coordinate from geometry the caller already produced
(Engineer 3's flood extent / Engineer 1's PostGIS `risk_zones.geometry`).
If neither an explicit origin nor any geometry is available,
`build_response_plan()` raises `ValueError` rather than silently routing
from an arbitrary point.

## Output contract (standardized — integration-round Fix #5)

```json
{
    "scenario_id": "scn_001",
    "priority_zone_id": "zone_a",
    "risk_score": 87.5,
    "risk_level": "CRITICAL",
    "recommended_facility_id": "fac_1",
    "recommended_facility_name": "Riverside General Hospital",
    "route_geometry": { "type": "LineString", "coordinates": [[lon, lat], ...] },
    "estimated_distance_km": 4.2,
    "used_flooded_road": false
}
```

Produced by `emergency_route.build_response_plan()` — ready to store in
`response_plans` and serve via `POST /api/route`. Two fields were
renamed for clarity from an earlier draft of this contract:
`estimated_distance` → **`estimated_distance_km`** (unit made explicit),
and the single ambiguous `"priority_zone"` display-name string was
split into `priority_zone_id` (matches `risk_zones`/`zone_id`) plus the
now-always-present `used_flooded_road` boolean (previously only implied
via an optional `"note"`). If the recommended route had to cross a
flooded segment as a last resort (no dry option existed to any candidate
facility), the response additionally includes a `"note"` field — the
database schema itself is unchanged.

When no facility is reachable at all, the same shape is returned with
`recommended_facility_id`/`recommended_facility_name` = `null`,
`route_geometry` = `{}`, `estimated_distance_km` = `null`,
`used_flooded_road` = `false`, and a `"note"` explaining why.

---

## Fixes applied

### Fix #4 — Emergency facility selection (the core correctness bug)

**Bug:** the previous implementation sorted candidate facilities by
straight-line (lat/lon) distance from the origin and returned the
**first** one with any reachable, non-flooded route — not the one with
the shortest actual road distance. A facility 1km away as the crow
flies but 12km by a winding road could beat one 2km away but only 4km
by road.

**Fix:** `select_best_facility()` now:
1. Computes the actual NetworkX shortest-path route + distance to
   **every** eligible candidate (straight-line distance is used only as
   a cheap pre-filter down to `MAX_CANDIDATES = 8` facilities, to bound
   the number of `shortest_path` calls on a large graph — see
   `find_accessible_route()`).
2. Discards candidates with no path at all (`nx.NetworkXNoPath`).
3. Among candidates whose route does not touch a flooded edge, selects
   the one with the **minimum actual road distance**.
4. Only if no dry route exists to *any* candidate does it fall back to
   the minimum-distance flooded route, explicitly flagged via
   `used_flooded_road: True` (surfaced as a `"note"` in
   `build_response_plan()`'s output).
5. Returns `None` only if nothing is reachable at all.

Additionally (per Fix #4 step 1), `find_accessible_route()` accepts an
optional `flood_geometry` parameter — if supplied, facilities whose
point location falls inside the flood polygon are excluded from the
candidate set entirely (requires shapely; skipped with no error if
shapely or the geometry isn't provided — documented MVP limitation).

Verified by `tests/test_routing.py::test_facility_selection_uses_actual_road_distance_not_straight_line`,
which reproduces the exact brief example (Facility A: close by air, far
by road; Facility B: far by air, close by road) and asserts Facility B
is selected.

### Fix #5 — Flooded road handling (unchanged approach, confirmed correct)

Still OSMnx + NetworkX + Dijkstra, no other routing engine introduced.
`graph.find_flooded_edges()` (geometry intersection, needs
osmnx+shapely) is now cleanly separated from `graph.apply_flood_penalty()`
(pure NetworkX edge marking/weighting/removal), so the two concerns —
"which edges are flooded" and "what do we do about it" — are
independently testable.

### Fix #6 — CRS safety

**Bug:** the previous code had only a *comment* asserting "OSMnx graphs
default to EPSG:4326 (lon/lat), matching GeoJSON, so direct shapely
intersection is valid without reprojecting" — with no actual check. A
cached `.graphml` reprojected by another tool could carry a different
CRS, and comparing its coordinates directly against WGS84 flood GeoJSON
would silently produce wrong (or zero) intersections.

**Fix:** `ensure_graph_crs_4326()` now:
- Reads `graph.graph["crs"]` metadata.
- If present and not EPSG:4326, reprojects via
  `osmnx.projection.project_graph(graph, to_crs="epsg:4326")`.
- If osmnx isn't available to do that reprojection, **raises** rather
  than silently comparing mismatched coordinate systems.
- **Documented assumption:** if the graph has no CRS metadata at all
  (`"crs"` key missing), it is assumed to already be EPSG:4326 — this
  matches OSMnx's default download CRS and Engineer 1's PostGIS columns.
  This is a lightweight, explicit assumption rather than an attempt at
  coordinate-range CRS *detection*, which is out of scope for a 10-day
  prototype.
- `mark_flooded_edges()` now calls this normalization before any
  intersection test.

### Fix #7 — Route geometry (unchanged, confirmed compatible)

Still a node-based `LineString` built directly from graph node `x`/`y`
attributes. No curved OSM edge-geometry reconstruction was added, per
the brief's explicit "do not spend significant time" guidance. Compatible
as-is with `response_plans.route_geometry` (Engineer 1's schema,
unchanged).

### Fix #8 — Package imports

`graph.py` has no internal cross-module imports. `emergency_route.py`
previously did a hard `from graph import FLOODED_ATTR`, which breaks
when imported as `routing.emergency_route` from the project root
(Python wouldn't find a top-level `graph` module). Both now use:

```python
try:
    from .graph import FLOODED_ATTR      # package import (project root)
except ImportError:
    from graph import FLOODED_ATTR       # flat script import (inside routing/)
```

`__init__.py` files were added to `risk/` and `routing/` so both are
proper importable packages. Verified with:

```python
from risk.risk_engine import assess
from risk.impact import prioritize_zones
from routing.graph import apply_flood_penalty
from routing.emergency_route import select_best_facility
```

No circular imports were introduced (`emergency_route` depends on
`graph`; nothing in `graph` depends on `emergency_route`).

---

## Integration-round fixes (Final Integration Fix Prompt)

### Routing origin and standardized output contract

See the "Routing origin" and "Output contract" sections near the top of
this README.

### `build_response_plan()` signature change — **breaking change, flag for FastAPI callers**

Previous signature:
```python
build_response_plan(graph, priority_zone, origin_lat, origin_lon, facilities, flood_geometry=None)
```

New signature:
```python
build_response_plan(graph, priority_zone, facilities, origin_lat=None, origin_lon=None, zone_geometry=None, flood_geometry=None)
```

`facilities` moved earlier (now the third positional argument) and
`origin_lat`/`origin_lon` became optional keyword arguments, since the
origin can now be derived from zone geometry instead. **Any existing
FastAPI/service-layer call site using positional arguments must be
updated** — the old `build_response_plan(g, zone, lat, lon, facilities)`
call order will now bind `facilities` to `origin_lat`, which will fail
(rather than silently misrouting, since `origin_lat` would then be a
list rather than a float and `_nearest_node` would raise), but the call
site should still be fixed rather than relied upon to error correctly.

### `zone_centroid()` — new helper

Computes a `(lat, lon)` centroid from GeoJSON geometry via shapely.
Guarded the same way as the rest of the module's shapely usage — raises
`ImportError` with a clear message if shapely isn't installed and no
explicit `origin_lat`/`origin_lon` was supplied instead.

### Road-impact field naming (shared with `risk/`)

`routing/` does not itself compute or reference the renamed
`roads_affected_km` / `affected_road_segments` fields (those live
entirely in `risk/risk_engine.py`/`impact.py`), but note them here since
`priority_zone` dicts passed into `build_response_plan()` originate from
`risk/impact.py::prioritize_zones()` and now carry `roads_affected_km`
(not the old ambiguous `roads_affected`) if that context is surfaced
downstream.

---

## Testing

```bash
python3 tests/test_routing.py
```

Covers:
- Dry route exists.
- Flooded route exists but a dry alternative exists (must route around).
- No accessible route at all (`select_best_facility` returns `None`).
- Only a flooded route is reachable → used as a flagged last resort.
- **Facility-selection regression:** selection by actual road distance,
  not straight-line distance.
- `apply_flood_penalty` marking/weighting and hard-removal.
- **CRS regression:** passthrough when metadata is absent or already
  4326; raises (rather than silently mis-comparing) when a non-4326 CRS
  is declared and osmnx isn't available to reproject it.
- **Integration-round regressions:** `build_response_plan()`'s
  standardized output contract with an explicit origin; the
  centroid-derived origin path (zone geometry → centroid → route);
  `ValueError` when no origin source is available; the "no facility
  reachable" response shape under the new contract.

The core algorithm tests (everything above except the four
`build_response_plan` tests) run with just `networkx` installed. The
four `build_response_plan` tests substitute a tiny in-test fake for
`osmnx.nearest_nodes` (and, for the centroid test, `shapely.geometry.shape`)
so the full origin-resolution and node-snapping flow is exercised
end-to-end without those heavier dependencies installed — see
`_FakeOx`/`_fake_shape` in `tests/test_routing.py`. This is a test-only
stand-in; production code still uses real osmnx/shapely via the same
`try/except ImportError` guards described above.

## Network / offline / GraphML workflow

`build_road_graph()` calls OSMnx's Overpass API, which requires
outbound network access — exercised at integration time against the
region chosen in Module 1 (Data Collection), not inside this
deliverable's offline test suite (no live network call is made by
`tests/test_routing.py`). For demo reliability:

```python
graph.save_graph(g, "region.graphml")          # cache once, ahead of the demo
g = graph.graph_from_graphml("region.graphml")  # instant, no network call
```

## Facility eligibility

Only `critical_infrastructure` rows (Engineer 1's schema) with `type` in
`{Hospital, Fire Station, Police Station, Relief Centre}` are considered.
Bridges/schools exist in the same table but are excluded from emergency-
facility routing.

## MVP limitations

- Facility-in-flood-zone exclusion (`flood_geometry` param) requires
  shapely and an explicit flood polygon; if either is missing, the check
  is silently skipped (facilities are not excluded), not silently marked
  safe — the caller controls whether this check runs at all.
- The straight-line pre-filter (`MAX_CANDIDATES = 8`) assumes the true
  nearest-by-road facility is very likely among the 8 nearest-by-air
  candidates. This is a reasonable assumption for typical road networks
  but could theoretically miss the 9th-nearest-by-air facility being
  closer by road in a region with unusually sparse/indirect roads.
  Raise `max_candidates` if that becomes a real concern for the chosen
  demo region.
- `zone_centroid()` requires shapely to derive an origin from zone
  geometry. If shapely isn't installed, the caller must supply an
  explicit `origin_lat`/`origin_lon` to `build_response_plan()` instead
  (e.g. computed upstream via PostGIS's own `ST_Centroid`).

## Explicitly out of scope (per project constraints)

- No modification of the AI model, React UI, database schema, or Digital
  Twin architecture — this module only reads facility/flood geometry and
  writes `response_plans`-shaped output.
- No custom routing algorithm — NetworkX's built-in Dijkstra only.
- No alternative routing API/service.
