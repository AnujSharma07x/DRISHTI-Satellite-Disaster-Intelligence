import { LineStringGeometry, PointGeometry } from './geojson';
import { NormalizedRiskLevel } from './risk';

export interface EmergencyFacility {
  id: string;
  name: string;
  type: 'hospital' | 'school' | 'police_station' | 'fire_station' | 'relief_centre' | 'bridge' | string;
  importance?: number;
  geometry: PointGeometry;
  latitude?: number;
  longitude?: number;
  is_accessible?: boolean;
}

export interface EvacuationRoute {
  scenario_id?: string;
  priority_zone_id?: string;
  risk_score?: number;
  risk_level?: NormalizedRiskLevel;
  recommended_facility_id?: string | null;
  recommended_facility_name?: string | null;
  recommended_facility_type?: string;
  route_geometry: LineStringGeometry | Record<string, never>;
  estimated_distance_km?: number | null;
  estimated_time_minutes?: number | null;
  used_flooded_road: boolean;
  note?: string | null;
}
