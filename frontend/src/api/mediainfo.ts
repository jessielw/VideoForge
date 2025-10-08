import type { MediaInfoData } from '../types/mediaInfoContext';
import { baseFetchJson } from './base';

export async function fetchMediaInfoApi(
  path: string,
  includeRaw: boolean = false
): Promise<MediaInfoData> {
  // Use a short timeout and a single retry for mediainfo parsing to improve
  // developer UX when the backend momentarily fails or is slow.
  return await baseFetchJson<MediaInfoData>(
    '/api/mediainfo',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, include_raw: includeRaw }),
    },
    { timeoutMs: 3000, retries: 1, retryDelayMs: 300 }
  );
}
