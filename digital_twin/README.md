# `digital_twin/` — Geospatial Digital Twin & Flood Scenario Simulation

**Owner:** Engineer 3
**Project:** DRISHTI (SIH 2026, PS 26206)

This module implements the pieces of DRISHTI that Engineer 3 owns per
`ENGG_3.txt`:

1. DEM processing
2. Lightweight 2D geospatial Digital Twin (read-layer only — see below)
3. Flood scenario simulation (`elevation <= flood_level`)
4. Flood depth calculation (`flood_level - elevation`, positive only)
5. Flood mask → flood polygon generation, reprojected to EPSG:4326
6. PostGIS-based spatial impact calculation (population, roads, hospitals,
   buildings)
7. Persistence of results into `simulation_scenarios`

It deliberately does **not** implement: AI flood detection, the React
frontend, emergency routing, or the overall Supabase schema — those belong
to Engineers 2, 5, 4, and 1 respectively (`ARCHITECTURE.md` §4).

## ⚠️ What this model is — and isn't

This is a **scenario-based potential inundation model**, not an accurate
hydrodynamic flood prediction. It answers:

> "If water reaches this elevation, which areas could potentially be
> affected?"

It does **not** model water flow, connectivity to a source, drainage, or
time — a low-lying pixel with no path to the flood source is still marked
"potentially flooded." This is an explicit, accepted MVP simplification
(`COMMON.txt` #5: *"Do NOT build a full hydrodynamic flood model"*). Do not
present this as a hydrodynamic prediction in the SIH demo.

## Files

| File | Purpose |
|---|---|
| `dem.py` | Load a DEM GeoTIFF from local scratch disk into a NumPy array + georeferencing info. |
| `simulation.py` | Core `elevation <= flood_level` mask, depth calc, and per-scenario orchestration. |
| `geometry.py` | Vectorize the flood mask into a polygon, reproject to EPSG:4326, compute area in km². |
| `impact.py` | PostGIS `ST_Intersects` queries against `roads`, `critical_infrastructure`, `population_zones`, optional `buildings`; persists to `simulation_scenarios`. |
| `example_scenario.py` | End-to-end example: runs the 2.5m / 3.0m / 3.5m example scenario set from `ENGG_3.txt`. |
| `requirements.txt` | Module-scoped dependency list (subset of the project's full `requirements.txt`). |
| `tests/` | Unit tests. `test_simulation.py` needs only NumPy. `test_dem.py` / `test_geometry.py` need rasterio + shapely + pyproj. `test_impact.py` needs neither a real database nor the geospatial stack — it uses a fake DB-API connection (`tests/fakes.py`). All geospatial-dependent test files skip cleanly (not fail) if their dependency isn't installed yet. |

## Pipeline

```
Supabase Storage (dem/*.tif)
        │  (downloaded to local temp file by caller — Engineer 1's service layer)
        ▼
dem.load_dem()                     -> DEMData (elevation array, transform, source CRS)
        │
        ▼
simulation.run_simulation()
        │  compute_flood_mask()    -> boolean mask (elevation <= flood_level)
        │  compute_flood_depth()   -> depth array (flood_level - elevation, >=0)
        │  geometry.mask_to_multipolygon_4326()
        │        -> vectorize mask (rasterio.features.shapes)
        │        -> reproject to EPSG:4326  (DATA_FORMATS.md §1)
        │  geometry.calculate_area_km2()
        │        -> transient equal-area reprojection, km²
        ▼
SimulationResult (flood_level, flooded_area_km2, result_geometry_geojson/wkt, ...)
        │
        ▼
impact.calculate_all_impacts()     -> ST_Intersects against roads / critical_infrastructure /
        │                               population_zones / buildings (region-scoped)
        ▼
impact.save_simulation_scenario()  -> INSERT INTO simulation_scenarios ... RETURNING id
```

The local DEM file should be deleted once processing is complete
(`dem.cleanup_local_file()`) — per `ARCHITECTURE.md` §7, local disk is
scratch space only, never a persistent store.

## Usage

```python
from digital_twin import dem, simulation, impact

# 1. Load DEM (already downloaded locally from Supabase Storage by the caller)
dem_data = dem.load_dem("/tmp/region_dem.tif")

# 2. Run one or more scenarios
results = [simulation.run_simulation(dem_data, level) for level in (2.5, 3.0, 3.5)]

for r in results:
    print(r.flood_level, r.flooded_area_km2, "km^2")

# 3. Compute impact + persist (requires an open psycopg2 connection, e.g. to
#    the Supabase Postgres instance — connection string from env, never hardcoded)
import psycopg2, os
conn = psycopg2.connect(os.environ["DATABASE_URL"])

region_id = "…"  # uuid from `regions`
for r in results:
    if r.result_geometry_wkt is None:
        continue  # no inundation at this level
    impact_result = impact.calculate_all_impacts(conn, region_id, r.result_geometry_wkt)
    scenario_id = impact.save_simulation_scenario(
        conn,
        region_id=region_id,
        scenario_name=f"Scenario {r.flood_level}m",
        flood_level=r.flood_level,
        flooded_area_km2=r.flooded_area_km2,
        impact=impact_result,
        result_geometry_wkt=r.result_geometry_wkt,
    )
```

Or from the command line:

```bash
# Simulation-only — no database, no region_id required:
python -m digital_twin.example_scenario /path/to/region_dem.tif

# Full DB pipeline — impact calculation + persistence, region_id required:
DATABASE_URL="postgresql://...supabase connection string..." \
    python -m digital_twin.example_scenario /path/to/region_dem.tif <region_id>
```

The two modes are selected purely by argument count: pass just the DEM path
for a DB-free simulation sanity check; add a `region_id` as a second
argument to run the full impact + persistence pipeline (which then also
requires `DATABASE_URL` to be set — see `run_with_db()` in
`example_scenario.py`).

## Running the tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

`test_simulation.py` covers the core mask/depth math and needs nothing but
NumPy. `test_impact.py` covers `impact.py`'s query-building and
control-flow logic (including the buildings three-state behavior and the
commit/rollback paths) against a fake DB-API connection — no live database
needed, no rasterio/shapely/pyproj needed either. `test_dem.py` and
`test_geometry.py` build small synthetic DEMs on the fly (no real regional
DEM required) and cover, among other things, the required invariant
`area(2.5m) <= area(3.0m) <= area(3.5m)` and the missing-CRS behavior
described below.

Note: `test_impact.py` deliberately does **not** verify the SQL is valid
PostGIS syntax or that `ST_Intersects` behaves correctly against real
geometry — that needs a real PostGIS instance and is out of scope for this
unit-test pass. If/when the team wants that coverage, it belongs in a
separate integration-test suite (e.g. `tests/integration/`, gated behind a
`DATABASE_URL` env var), not mixed into these dependency-free unit tests.

## Fixed in the second review pass (schema/impact-testing focus)

- Added `tests/test_impact.py` + `tests/fakes.py` — fake DB-API connection
  covering `calculate_population_affected`, `calculate_roads_affected_count`,
  `calculate_hospitals_affected`, `calculate_infrastructure_breakdown`, all
  three `buildings` states (missing table / no rows / has rows), and
  `save_simulation_scenario`'s commit-on-success and rollback-on-failure paths.
- `buildings_table_exists()` now constrains its `information_schema.tables`
  lookup to `current_schema()`, so it can't false-positive on an unrelated
  `buildings` table in a different schema.
- Verified all 11 `simulation_scenarios` columns written by
  `save_simulation_scenario()` against `DATABASE_SCHEMA.md` §7 exactly:
  `region_id`, `flood_prediction_id`, `scenario_name`, `flood_level`,
  `flooded_area`, `population_affected`, `buildings_affected`,
  `roads_affected_count`, `hospitals_affected`, `result_geometry`, `status`
  — no mismatch found, no schema change made.
- Reworded the `buffer(0)` comment in `geometry.py` to not overclaim that it
  can never alter geometry.

## SCHEMA CONFIRMATION REQUIRED

**`result_geometry` nullability is unconfirmed and must be checked against
the live Supabase table before demo day.**

`DATABASE_SCHEMA.md` §7 marks `flood_prediction_id` and `buildings_affected`
explicitly `nullable`, but has no nullability annotation at all for
`result_geometry`. `save_simulation_scenario()` writes `NULL` for
`result_geometry` whenever a scenario has zero inundation (correct per the
flood model — no flooding means no polygon) — but if the live table has a
`NOT NULL` constraint on that column, every zero-inundation scenario save
will fail with a constraint violation the first time it runs against a real
database, and the mocked unit tests in `tests/test_impact.py` won't catch
this, since they don't enforce real column constraints.

**Action needed from Engineer 1 before integration:** confirm whether
`result_geometry` is nullable. If it is not, the team needs to decide how to
represent a zero-inundation scenario (e.g. an empty `MULTIPOLYGON EMPTY`
literal instead of `NULL`) — that's a schema-owner decision, not something
to guess here.

## Fixed in the third review pass (schema/PostGIS validation focus)

- Fixed a stale docstring in `example_scenario.py`: the "no live Supabase
  connection needed" example command incorrectly included `<region_id>`,
  which actually triggers the full DB-requiring pipeline. Corrected to show
  the two modes distinctly (simulation-only vs. full DB pipeline).
- Reviewed `impact.py`'s four `ST_Intersects` queries and
  `save_simulation_scenario()`'s INSERT against `DATABASE_SCHEMA.md` §7
  field-by-field — no mismatch, no code change needed there.
- Identified the `result_geometry` nullability gap above — flagged for
  Engineer 1, not coded around.
- Recommended (not implemented, per "small test infra only") a short
  integration-test script using the existing `example_scenario.py` against
  a real seeded Supabase dev instance, rather than new pytest
  infrastructure — see "Running the tests" above.

## Contract compliance

This module was built against the **locked Phase 1 docs** and does not
deviate from them:

- **CRS**: raster processing may use the DEM's native/projected CRS
  transiently; every geometry returned for persistence is reprojected to
  **EPSG:4326** before it leaves `geometry.py` (`DATA_FORMATS.md` §1).
  **A DEM with no embedded CRS raises a `ValueError`** rather than being
  defaulted to EPSG:4326 or anything else — `load_dem()` accepts an optional
  `crs_override` for the rare case where the caller has independently
  confirmed the DEM's true CRS out-of-band. This was a fixed bug (see
  "Fixed in review" below) — never re-introduce a default here.
- **Units**: `flood_level` in metres, `flooded_area` in km²,
  `roads_affected_count` is always an integer **count**, never a length
  (`DATA_FORMATS.md` §3).
- **Schema**: `simulation_scenarios` columns are written exactly as defined
  in `DATABASE_SCHEMA.md` §7 (`region_id`, `flood_prediction_id`,
  `scenario_name`, `flood_level`, `flooded_area`, `population_affected`,
  `buildings_affected`, `roads_affected_count`, `hospitals_affected`,
  `result_geometry`, `status`).
- **Impact method**: population/roads/hospitals/buildings affected are all
  computed via `ST_Intersects()` against the shared reference layers, not
  application-level geometry math (`DATA_FORMATS.md` §7).
- **No DB duplication**: this module never creates or alters tables it
  doesn't own; it only reads `roads` / `critical_infrastructure` /
  `population_zones` / `buildings` and writes `simulation_scenarios`
  (`ARCHITECTURE.md` §4, rule 2).
- **`buildings_affected`**: returned as `None` (→ SQL `NULL`) whenever the
  optional `buildings` table doesn't exist or has no rows for the region,
  never silently reported as `0` (`DATABASE_SCHEMA.md` §4 note).

## Documented assumptions

These are called out per `COMMON.txt` #16 ("If something is unclear,
document the assumption instead of silently changing architecture") and are
not architecture changes — flag for team sign-off if any should change:

1. **Population weighting.** `calculate_population_affected()` sums the
   *entire* population of any `population_zones` polygon that intersects the
   flood extent at all (not area-weighted by overlap fraction). An
   area-weighted version (`ST_Intersection` + area ratio) is a natural
   follow-up but was out of scope for the 10-day MVP.
2. **DEM vertical datum.** `flood_level` is assumed to be in the same
   vertical reference as the input DEM (e.g. both relative to a local
   benchmark, or both EGM96/WGS84 ellipsoidal height). No datum conversion
   is performed. If the seeded DEM and any future ground-truth flood levels
   use different datums, this needs an explicit fix before demo.
3. **Hydrological connectivity.** Not modelled (see the "What this model is"
   section above) — this is the accepted scope per `COMMON.txt` #5, not an
   oversight.
4. **DB connection ownership.** `impact.py` takes an already-open DB-API
   connection rather than opening its own, so it stays agnostic to how
   Engineer 1 wires the Supabase Postgres connection string into FastAPI.

## Fixed in code review (2026-08-22)

A structured review against the locked docs found and fixed one correctness
bug and several robustness gaps. Kept here as a durable record so the fixes
aren't accidentally reverted:

- **Critical:** `dem.py` no longer defaults a missing DEM CRS to EPSG:4326 —
  it raises `ValueError` unless the caller explicitly supplies `crs_override`.
- `dem.py` now uses rasterio's native masked read instead of a manual
  `elevation == nodata` float comparison (avoids precision-drift bugs).
- `dem.py` raises a clear error on an all-NoData (empty) DEM, and wraps
  `RasterioIOError` with a clearer message for corrupt files.
- `simulation.py` rejects non-finite (`NaN`/`inf`) `flood_level` values, but
  deliberately does **not** enforce `flood_level >= 0` — no vertical-datum
  contract exists in the project docs to justify that restriction.
- `geometry.py` checks (and repairs via `buffer(0)`) invalid geometry from
  `unary_union`, and verifies a projected CRS's axis unit is actually metres
  before trusting `geom.area` as square metres.
- `impact.py`'s `save_simulation_scenario()` now rolls back the transaction
  on failure instead of leaving it half-open; `calculate_buildings_affected()`
  accepts a pre-computed `table_exists` flag so a caller looping over several
  scenarios doesn't re-query `information_schema` every time.
- Added `tests/` (previously missing entirely) — see "Running the tests" above.
