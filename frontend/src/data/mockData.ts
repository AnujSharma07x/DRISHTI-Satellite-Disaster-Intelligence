import { Region } from '../types/region';
import { SimulationResponse } from '../types/simulation';
import { RiskZone } from '../types/risk';
import { EmergencyFacility, EvacuationRoute } from '../types/routing';
import { FloodPredictionData, InferenceMetadata } from '../types/telemetry';

// ============================================================================
// VERIFIED REPOSITORY REGIONS
// ============================================================================

export const MOCK_REGIONS: Region[] = [
  {
    id: 'morigaon-assam-001',
    name: 'Morigaon Study Area',
    state: 'Assam',
    country: 'India',
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [92.15, 26.15],
          [92.50, 26.15],
          [92.50, 26.45],
          [92.15, 26.45],
          [92.15, 26.15],
        ],
      ],
    },
    created_at: '2026-06-05T00:00:00Z',
  },
  {
    id: 'kendrapara-odisha-002',
    name: 'Mahanadi Basin (AI Sentinel-1 Scene)',
    state: 'Odisha',
    country: 'India',
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [86.66, 20.44],
          [86.70, 20.44],
          [86.70, 20.48],
          [86.66, 20.48],
          [86.66, 20.44],
        ],
      ],
    },
    created_at: '2026-08-22T00:00:00Z',
  },
];

// ============================================================================
// AI FLOOD DETECTION OUTPUTS (from ai/sample_output/ and data/mock/)
// ============================================================================

export const MOCK_AI_PREDICTION_ODISHA: FloodPredictionData = {
  region_id: 'kendrapara-odisha-002',
  flood_event_id: null,
  satellite_observation_id: null,
  model_version: 'sar_change_threshold_baseline_v1',
  confidence: 0.9953,
  flood_area: 0.6895,
  mask_storage_path: 'flood-masks/demo-region-001/flood_mask.tif',
  status: 'completed',
  geometry: {
    type: 'MultiPolygon',
    coordinates: [
      [
        [
          [86.682624, 20.468419],
          [86.682624, 20.468328],
          [86.681953, 20.468327],
          [86.681953, 20.468237],
          [86.681665, 20.468236],
          [86.681665, 20.468146],
          [86.681378, 20.468145],
          [86.681378, 20.468055],
          [86.681091, 20.467874],
          [86.680899, 20.467783],
          [86.680612, 20.467511],
          [86.680325, 20.467240],
          [86.680038, 20.466968],
          [86.679751, 20.466516],
          [86.679465, 20.465973],
          [86.679178, 20.465250],
          [86.678894, 20.463442],
          [86.678897, 20.462267],
          [86.679187, 20.461274],
          [86.679476, 20.460551],
          [86.679764, 20.460100],
          [86.680149, 20.459649],
          [86.680533, 20.459288],
          [86.680917, 20.458928],
          [86.681397, 20.458657],
          [86.681973, 20.458478],
          [86.682644, 20.458389],
          [86.683411, 20.458480],
          [86.684082, 20.458753],
          [86.684656, 20.459115],
          [86.685230, 20.459658],
          [86.685708, 20.460292],
          [86.686090, 20.461015],
          [86.686376, 20.461829],
          [86.686469, 20.463365],
          [86.686274, 20.465263],
          [86.685792, 20.466256],
          [86.685215, 20.467068],
          [86.684639, 20.467609],
          [86.683967, 20.468060],
          [86.683391, 20.468330],
          [86.682624, 20.468419],
        ],
      ],
    ],
  },
};

export const MOCK_INFERENCE_METADATA_ODISHA: InferenceMetadata = {
  is_calibrated_probability: false,
  valid_pixels: 37000,
  total_pixels: 40000,
  flooded_pixels: 6890,
  drop_threshold_db: 3.0,
  probability_threshold: 0.5,
  demo_mode: true,
};

