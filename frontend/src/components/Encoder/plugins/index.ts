/**
 * Encoder Plugins Index - Register all encoder plugins here
 */

import { EncoderRegistry } from '../registry';
import { x264Plugin } from './X264EncoderOptions';
import { x265Plugin } from './X265EncoderOptions';

// Central encoder registry
export const ENCODER_REGISTRY: EncoderRegistry = {
  x264: x264Plugin as any, // Type-safe at runtime due to discriminated union
  x265: x265Plugin as any,
  // Add more encoders here as they're implemented:
  // 'av1-svt': av1Plugin as any,
  // 'nvenc-h264': nvencH264Plugin as any,
  // 'nvenc-h265': nvencH265Plugin as any,
};

// Export individual plugins
export { x264Plugin, x265Plugin };
