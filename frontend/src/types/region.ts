import { GeoJSONGeometry } from './geojson';

export interface Region {
  id: string;
  name: string;
  state?: string | null;
  country?: string | null;
  geometry: GeoJSONGeometry;
  created_at?: string;
}

export interface RegionsResponse {
  regions: Region[];
}
