
# DRISHTI — Data Formats & Standards (Phase 1, Locked)

This document is the single source of truth for spatial reference systems, units,
ID formats, enums, and cross-module data exchange. `ARCHITECTURE.md`,
`DATABASE_SCHEMA.md`, and `API_CONTRACT.md` must not contradict it.

---

## 1. Spatial Data Standard

| Layer | Format | CRS |
|---|---|---|
| Database (persistent vector data) | PostGIS `geometry` columns | **SRID 4326 (WGS84)** |
| API (request/response vector data) | GeoJSON | **WGS84 / EPSG:4326** |
| Raster processing (AI/GIS, in-flight only) | GeoTIFF or in-memory array | Native or projected CRS may be used **temporarily** |

Required flow before any vector result is persisted:

```
Satellite / DEM raster
        ↓
AI or GIS processing
        ↓
Temporary native/projected CRS (if required for accurate area/distance math)
        ↓
Generate flood/result polygon
        ↓
Convert vector result to EPSG:4326
        ↓
Store in PostGIS (geometry(..., 4326))
        ↓
Return as GeoJSON through FastAPI
```

Rule: **no vector data is ever stored in PostGIS in a projected CRS.** Projected
CRS is only acceptable transiently, in memory or in a temp file, for calculations
like accurate area (km²) or distance (km) — convert back to EPSG:4326 before the
`INSERT`/`UPDATE`.

**Geometry type standardization — `critical_infrastructure`:** for MVP consistency,
all critical infrastructure entities, including linear or area-based infrastructure
such as bridges, are represented using a representative Point geometry in
EPSG:4326 (`geometry(Point, 4326)`). No other geometry type is used for this table
in Phase 1.

## 2. File Storage vs. Database

Large binary/raster files are **never** stored in PostgreSQL. They go in Supabase
Storage; PostgreSQL stores only the path + metadata.

Supabase Storage bucket layout:

```
satellite/        raw satellite imagery
dem/               digital elevation model files
flood-masks/       AI-generated flood mask rasters
model-outputs/     other AI model outputs
generated-maps/    rendered map images / reports
```

Example:
```
Supabase Storage:  satellite/post_flood.tif
Supabase Database: satellite_observations.storage_path = "satellite/post_flood.tif"
```

Local/runtime disk storage is permitted **only** as temporary scratch space during
AI/GIS processing (see `ARCHITECTURE.md` §7); the file is deleted once the result is
written to Supabase.

## 3. Units

| Quantity | Unit | Used in |
|---|---|---|
| Flood level | metres (m) | `simulation_scenarios.flood_level`, `POST /api/simulation` request |
| Area | square kilometres (km²) | `flood_predictions.flood_area`, `simulation_scenarios.flooded_area` |
| Distance | kilometres (km) | `response_plans.estimated_distance_km` |
| Time | minutes | `response_plans.estimated_time_minutes` |
| Population | whole persons (integer count) | `population_zones.population`, `*_affected`/`*_exposed` fields |
| Density | people per km² | `population_zones.density` |
| Confidence / risk score | float, 0.0–1.0 | `flood_predictions.confidence`, `risk_zones.risk_score` |
| Affected road segments | integer count | `simulation_scenarios.roads_affected_count` |
| Affected road length *(future, optional)* | kilometres (km) | `simulation_scenarios.affected_road_length_km` — not part of MVP |

`roads_affected_count` is always an integer count of road segments/features
intersected by the flood extent — never a length. This ambiguity is resolved: a
single field must not sometimes mean count and sometimes mean kilometres. If road
length is needed later, it is added as the separate, optional
`affected_road_length_km` field (see `DATABASE_SCHEMA.md` §7); it does not replace
`roads_affected_count`.

## 4. Enumerations (must match `DATABASE_SCHEMA.md` and `API_CONTRACT.md`)

**`satellite_observations.observation_type`**
`pre_flood` | `post_flood`

**`flood_predictions.status`**
`processing` | `completed` | `failed`

**`simulation_scenarios.status`**
`pending` | `running` | `completed` | `failed`

**`risk_zones.risk_level`**
`LOW` | `MODERATE` | `HIGH` | `VERY_HIGH` | `CRITICAL`

**`critical_infrastructure.type`**
`hospital` | `school` | `police_station` | `fire_station` | `relief_centre` | `bridge`
(extendable — add new values here first if a module needs one)

## 5. ID Format

All primary keys and foreign keys are UUID strings (`uuid`, Postgres
`gen_random_uuid()`). API requests/responses represent IDs as JSON strings.

## 6. Engineer-to-Engineer Object Handoff

| Producer | Object | Consumer | Via |
|---|---|---|---|
| Engineer 2 | Flood polygon + mask | Engineer 3 | `flood_predictions` row (PostGIS + Storage path) |
| Engineer 3 | Simulation result | Engineer 4 | `simulation_scenarios` row |
| Engineer 4 | Risk zones, response plans | Engineer 1 (API) | `risk_zones`, `response_plans` rows |
| Engineer 1 | GeoJSON API responses | Engineer 5 (React) | FastAPI JSON, per `API_CONTRACT.md` |

No engineer reads another engineer's in-progress local files or calls another
engineer's module functions directly — all handoff happens through the Supabase
tables above, using the shapes defined in `DATABASE_SCHEMA.md`.

## 7. Impact Calculation Method (for consistency across simulation & risk)

Affected entities are computed with PostGIS spatial queries, not application-level
geometry math:

```
flood polygon (simulation_scenarios.result_geometry)
        ↓
ST_Intersects()
        ↓
roads / critical_infrastructure / population_zones (+ buildings, if adopted)
```

This keeps `roads_affected_count`, `hospitals_affected`, `population_affected`, and
`infrastructure_exposed` derived the same way everywhere they are computed.
