import type { VsResponse } from '../types/vs';
import { baseFetchJson } from './base';

export async function fetchVsInfo(path: string): Promise<VsResponse> {
  return await baseFetchJson<VsResponse>('/api/vs/info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
}
