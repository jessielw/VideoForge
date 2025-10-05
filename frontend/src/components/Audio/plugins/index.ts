/**
 * Audio Encoder Plugins Index - Register all audio encoder plugins here
 */

import { AudioEncoderRegistry } from '../registry';
import { ac3Plugin } from './AC3EncoderOptions';

// Central audio encoder registry
export const AUDIO_ENCODER_REGISTRY: AudioEncoderRegistry = {
  ac3: ac3Plugin as any, // Type-safe at runtime due to discriminated union
  // Add more audio encoders here as they're implemented:
  // 'aac': aacPlugin as any,
  // 'opus': opusPlugin as any,
  // 'flac': flacPlugin as any,
  // 'copy': copyPlugin as any,
};

// Export individual plugins
export { ac3Plugin };