export const MOCK_FLOOD_POLYGON_ASSAM = {
  type: 'MultiPolygon',
  coordinates: [
    [
      [
        [92.24, 26.24],
        [92.32, 26.24],
        [92.32, 26.29],
        [92.27, 26.31],
        [92.24, 26.29],
        [92.24, 26.24],
      ],
    ],
    [
      [
        [92.36, 26.32],
        [92.41, 26.32],
        [92.41, 26.36],
        [92.36, 26.36],
        [92.36, 26.32],
      ],
    ],
  ],
};

export const MOCK_AI_PREDICTION_ASSAM: FloodPredictionData = {
  region_id: 'morigaon-assam-001',
  flood_event_id: 'demo-flood-001',
  model_version: 'demo-unet-v1',
  confidence: 0.91,
  flood_area: 42.3,
  mask_storage_path: 'flood-events/demo-flood-001/flood_mask.tif',
  status: 'completed',
  geometry: MOCK_FLOOD_POLYGON_ASSAM as any,
};

export const MOCK_INFERENCE_METADATA_ASSAM: InferenceMetadata = {
  is_calibrated_probability: true,
  valid_pixels: 512000,
  total_pixels: 512000,
  flooded_pixels: 94200,
  drop_threshold_db: 3.0,
  probability_threshold: 0.5,
  demo_mode: true,
};

// ============================================================================
// VERIFIED RISK ZONES (from data/mock/sample_risk_zones.geojson)
// ============================================================================

export const MOCK_RISK_ZONES: RiskZone[] = [
  {
    id: 'zone-001',
    region_id: 'morigaon-assam-001',
    scenario_id: 'scenario-3.0m',
    risk_score: 0.87,
    risk_level: 'CRITICAL',
    population_exposed: 12500,
    infrastructure_exposed: 6,
    primary_reason: 'High population exposure & low-lying riverbank',
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [92.24, 26.24],
          [92.29, 26.24],
          [92.29, 26.28],
          [92.24, 26.28],
          [92.24, 26.24],
        ],
      ],
    },
    created_at: '2026-06-05T00:00:00Z',
  },
  {
    id: 'zone-002',
    region_id: 'morigaon-assam-001',
    scenario_id: 'scenario-3.0m',
    risk_score: 0.55,
    risk_level: 'MODERATE', // Normalized from "MEDIUM" in raw JSON
    population_exposed: 4800,
    infrastructure_exposed: 3,
    primary_reason: 'Moderate infrastructure exposure near bridge',
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [92.36, 26.32],
          [92.41, 26.32],
          [92.41, 26.36],
          [92.36, 26.36],
          [92.36, 26.32],
        ],
      ],
    },
    created_at: '2026-06-05T00:00:00Z',
  },
  {
    id: 'zone-003',
    region_id: 'morigaon-assam-001',
    scenario_id: 'scenario-3.0m',
    risk_score: 0.22,
    risk_level: 'LOW',
    population_exposed: 1200,
    infrastructure_exposed: 1,
    primary_reason: 'Elevated topography, minimal flood impact',
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [92.30, 26.36],
          [92.35, 26.36],
          [92.35, 26.39],
          [92.30, 26.39],
          [92.30, 26.36],
        ],
      ],
    },
    created_at: '2026-06-05T00:00:00Z',
  },
];

// ============================================================================
// VERIFIED SIMULATION SCENARIOS (from data/mock/sample_simulation.json)
// ============================================================================

