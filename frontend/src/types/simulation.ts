import { GeoJSONGeometry } from './geojson';

export interface SimulationRequest {
  region_id: string;
  flood_level: number; // in meters (>= 0)
}

export type SimulationStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface SimulationResponse {
  scenario_id: string;
  region_id: string;
  flood_level: number;
  status: SimulationStatus;
  flooded_area?: number | null; // km²
  population_affected?: number | null;
  buildings_affected?: number | null;
  roads_affected_count?: number | null; // Always segment count, never km
  hospitals_affected?: number | null;
  result_geometry?: GeoJSONGeometry | null;
  created_at?: string;
}
