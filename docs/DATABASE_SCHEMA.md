# DRISHTI — Database Schema (Phase 1, Locked)

Database: Supabase PostgreSQL + PostGIS. This is the source of truth for column
names, types, and relationships. Do not rename or restructure without updating this
file and the other three Phase 1 docs together.

Conventions used throughout:
- All primary keys: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- All geometry columns: PostGIS `geometry(<TYPE>, 4326)` — see `DATA_FORMATS.md` §1
- All `created_at` columns: `TIMESTAMPTZ DEFAULT now()`
- Foreign keys are nullable only where explicitly noted

---

## MVP Core Tables (implement first)

### 1. `regions`
Study-area boundary. Root of the data flow.

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| name | text | |
| state | text | |
| country | text | |
| geometry | geometry(Polygon, 4326) | region boundary |
| created_at | timestamptz | |

### 2. `satellite_observations`
Metadata for satellite imagery. Raw imagery lives in Supabase Storage
(`satellite/` bucket); this table stores the pointer.

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| satellite | text | e.g. `Sentinel-1` |
| acquisition_date | date | |
| observation_type | text | `pre_flood` \| `post_flood` |
| storage_path | text | path in Supabase Storage |
| processed | boolean | default false |
| created_at | timestamptz | |

### 3. `flood_predictions`
AI-generated flood detection result (Engineer 2's output). Owns the flood polygon
used everywhere downstream.

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| flood_event_id | uuid | FK → flood_events.id, **nullable** (optional table, see below) |
| satellite_observation_id | uuid | FK → satellite_observations.id, nullable |
| model_version | text | |
| confidence | float | 0.0–1.0 |
| flood_area | float | km² |
| mask_storage_path | text | raster mask in Supabase Storage (`flood-masks/`) |
| geometry | geometry(MultiPolygon, 4326) | flood polygon, reprojected to EPSG:4326 |
| status | text | `processing` \| `completed` \| `failed` — default `processing` |
| created_at | timestamptz | |

### 4. `population_zones`
| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| population | integer | |
| density | float | people / km² |
| geometry | geometry(Polygon, 4326) | |
| created_at | timestamptz | |

### 5. `critical_infrastructure`
Hospitals, schools, police, fire stations, relief centres, bridges, etc.

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| name | text | |
| type | text | `hospital` \| `school` \| `police_station` \| `fire_station` \| `relief_centre` \| `bridge` \| ... |
| importance | integer | relative priority weight |
| geometry | geometry(Point, 4326) | |
| created_at | timestamptz | |

> For MVP consistency, all critical infrastructure entities, including linear or
> area-based infrastructure such as bridges, are represented using a representative
> Point geometry in EPSG:4326. No other geometry type is used for this table.

### 6. `roads`
| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| road_name | text | |
| road_type | text | |
| importance | integer | |
| geometry | geometry(LineString, 4326) | |
| created_at | timestamptz | |

### 7. `simulation_scenarios`
Digital Twin "what-if" flood-level simulation (Engineer 3's output).

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| flood_prediction_id | uuid | FK → flood_predictions.id, nullable (baseline this scenario extends, if any) |
| scenario_name | text | |
| flood_level | float | metres |
| flooded_area | float | km² |
| population_affected | integer | |
| buildings_affected | integer | nullable — only populated if `buildings` table is in use |
| roads_affected_count | integer | number of road segments/features intersected by the flood extent — always a count, never a length, see `DATA_FORMATS.md` §3 |
| hospitals_affected | integer | |
| result_geometry | geometry(MultiPolygon, 4326) | simulated flood extent |
| status | text | `pending` \| `running` \| `completed` \| `failed` — default `pending` |
| created_at | timestamptz | |

> **Future extension (not part of MVP):** `affected_road_length_km FLOAT` — total
> length, in kilometres, of affected road segments. Add only if a real need arises;
> it must never replace or be confused with `roads_affected_count`, which always
> stays a count.

### 8. `risk_zones`
Risk engine output (Engineer 4).

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| scenario_id | uuid | FK → simulation_scenarios.id, nullable |
| risk_score | float | 0.0–1.0 |
| risk_level | text | `LOW` \| `MODERATE` \| `HIGH` \| `VERY_HIGH` \| `CRITICAL` |
| population_exposed | integer | |
| infrastructure_exposed | integer | count of critical_infrastructure records intersected |
| geometry | geometry(Polygon, 4326) | |
| created_at | timestamptz | |

### 9. `response_plans`
Kept intentionally lightweight for MVP (Fix 5). No workflow-engine fields.

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| scenario_id | uuid | FK → simulation_scenarios.id |
| priority_zone_id | uuid | FK → risk_zones.id |
| recommended_facility_id | uuid | FK → critical_infrastructure.id |
| route_geometry | geometry(LineString, 4326) | |
| estimated_distance_km | float | |
| estimated_time_minutes | float | |
| created_at | timestamptz | |

---

## Optional / Future MVP Extensions

These tables are **not required** for the first end-to-end demo. Keep their
definitions documented so Engineer 2–4 can adopt them later without a schema
redesign, but do not block Phase 1 implementation on them.

### `buildings` (optional)
| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| building_type | text | |
| importance | integer | |
| geometry | geometry(Polygon, 4326) | |
| created_at | timestamptz | |

### `flood_events` (optional)
Groups one or more `flood_predictions` under a named real-world event. If adopted,
`flood_predictions.flood_event_id` becomes populated; until then it stays null.

| column | type | notes |
|---|---|---|
| id | uuid | PK |
| region_id | uuid | FK → regions.id |
| event_name | text | |
| start_date | date | |
| end_date | date | nullable |
| severity | text | |
| source | text | |
| geometry | geometry(Polygon, 4326) | |
| created_at | timestamptz | |

---

## Simplified MVP Data Flow

```
regions
   ↓
satellite_observations
   ↓
flood_predictions
   ↓
simulation_scenarios
   ↓
risk_zones
   ↓
response_plans
```

`population_zones`, `roads`, and `critical_infrastructure` are static reference
layers loaded once per region and joined into the flow via `region_id` (impact
calculations use `ST_Intersects`, see `DATA_FORMATS.md` §3) — they are not a
sequential step but shared inputs to `simulation_scenarios` and `risk_zones`.

## Status Fields (Fix 6)

| table | column | values | default |
|---|---|---|---|
| flood_predictions | status | `processing`, `completed`, `failed` | `processing` |
| simulation_scenarios | status | `pending`, `running`, `completed`, `failed` | `pending` |

These values are also used in `API_CONTRACT.md` responses and `DATA_FORMATS.md`
object definitions — keep all three in sync.

