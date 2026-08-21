
- Region selection (one flood-prone Indian region, seeded)
- Flood polygon input → stored in PostGIS (`flood_predictions`)
- Digital Twin read layer (region, roads, population zones, critical infrastructure,
  flood state, risk state) served from Supabase
- Flood-level scenario simulation (`POST /api/simulation`) with impact numbers
- Risk zone output (`risk_zones`)
- React dashboard showing map + simulation + statistics
- FastAPI backend connecting frontend to Supabase

### NICE TO HAVE
- Emergency routing (`POST /api/route`) and response plans
- `buildings` layer and buildings-affected counts
- `flood_events` grouping of predictions

### FUTURE EXTENSIONS (explicitly out of scope for Phase 1)
- Multiple disaster types (cyclone, landslide, earthquake, fire, drought)
- Full hydrodynamic flood modelling
- Photorealistic 3D Digital Twin (Unity/Unreal)
- Real-time IoT / streaming ingestion
- Drone integration, custom satellite infrastructure
- Reinforcement learning, multi-agent systems
- Nationwide monitoring
- Complex emergency-workflow engine
- Blockchain, or any auth system beyond optional Supabase Auth

## 3. System Diagram

```
Satellite / GIS Data
        ↓
AI Flood Detection  (Engineer 2)
        ↓
Flood Mask / Flood Polygon
        ↓
flood_predictions  (Supabase PostGIS)
        ↓
Digital Twin + Scenario Simulation  (Engineer 3)
        ↓
simulation_scenarios  (Supabase PostGIS)
        ↓
Risk Assessment + Response Planning + Routing  (Engineer 4)
        ↓
risk_zones, response_plans  (Supabase PostGIS)
        ↓
FastAPI Integration Layer  (Engineer 1)
        ↓
React Dashboard  (Engineer 5)
```

Large binary files (satellite rasters, DEM, flood masks, generated maps) never enter
this vector flow directly — they live in Supabase Storage, referenced by
`storage_path`/`mask_storage_path` columns in PostgreSQL. See `DATA_FORMATS.md` §2.

## 4. Engineer Ownership & Data Flow (locked)

| Engineer | Owns | Produces | Consumes |
|---|---|---|---|
| 1 | Backend architecture, Supabase/PostGIS setup, FastAPI, integration contracts | `regions`, storage buckets, API layer | Data written by Engineers 2–4, via shared contracts |
| 2 | AI flood detection | `flood_predictions` (flood mask + polygon) | `satellite_observations` |
| 3 | Digital Twin + flood scenario simulation | `simulation_scenarios` | `flood_predictions`, `population_zones`, `roads`, `critical_infrastructure` |
| 4 | Risk assessment, response planning, routing | `risk_zones`, `response_plans` | `simulation_scenarios` |
| 5 | React dashboard | UI only | FastAPI endpoints only |

Rules (do not violate without team sign-off):

1. Engineer 2 does **not** call the Digital Twin module directly — it writes to
   `flood_predictions` and Engineer 3 reads from there.
2. Engineer 3 consumes only through the shared database/contracts, never through
   ad-hoc calls into Engineer 2's code.
3. Engineer 4 consumes simulation outputs only through `simulation_scenarios`.
4. Engineer 5 (React) **never** computes flood risk or simulation results client-side.
   All numbers come from FastAPI.
5. No engineer redesigns a shared contract (table shape, endpoint shape, GeoJSON
   shape) unilaterally. Propose a change, document it, get it approved, then update
   all four docs together.

## 5. Digital Twin Definition (MVP)

DRISHTI's Digital Twin is a **lightweight 2D geospatial digital twin**, not a
simulation of physical reality. For Phase 1 it is simply a live read-view over
PostGIS data, rendered by the frontend map. It represents:

- Region boundary
- Roads
- Population zones
- Critical infrastructure (hospitals, schools, police, fire, relief centres, bridges)
- Flood extent (from `flood_predictions` / `simulation_scenarios.result_geometry`)
- Flood level / depth information
- Risk state (from `risk_zones`)

It is explicitly **not**:
- A photorealistic 3D city
- A real-time physical replica
- A full hydrodynamic flood model

`buildings` is an optional future layer (see `DATABASE_SCHEMA.md`).

## 6. Spatial Data Standard

See `DATA_FORMATS.md` §1 for the full, authoritative statement. Summary:

- **Database (PostGIS):** geometry columns, SRID 4326 (WGS84).
- **API (FastAPI ↔ React):** GeoJSON, WGS84 / EPSG:4326.
- **Raster processing (AI/GIS, in-memory or temporary files):** native or projected
  CRS may be used transiently; any resulting vector output **must** be reprojected to
  EPSG:4326 before it is written to PostGIS.

## 7. Technology Stack

| Layer | Choice |
|---|---|
| Frontend | React, Tailwind CSS, Leaflet/MapLibre |
| Backend | FastAPI (Python) |
| Database | Supabase PostgreSQL + PostGIS |
| File storage | Supabase Storage |
| AI | PyTorch, U-Net, NumPy, scikit-learn |
| GIS | GeoPandas, Rasterio, Shapely, PyProj |
| Routing | OSMnx, NetworkX |

No other database (MongoDB, Firebase, SQLite-as-project-db, local JSON/CSV) is
permitted. Local/runtime files are allowed **only** as temporary scratch space during
AI/GIS processing; the result is written to Supabase and the temp file is discarded.

## 8. Explicitly Rejected Complexity

Per the hackathon constraint, the following are **out of scope** and must not be
introduced without an explicit, team-approved architecture change:

Microservices · multiple databases · complex authentication systems · advanced
workflow/orchestration engines · full hydrodynamic modelling · complex 3D
visualization · real-time streaming infrastructure (unless a later phase proves it
necessary) · unnecessary tables/APIs/dependencies.

## 9. Open Assumptions Requiring Team Approval

1. `flood_predictions` links to `region_id` directly (not only via `flood_events`),
   since `flood_events` is optional for MVP. If `flood_events` is implemented, we add
   `flood_event_id` (nullable) to `flood_predictions` — schema already supports this
   without a breaking change (see `DATABASE_SCHEMA.md`).
2. Supabase Auth is not implemented in Phase 1. The dashboard is assumed to be
   unauthenticated for the demo. If judges/deployment require login, this needs an
   explicit decision before Phase 2.
3. One region is seeded manually for the MVP demo; multi-region support is assumed
   out of scope unless trivial.

