/**
 * Audio encoder availability API
 */

import { baseFetchJson } from './base';
import type { EncoderAvailabilityResponse } from '../types/audio';

/**
 * Check availability of all audio encoder binaries
 */
export async function fetchEncoderAvailability(): Promise<EncoderAvailabilityResponse> {
  return await baseFetchJson<EncoderAvailabilityResponse>('/api/audio/availability');
}
