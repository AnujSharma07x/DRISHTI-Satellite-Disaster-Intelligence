import { apiClient } from './client';
import { RiskZone, RiskZonesResponse } from '../types/risk';

export async function fetchRiskZones(
  regionId?: string | null,
  scenarioId?: string | null
): Promise<RiskZone[]> {
  const params: Record<string, string> = {};
  if (regionId) params.region_id = regionId;
  if (scenarioId) params.scenario_id = scenarioId;

  const response = await apiClient.get<RiskZonesResponse>('/risk-zones', { params });
  return response.data.risk_zones;
}
