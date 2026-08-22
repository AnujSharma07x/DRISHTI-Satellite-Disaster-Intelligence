-- ============================================================================
-- DRISHTI — Phase 2 Database Schema
-- ============================================================================
-- Source of truth: docs/DATABASE_SCHEMA.md (Phase 1, Locked)
-- Implements ONLY the 9 MVP Core Tables. The two Optional/Future MVP
-- Extensions (`buildings`, `flood_events`) are NOT created here — see the
-- flagged note on `flood_predictions.flood_event_id` below.
--
-- HOW TO APPLY:
--   1. Open your Supabase project dashboard → SQL Editor.
--   2. Paste the contents of this file and run it (or run all statements via
--      `psql "$DATABASE_URL" -f database/schema.sql` if you have direct
--      Postgres access configured).
--   3. Re-running this file is safe: every statement uses IF NOT EXISTS /
--      OR REPLACE, so it will not error on a second run and will not drop
--      or overwrite existing data.
--
-- This file has NOT been executed against a live Supabase project by
-- Engineer 1 / this assistant — no Supabase credentials or supabase.co
-- network access were available in the working environment. See
-- backend/README.md "Manual Setup Checklist" for what a human must do by
-- hand in the Supabase dashboard.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extensions
-- ----------------------------------------------------------------------------
create extension if not exists postgis;
create extension if not exists pgcrypto; -- provides gen_random_uuid()

