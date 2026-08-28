export const RISK_WEIGHTS = {
  flood_severity: 0.30,
  population_exposure: 0.30,
  infrastructure_importance: 0.25,
  accessibility: 0.15,
};

export const RISK_CAPS = {
  flood_level_m: 5.0,
  population_affected: 50000,
  hospitals_affected: 5,
  critical_infra_affected: 10,
};

export const MAP_DEFAULTS = {
  centerAssam: [26.30, 92.32] as [number, number],
  centerOdisha: [20.46, 86.68] as [number, number],
  zoom: 12,
};

export const TILE_LAYERS = {
  cartoDark: {
    name: 'CartoDB Dark Matter',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
  },
  satellite: {
    name: 'ESRI World Imagery',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '&copy; <a href="https://www.esri.com/">Esri</a>',
  },
  osm: {
    name: 'OpenStreetMap',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>',
  },
};