export const MOCK_SIMULATION_SCENARIOS: Record<number, SimulationResponse> = {
  2.5: {
    scenario_id: 'scenario-2.5m',
    region_id: 'morigaon-assam-001',
    flood_level: 2.5,
    status: 'completed',
    flooded_area: 28.5,
    population_affected: 9000,
    buildings_affected: 2100,
    roads_affected_count: 18,
    hospitals_affected: 1,
    result_geometry: {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [92.25, 26.25],
            [92.30, 26.25],
            [92.30, 26.28],
            [92.25, 26.28],
            [92.25, 26.25],
          ],
        ],
      ],
    },
    created_at: '2026-06-05T00:00:00Z',
  },
  3.0: {
    scenario_id: 'scenario-3.0m',
    region_id: 'morigaon-assam-001',
    flood_level: 3.0,
    status: 'completed',
    flooded_area: 42.3,
    population_affected: 12500,
    buildings_affected: 3200,
    roads_affected_count: 31,
    hospitals_affected: 3,
    result_geometry: MOCK_FLOOD_POLYGON_ASSAM as any,
    created_at: '2026-06-05T00:00:00Z',
  },
  3.5: {
    scenario_id: 'scenario-3.5m',
    region_id: 'morigaon-assam-001',
    flood_level: 3.5,
    status: 'completed',
    flooded_area: 58.7,
    population_affected: 18000,
    buildings_affected: 4600,
    roads_affected_count: 45,
    hospitals_affected: 5,
    result_geometry: {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [92.23, 26.23],
            [92.34, 26.23],
            [92.34, 26.31],
            [92.26, 26.33],
            [92.23, 26.31],
            [92.23, 26.23],
          ],
        ],
        [
          [
            [92.35, 26.31],
            [92.43, 26.31],
            [92.43, 26.38],
            [92.35, 26.38],
            [92.35, 26.31],
          ],
        ],
      ],
    },
    created_at: '2026-06-05T00:00:00Z',
  },
};

// ============================================================================
// CRITICAL INFRASTRUCTURE (Hospitals, Police, Relief, Fire)
// ============================================================================

export const MOCK_FACILITIES: EmergencyFacility[] = [
  {
    id: 'fac-hosp-01',
    name: 'District Civil Hospital Morigaon',
    type: 'hospital',
    importance: 10,
    latitude: 26.26,
    longitude: 92.34,
    is_accessible: true,
    geometry: { type: 'Point', coordinates: [92.34, 26.26] },
  },
  {
    id: 'fac-relief-01',
    name: 'Morigaon Higher Secondary Relief Camp',
    type: 'relief_centre',
    importance: 8,
    latitude: 26.35,
    longitude: 92.35,
    is_accessible: true,
    geometry: { type: 'Point', coordinates: [92.35, 26.35] },
  },
  {
    id: 'fac-fire-01',
    name: 'Central Fire & Emergency Station',
    type: 'fire_station',
    importance: 7,
    latitude: 26.22,
    longitude: 92.28,
    is_accessible: false, // Flooded
    geometry: { type: 'Point', coordinates: [92.28, 26.22] },
  },
  {
    id: 'fac-police-01',
    name: 'District Police Headquarters',
    type: 'police_station',
    importance: 6,
    latitude: 26.30,
    longitude: 92.30,
    is_accessible: true,
    geometry: { type: 'Point', coordinates: [92.30, 26.30] },
  },
];

// ============================================================================
// VERIFIED EVACUATION ROUTE (from data/mock/sample_route.geojson)
// ============================================================================

export const MOCK_EVACUATION_ROUTE: EvacuationRoute = {
  scenario_id: 'scenario-3.0m',
  priority_zone_id: 'zone-001',
  risk_score: 87,
  risk_level: 'CRITICAL',
  recommended_facility_id: 'fac-relief-01',
  recommended_facility_name: 'Morigaon Higher Secondary Relief Camp',
  recommended_facility_type: 'relief_centre',
  route_geometry: {
    type: 'LineString',
    coordinates: [
      [92.30, 26.20],
      [92.32, 26.24],
      [92.34, 26.28],
      [92.35, 26.32],
      [92.35, 26.35],
    ],
  },
  estimated_distance_km: 8.4,
  estimated_time_minutes: 18.5,
  used_flooded_road: false,
  note: 'Safe elevated evacuation corridor active. Avoid southern riverbank detour.',
};
