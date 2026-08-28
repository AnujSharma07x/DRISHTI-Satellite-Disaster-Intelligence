import { GeoJSONGeometry } from './geojson';

export type NormalizedRiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH' | 'CRITICAL';

export interface RiskZone {
  id: string;
  region_id: string;
  scenario_id?: string | null;
  risk_score?: number | null; // 0.0 - 1.0 (or 0 - 100)
  risk_level?: string | null; // e.g. "LOW", "MODERATE", "MEDIUM", "HIGH", "VERY HIGH", "VERY_HIGH", "CRITICAL"
  population_exposed?: number | null;
  infrastructure_exposed?: number | null;
  geometry: GeoJSONGeometry;
  created_at?: string;
  primary_reason?: string;
}

export interface RiskZonesResponse {
  risk_zones: RiskZone[];
}

export interface RiskScoreBreakdown {
  flood_severity_score: number;       // 0 - 100 (30% weight)
  population_exposure_score: number;   // 0 - 100 (30% weight)
  infrastructure_importance_score: number; // 0 - 100 (25% weight)
  accessibility_score: number;        // 0 - 100 (15% weight)
  accessibility_fallback_used?: boolean;
  total_score: number;                // 0 - 100
  normalized_level: NormalizedRiskLevel;
}

export interface PriorityZone {
  rank: number;
  zone_id: string;
  zone_name: string;
  scenario_id?: string;
  risk_level: NormalizedRiskLevel;
  risk_score: number;
  flood_level: number;
  population_affected: number;
  hospitals_affected: number;
  roads_affected_count?: number;
  roads_affected_km?: number;
  accessibility_score?: number;
  geometry?: GeoJSONGeometry | null;
}
