import { GeoJSONInput, Position } from '../types/geojson';
import L from 'leaflet';

/**
 * Extracts all coordinates from any arbitrary GeoJSON object
 * (Geometry, Feature, or FeatureCollection).
 */
export function extractCoordinates(geojson: GeoJSONInput | null | undefined): Position[] {
  if (!geojson) return [];
  const coords: Position[] = [];

  const traverse = (obj: any) => {
    if (!obj) return;
    if (obj.type === 'FeatureCollection' && Array.isArray(obj.features)) {
      obj.features.forEach(traverse);
    } else if (obj.type === 'Feature' && obj.geometry) {
      traverse(obj.geometry);
    } else if (obj.coordinates) {
      const flatten = (arr: any) => {
        if (
          Array.isArray(arr) &&
          arr.length >= 2 &&
          typeof arr[0] === 'number' &&
          typeof arr[1] === 'number'
        ) {
          coords.push([arr[0], arr[1]]);
        } else if (Array.isArray(arr)) {
          arr.forEach(flatten);
        }
      };
      flatten(obj.coordinates);
    }
  };

  traverse(geojson);
  return coords;
}

/**
 * Computes Leaflet LatLngBounds from any GeoJSON object.
 */
export function getBoundsFromGeoJSON(geojson: GeoJSONInput | null | undefined): L.LatLngBounds | null {
  const coords = extractCoordinates(geojson);
  if (coords.length === 0) return null;

  let minLat = Infinity,
    maxLat = -Infinity,
    minLng = Infinity,
    maxLng = -Infinity;

  for (const [lng, lat] of coords) {
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
  }

  if (!isFinite(minLat) || !isFinite(minLng)) return null;
  return L.latLngBounds([minLat, minLng], [maxLat, maxLng]);
}

/**
 * Calculates a simple mathematical centroid from GeoJSON coordinates.
 * Returns [latitude, longitude] for Leaflet map views.
 */
export function getCentroidFromGeoJSON(geojson: GeoJSONInput | null | undefined): [number, number] | null {
  const coords = extractCoordinates(geojson);
  if (coords.length === 0) return null;

  let sumLat = 0;
  let sumLng = 0;

  for (const [lng, lat] of coords) {
    sumLng += lng;
    sumLat += lat;
  }

  return [sumLat / coords.length, sumLng / coords.length];
}

/**
 * Normalizes any GeoJSON input into a clean object ready for Leaflet GeoJSON layer.
 */
export function normalizeGeoJSON(input: any): any {
  if (!input) return null;
  if (typeof input === 'string') {
    try {
      input = JSON.parse(input);
    } catch {
      return null;
    }
  }

  // If it's a bare geometry, wrap in Feature for maximum Leaflet compatibility
  if (input.type && input.type !== 'Feature' && input.type !== 'FeatureCollection' && input.coordinates) {
    return {
      type: 'Feature',
      properties: {},
      geometry: input,
    };
  }

  return input;
}
