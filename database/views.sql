-- ============================================================================
-- DRISHTI — Read-Only GeoJSON Views (Phase 2 infrastructure helper)
-- ============================================================================
-- WHY THIS FILE EXISTS:
-- docs/API_CONTRACT.md requires all API geometry to be returned as GeoJSON
-- (docs/DATA_FORMATS.md §1). Supabase's REST layer (PostgREST) returns
-- PostGIS `geometry` columns as raw WKB by default, not GeoJSON. Rather than
-- changing any locked table (which would require team sign-off per
-- docs/ARCHITECTURE.md §4 rule 5), this file adds simple, additive,
-- READ-ONLY views that expose `ST_AsGeoJSON(geometry)` instead of the raw
-- column. No table in database/schema.sql is modified. INSERT/UPDATE
-- operations (e.g. creating a simulation scenario) still go directly against
-- the base tables — these views are for GET-style reads only.
--
-- Apply this AFTER database/schema.sql. Safe to re-run (CREATE OR REPLACE).
-- ============================================================================

create or replace view regions_geojson as
select
    id,
    name,
    state,
    country,
    ST_AsGeoJSON(geometry)::jsonb as geometry,
    created_at
from regions;

create or replace view simulation_scenarios_geojson as
select
    id,
    region_id,
    flood_prediction_id,
    scenario_name,
    flood_level,
    flooded_area,
    population_affected,
    buildings_affected,
    roads_affected_count,
    hospitals_affected,
    ST_AsGeoJSON(result_geometry)::jsonb as result_geometry,
    status,
    created_at
from simulation_scenarios;

create or replace view risk_zones_geojson as
select
    id,
    region_id,
    scenario_id,
    risk_score,
    risk_level,
    population_exposed,
    infrastructure_exposed,
    ST_AsGeoJSON(geometry)::jsonb as geometry,
    created_at
from risk_zones;
