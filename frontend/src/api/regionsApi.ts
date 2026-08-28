import { apiClient } from './client';
import { Region, RegionsResponse } from '../types/region';

export async function fetchRegions(limit: number = 20, offset: number = 0): Promise<Region[]> {
  const response = await apiClient.get<RegionsResponse>('/regions', {
    params: { limit, offset },
  });
  return response.data.regions;
}
