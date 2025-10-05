/**
 * Audio encoder configuration types - Plugin System
 */

// Supported audio encoder types
export type AudioEncoderType = 'ac3' | 'aac' | 'opus' | 'flac' | 'copy';

// Audio track selection
export interface AudioTrack {
  index: number; // Track index from source
  language?: string;
  title?: string;
  codec?: string;
  channels?: number;
  sampleRate?: number;
}

// Base audio encoder configuration
export interface BaseAudioConfig {
  encoderType: AudioEncoderType;
  sourceTrack: number; // Which track from source to encode
}

// AC3 (Dolby Digital) configuration
export interface AC3Config extends BaseAudioConfig {
  encoderType: 'ac3';
  bitrate: number; // kbps: 96, 128, 192, 256, 320, 384, 448, 640
  channels?: '1.0' | '2.0' | '5.1'; // Downmix option
}

// AAC configuration (placeholder for future)
export interface AACConfig extends BaseAudioConfig {
  encoderType: 'aac';
  bitrate: number; // kbps
  profile?: 'lc' | 'he' | 'he-v2';
}

// Opus configuration (placeholder for future)
export interface OpusConfig extends BaseAudioConfig {
  encoderType: 'opus';
  bitrate: number; // kbps
  application?: 'audio' | 'voip' | 'lowdelay';
}

// FLAC configuration (placeholder for future)
export interface FLACConfig extends BaseAudioConfig {
  encoderType: 'flac';
  compressionLevel?: number; // 0-8
}

// Copy stream (no re-encoding)
export interface AudioCopyConfig extends BaseAudioConfig {
  encoderType: 'copy';
}

// Union type for all audio encoders (discriminated union)
export type AudioEncoderConfig = AC3Config | AACConfig | OpusConfig | FLACConfig | AudioCopyConfig;

// Audio encoding job configuration (supports multiple tracks)
export interface AudioJobConfig {
  tracks: AudioEncoderConfig[];
}

// Legacy support - simple single-track config
export interface SimpleAudioConfig {
  encoder: AudioEncoderType;
  bitrate: number;
  sourceTrack: number;
}
