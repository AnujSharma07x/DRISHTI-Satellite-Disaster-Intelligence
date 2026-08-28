import { apiClient } from './client';
import { SimulationRequest, SimulationResponse } from '../types/simulation';

export async function createSimulation(payload: SimulationRequest): Promise<SimulationResponse> {
  const response = await apiClient.post<SimulationResponse>('/simulation', payload);
  return response.data;
}

export async function getSimulation(scenarioId: string): Promise<SimulationResponse> {
  const response = await apiClient.get<SimulationResponse>(`/simulation/${scenarioId}`);
  return response.data;
}
