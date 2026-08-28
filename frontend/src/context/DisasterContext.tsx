import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Region } from '../types/region';
import { SimulationResponse } from '../types/simulation';
import { RiskZone, PriorityZone } from '../types/risk';
import { EmergencyFacility, EvacuationRoute } from '../types/routing';
import { FloodPredictionData, InferenceMetadata } from '../types/telemetry';
import {
  MOCK_REGIONS,
  MOCK_AI_PREDICTION_ASSAM,
  MOCK_INFERENCE_METADATA_ASSAM,
  MOCK_AI_PREDICTION_ODISHA,
  MOCK_INFERENCE_METADATA_ODISHA,
  MOCK_RISK_ZONES,
  MOCK_SIMULATION_SCENARIOS,
  MOCK_FACILITIES,
  MOCK_EVACUATION_ROUTE,
} from '../data/mockData';
import { checkHealth } from '../api/healthApi';
import { fetchRegions } from '../api/regionsApi';
import { createSimulation, getSimulation } from '../api/simulationApi';
import { fetchRiskZones } from '../api/riskApi';
import { normalizeRiskLevel } from '../utils/riskNormalizer';
import { TILE_LAYERS } from '../data/constants';

export interface LayerVisibility {
  regionBoundary: boolean;
  floodPolygon: boolean;
  simulationPolygon: boolean;
  riskZones: boolean;
  infrastructure: boolean;
  evacuationRoute: boolean;
}

interface DisasterContextType {
  // Operational Mode
  isLiveMode: boolean;
  isBackendHealthy: boolean;
  setLiveMode: (enabled: boolean) => void;
  isLoading: boolean;
  error: string | null;

  // Region & Scenarios
  regions: Region[];
  selectedRegion: Region | null;
  setSelectedRegionId: (regionId: string) => void;

  // AI Satellite Flood Detection
  floodPrediction: FloodPredictionData | null;
  inferenceMetadata: InferenceMetadata | null;

  // Simulation & What-If
  activeScenario: SimulationResponse | null;
  isSimulating: boolean;
  runScenarioSimulation: (floodLevel: number) => Promise<void>;

  // Risk Assessment
  riskZones: RiskZone[];
  priorityZones: PriorityZone[];
  selectedZoneId: string | null;
  setSelectedZoneId: (zoneId: string | null) => void;

  // Emergency Response & Facilities
  facilities: EmergencyFacility[];
  activeRoute: EvacuationRoute | null;

  // Map Controls
  visibleLayers: LayerVisibility;
  toggleLayer: (layerKey: keyof LayerVisibility) => void;
  tileLayer: keyof typeof TILE_LAYERS;
  setTileLayer: (tileKey: keyof typeof TILE_LAYERS) => void;

  // Actions
  refreshData: () => Promise<void>;
}

const DisasterContext = createContext<DisasterContextType | undefined>(undefined);

