import { MultiPolygonGeometry } from './geojson';

export interface FloodPredictionData {
  region_id: string;
  flood_event_id?: string | null;
  satellite_observation_id?: string | null;
  model_version: string;
  confidence: number;
  flood_area: number; // km²
  mask_storage_path?: string | null;
  geometry: MultiPolygonGeometry | null;
  status: 'processing' | 'completed' | 'failed';
}

export interface InferenceMetadata {
  is_calibrated_probability: boolean;
  valid_pixels: number;
  total_pixels: number;
  flooded_pixels: number;
  drop_threshold_db?: number | null;
  probability_threshold: number;
  demo_mode: boolean;
}

export interface ImpactSummaryStats {
  flooded_area_km2: number;
  population_affected: number;
  buildings_affected?: number | null;
  roads_affected_count: number;
  hospitals_affected: number;
  critical_infra_affected?: number;
}
