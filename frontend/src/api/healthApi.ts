import { apiClient } from './client';

export interface HealthResponse {
  status: string;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data.status === 'ok';
  } catch {
    return false;
  }
}