-- ----------------------------------------------------------------------------
-- 1. regions
-- ----------------------------------------------------------------------------
create table if not exists regions (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    state       text,
    country     text,
    geometry    geometry(Polygon, 4326) not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_regions_geometry on regions using gist (geometry);

-- ----------------------------------------------------------------------------
-- 2. satellite_observations
-- ----------------------------------------------------------------------------
create table if not exists satellite_observations (
    id                 uuid primary key default gen_random_uuid(),
    region_id          uuid not null references regions(id) on delete cascade,
    satellite          text not null,
    acquisition_date   date not null,
    observation_type   text not null check (observation_type in ('pre_flood', 'post_flood')),
    storage_path       text not null,
    processed          boolean not null default false,
    created_at         timestamptz not null default now()
);

create index if not exists idx_satellite_observations_region on satellite_observations(region_id);

-- ----------------------------------------------------------------------------
-- 3. flood_predictions
-- ----------------------------------------------------------------------------
-- FLAGGED NOTE (see backend/README.md "Known Deferrals"):
-- `flood_event_id` is included as a plain nullable uuid column, matching
-- docs/DATABASE_SCHEMA.md exactly in name/type/nullability. Its FK constraint
-- to `flood_events(id)` is deferred because `flood_events` is an Optional /
-- Future MVP Extension and is NOT created in this file. Add the constraint
-- with the ALTER TABLE statement at the bottom of this file once
-- `flood_events` is implemented — do not add a fake/placeholder table here.
create table if not exists flood_predictions (
    id                          uuid primary key default gen_random_uuid(),
    region_id                   uuid not null references regions(id) on delete cascade,
    flood_event_id              uuid, -- FK deferred, see note above
    satellite_observation_id    uuid references satellite_observations(id) on delete set null,
    model_version               text,
    confidence                  double precision check (confidence is null or (confidence >= 0.0 and confidence <= 1.0)),
    flood_area                  double precision, -- km²
    mask_storage_path           text,
    geometry                    geometry(MultiPolygon, 4326),
    status                      text not null default 'processing' check (status in ('processing', 'completed', 'failed')),
    created_at                  timestamptz not null default now()
);

create index if not exists idx_flood_predictions_region on flood_predictions(region_id);
create index if not exists idx_flood_predictions_satellite_obs on flood_predictions(satellite_observation_id);
create index if not exists idx_flood_predictions_geometry on flood_predictions using gist (geometry);
create index if not exists idx_flood_predictions_status on flood_predictions(status);

-- ----------------------------------------------------------------------------
-- 4. population_zones
-- ----------------------------------------------------------------------------
create table if not exists population_zones (
    id          uuid primary key default gen_random_uuid(),
    region_id   uuid not null references regions(id) on delete cascade,
    population  integer,
    density     double precision, -- people / km²
    geometry    geometry(Polygon, 4326) not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_population_zones_region on population_zones(region_id);
create index if not exists idx_population_zones_geometry on population_zones using gist (geometry);

-- ----------------------------------------------------------------------------
-- 5. critical_infrastructure
-- ----------------------------------------------------------------------------
-- All critical infrastructure (including bridges and other non-point
-- features) uses a representative Point geometry, per the locked spatial
-- standard in docs/DATA_FORMATS.md §1. No other geometry type is used here.
create table if not exists critical_infrastructure (
    id          uuid primary key default gen_random_uuid(),
    region_id   uuid not null references regions(id) on delete cascade,
    name        text not null,
    type        text not null check (type in ('hospital', 'school', 'police_station', 'fire_station', 'relief_centre', 'bridge')),
    importance  integer, -- relative priority weight
    geometry    geometry(Point, 4326) not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_critical_infra_region on critical_infrastructure(region_id);
create index if not exists idx_critical_infra_type on critical_infrastructure(type);
create index if not exists idx_critical_infra_geometry on critical_infrastructure using gist (geometry);

-- ----------------------------------------------------------------------------
-- 6. roads
-- ----------------------------------------------------------------------------
create table if not exists roads (
    id          uuid primary key default gen_random_uuid(),
    region_id   uuid not null references regions(id) on delete cascade,
    road_name   text,
    road_type   text,
    importance  integer,
    geometry    geometry(LineString, 4326) not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_roads_region on roads(region_id);
create index if not exists idx_roads_geometry on roads using gist (geometry);

-- ----------------------------------------------------------------------------
-- 7. simulation_scenarios
-- ----------------------------------------------------------------------------
create table if not exists simulation_scenarios (
    id                      uuid primary key default gen_random_uuid(),
    region_id               uuid not null references regions(id) on delete cascade,
    flood_prediction_id     uuid references flood_predictions(id) on delete set null,
    scenario_name           text,
    flood_level             double precision not null, -- metres
    flooded_area            double precision, -- km²
    population_affected     integer,
    buildings_affected      integer, -- null unless the optional `buildings` table is adopted
    roads_affected_count    integer, -- ALWAYS a count of road segments, never a length — see docs/DATA_FORMATS.md §3
    hospitals_affected      integer,
    result_geometry         geometry(MultiPolygon, 4326),
    status                  text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
    created_at              timestamptz not null default now()
);

create index if not exists idx_simulation_scenarios_region on simulation_scenarios(region_id);
create index if not exists idx_simulation_scenarios_flood_pred on simulation_scenarios(flood_prediction_id);
create index if not exists idx_simulation_scenarios_geometry on simulation_scenarios using gist (result_geometry);
create index if not exists idx_simulation_scenarios_status on simulation_scenarios(status);

-- ----------------------------------------------------------------------------
-- 8. risk_zones
-- ----------------------------------------------------------------------------
create table if not exists risk_zones (
    id                       uuid primary key default gen_random_uuid(),
    region_id                uuid not null references regions(id) on delete cascade,
    scenario_id              uuid references simulation_scenarios(id) on delete cascade,
    risk_score               double precision check (risk_score is null or (risk_score >= 0.0 and risk_score <= 1.0)),
    risk_level               text check (risk_level in ('LOW', 'MODERATE', 'HIGH', 'VERY_HIGH', 'CRITICAL')),
    population_exposed       integer,
    infrastructure_exposed   integer,
    geometry                 geometry(Polygon, 4326) not null,
    created_at               timestamptz not null default now()
);

create index if not exists idx_risk_zones_region on risk_zones(region_id);
create index if not exists idx_risk_zones_scenario on risk_zones(scenario_id);
create index if not exists idx_risk_zones_geometry on risk_zones using gist (geometry);
create index if not exists idx_risk_zones_level on risk_zones(risk_level);

-- ----------------------------------------------------------------------------
-- 9. response_plans
-- ----------------------------------------------------------------------------
create table if not exists response_plans (
    id                          uuid primary key default gen_random_uuid(),
    scenario_id                 uuid not null references simulation_scenarios(id) on delete cascade,
    priority_zone_id            uuid not null references risk_zones(id) on delete cascade,
    recommended_facility_id     uuid references critical_infrastructure(id) on delete set null,
    route_geometry              geometry(LineString, 4326),
    estimated_distance_km       double precision,
    estimated_time_minutes      double precision,
    created_at                  timestamptz not null default now()
);

create index if not exists idx_response_plans_scenario on response_plans(scenario_id);
create index if not exists idx_response_plans_priority_zone on response_plans(priority_zone_id);
create index if not exists idx_response_plans_geometry on response_plans using gist (route_geometry);

-- ============================================================================
-- DEFERRED — apply ONLY after the optional `flood_events` table (see
-- docs/DATABASE_SCHEMA.md "Optional / Future MVP Extensions") has been
-- created. Do not run this yet; it will fail with no such table.
-- ============================================================================
-- alter table flood_predictions
--     add constraint fk_flood_predictions_flood_event
--     foreign key (flood_event_id) references flood_events(id) on delete set null;

-- ============================================================================
-- End of Phase 2 MVP core schema. Optional/future tables (`buildings`,
-- `flood_events`) are intentionally NOT included — see docs/DATABASE_SCHEMA.md
-- for their definitions when/if the team decides to adopt them.
-- ============================================================================