export const DisasterProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Mode state
  const [isLiveMode, setIsLiveMode] = useState<boolean>(false);
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Entities
  const [regions, setRegions] = useState<Region[]>(MOCK_REGIONS);
  const [selectedRegion, setSelectedRegion] = useState<Region | null>(MOCK_REGIONS[0]);
  const [floodPrediction, setFloodPrediction] = useState<FloodPredictionData | null>(MOCK_AI_PREDICTION_ASSAM);
  const [inferenceMetadata, setInferenceMetadata] = useState<InferenceMetadata | null>(MOCK_INFERENCE_METADATA_ASSAM);
  const [activeScenario, setActiveScenario] = useState<SimulationResponse | null>(MOCK_SIMULATION_SCENARIOS[3.0]);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  // Risk & Routing
  const [riskZones, setRiskZones] = useState<RiskZone[]>(MOCK_RISK_ZONES);
  const [priorityZones, setPriorityZones] = useState<PriorityZone[]>([]);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>('zone-001');
  const [facilities, setFacilities] = useState<EmergencyFacility[]>(MOCK_FACILITIES);
  const [activeRoute, setActiveRoute] = useState<EvacuationRoute | null>(MOCK_EVACUATION_ROUTE);

  // Map Controls
  const [visibleLayers, setVisibleLayers] = useState<LayerVisibility>({
    regionBoundary: true,
    floodPolygon: true,
    simulationPolygon: true,
    riskZones: true,
    infrastructure: true,
    evacuationRoute: true,
  });
 const [tileLayer, setTileLayer] = useState<keyof typeof TILE_LAYERS>('osm');
  // Compute Priority Zones from Risk Zones
  useEffect(() => {
    const computed: PriorityZone[] = riskZones.map((z, index) => {
      const normalized = normalizeRiskLevel(z.risk_level);
      const score = typeof z.risk_score === 'number' ? (z.risk_score <= 1.0 ? z.risk_score * 100 : z.risk_score) : 50;
      return {
        rank: index + 1,
        zone_id: z.id,
        zone_name: z.primary_reason ? `Zone ${z.id} (${z.primary_reason})` : `Priority Sector ${z.id}`,
        scenario_id: z.scenario_id || undefined,
        risk_level: normalized,
        risk_score: Math.round(score),
        flood_level: activeScenario?.flood_level || 3.0,
        population_affected: z.population_exposed || 5000,
        hospitals_affected: z.infrastructure_exposed ? Math.min(3, Math.floor(z.infrastructure_exposed / 2)) : 1,
        roads_affected_count: Math.round((z.population_exposed || 5000) / 400),
        geometry: z.geometry,
      };
    });

    computed.sort((a, b) => b.risk_score - a.risk_score);
    computed.forEach((item, idx) => {
      item.rank = idx + 1;
    });

    setPriorityZones(computed);
  }, [riskZones, activeScenario]);

  // Initial startup: check backend health and set appropriate mode
  const initialize = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const isHealthy = await checkHealth();
      setIsBackendHealthy(isHealthy);
      if (isHealthy) {
        setIsLiveMode(true);
        // Load live regions
        try {
          const liveRegions = await fetchRegions();
          if (liveRegions && liveRegions.length > 0) {
            setRegions(liveRegions);
            setSelectedRegion(liveRegions[0]);
            // Load live risk zones
            const liveRiskZones = await fetchRiskZones(liveRegions[0].id);
            if (liveRiskZones && liveRiskZones.length > 0) {
              setRiskZones(liveRiskZones);
            }
          }
        } catch {
          // Fallback to mock data if specific endpoints fail
          setRegions(MOCK_REGIONS);
          setSelectedRegion(MOCK_REGIONS[0]);
        }
      } else {
        setIsLiveMode(false);
        setRegions(MOCK_REGIONS);
        setSelectedRegion(MOCK_REGIONS[0]);
        setRiskZones(MOCK_RISK_ZONES);
        setActiveScenario(MOCK_SIMULATION_SCENARIOS[3.0]);
        setFloodPrediction(MOCK_AI_PREDICTION_ASSAM);
        setInferenceMetadata(MOCK_INFERENCE_METADATA_ASSAM);
      }
    } catch {
      setIsBackendHealthy(false);
      setIsLiveMode(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    initialize();
  }, [initialize]);

  // Switch region handler
  const setSelectedRegionId = useCallback(
    (regionId: string) => {
      const found = regions.find((r) => r.id === regionId);
      if (found) {
        setSelectedRegion(found);
        if (regionId.includes('odisha') || found.name.toLowerCase().includes('odisha') || found.name.toLowerCase().includes('mahanadi')) {
          setFloodPrediction(MOCK_AI_PREDICTION_ODISHA);
          setInferenceMetadata(MOCK_INFERENCE_METADATA_ODISHA);
        } else {
          setFloodPrediction(MOCK_AI_PREDICTION_ASSAM);
          setInferenceMetadata(MOCK_INFERENCE_METADATA_ASSAM);
        }
      }
    },
    [regions]
  );

  // Toggle Layer visibility
  const toggleLayer = useCallback((layerKey: keyof LayerVisibility) => {
    setVisibleLayers((prev) => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  }, []);

  // Run Scenario Simulation
  const runScenarioSimulation = useCallback(
    async (floodLevel: number) => {
      setIsSimulating(true);
      setError(null);

      if (isLiveMode && selectedRegion) {
        try {
          const initial = await createSimulation({
            region_id: selectedRegion.id,
            flood_level: floodLevel,
          });

          // If completed immediately
          if (initial.status === 'completed') {
            setActiveScenario(initial);
          } else {
            // Poll for completion (up to 10 attempts)
            let attempts = 0;
            let current = initial;
            while (current.status !== 'completed' && current.status !== 'failed' && attempts < 10) {
              await new Promise((resolve) => setTimeout(resolve, 1000));
              current = await getSimulation(initial.scenario_id);
              attempts++;
            }

            if (current.status === 'completed') {
              setActiveScenario(current);
            } else {
              // Graceful fallback to matching mock curve if background worker is offline
              const fallback =
                MOCK_SIMULATION_SCENARIOS[floodLevel] ||
                MOCK_SIMULATION_SCENARIOS[3.0];
              setActiveScenario({
                ...fallback,
                scenario_id: initial.scenario_id,
                flood_level: floodLevel,
              });
            }
          }

          // Fetch updated risk zones for scenario
          try {
            const updatedZones = await fetchRiskZones(selectedRegion.id, initial.scenario_id);
            if (updatedZones && updatedZones.length > 0) {
              setRiskZones(updatedZones);
            }
          } catch {
            // Keep current risk zones if scenario filter is empty
          }
        } catch (err: any) {
          setError(`Simulation request failed: ${err.message}. Using demo simulation curve.`);
          const fallback =
            MOCK_SIMULATION_SCENARIOS[floodLevel] ||
            MOCK_SIMULATION_SCENARIOS[3.0];
          setActiveScenario(fallback);
        } finally {
          setIsSimulating(false);
        }
      } else {
        // DEMO / OFFLINE MODE: Instant response using verified simulation curves
        await new Promise((resolve) => setTimeout(resolve, 600)); // smooth tactile latency
        const scenario =
          MOCK_SIMULATION_SCENARIOS[floodLevel] || {
            scenario_id: `custom-scenario-${floodLevel}m`,
            region_id: selectedRegion?.id || 'morigaon-assam-001',
            flood_level: floodLevel,
            status: 'completed' as const,
            flooded_area: +(floodLevel * 14.1).toFixed(1),
            population_affected: Math.round(floodLevel * 4166),
            buildings_affected: Math.round(floodLevel * 1066),
            roads_affected_count: Math.round(floodLevel * 10),
            hospitals_affected: Math.min(5, Math.floor(floodLevel)),
            result_geometry: MOCK_SIMULATION_SCENARIOS[3.0].result_geometry,
            created_at: new Date().toISOString(),
          };

        setActiveScenario(scenario);
        setIsSimulating(false);
      }
    },
    [isLiveMode, selectedRegion]
  );

  return (
    <DisasterContext.Provider
      value={{
        isLiveMode,
        isBackendHealthy,
        setLiveMode: setIsLiveMode,
        isLoading,
        error,
        regions,
        selectedRegion,
        setSelectedRegionId,
        floodPrediction,
        inferenceMetadata,
        activeScenario,
        isSimulating,
        runScenarioSimulation,
        riskZones,
        priorityZones,
        selectedZoneId,
        setSelectedZoneId,
        facilities,
        activeRoute,
        visibleLayers,
        toggleLayer,
        tileLayer,
        setTileLayer,
        refreshData: initialize,
      }}
    >
      {children}
    </DisasterContext.Provider>
  );
};

export const useDisaster = () => {
  const context = useContext(DisasterContext);
  if (!context) {
    throw new Error('useDisaster must be used within a DisasterProvider');
  }
  return context;
};
