export type Position = [number, number]; // [longitude, latitude]

export interface GeoJSONGeometry {
  type: string;
  coordinates: any;
}

export interface PolygonGeometry extends GeoJSONGeometry {
  type: 'Polygon';
  coordinates: Position[][];
}

export interface MultiPolygonGeometry extends GeoJSONGeometry {
  type: 'MultiPolygon';
  coordinates: Position[][][];
}

export interface LineStringGeometry extends GeoJSONGeometry {
  type: 'LineString';
  coordinates: Position[];
}

export interface PointGeometry extends GeoJSONGeometry {
  type: 'Point';
  coordinates: Position;
}

export interface GeoJSONFeature<G = GeoJSONGeometry, P = Record<string, any>> {
  type: 'Feature';
  geometry: G;
  properties: P;
  id?: string | number;
}

export interface GeoJSONFeatureCollection<G = GeoJSONGeometry, P = Record<string, any>> {
  type: 'FeatureCollection';
  features: GeoJSONFeature<G, P>[];
  crs?: {
    type: string;
    properties: {
      name: string;
    };
  };
}

export type GeoJSONInput = GeoJSONGeometry | GeoJSONFeature | GeoJSONFeatureCollection;
