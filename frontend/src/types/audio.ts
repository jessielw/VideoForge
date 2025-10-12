/**
 * Audio encoder configuration types
 * These types match the backend Pydantic models in backend/app/enums/audio/
 */

// ============================================================================
// Base Types
// ============================================================================

export type AudioEncoderType = 'deezy' | 'copy';

export interface BaseAudioConfig {
  encoder_type: AudioEncoderType;
  source_track: number;
  language?: string;
  title?: string;
  custom_args?: string;
}

// ============================================================================
// Copy Mode
// ============================================================================

export interface CopyConfig extends BaseAudioConfig {
  encoder_type: 'copy';
}

// ============================================================================
// DeeZy Encoder Types
// ============================================================================

export type DeezyCodecFormat = 'dd' | 'ddp' | 'atmos' | 'ac4';

// DeeZy channel configurations
export type DeezyDDChannels = 0 | 1 | 2 | 6; // AUTO, MONO, STEREO, SURROUND
export type DeezyDDPChannels = 0 | 1 | 2 | 6 | 8; // AUTO, MONO, STEREO, SURROUND, SURROUNDEX
export type DeezyAtmosMode = 'streaming' | 'bluray';
export type DeezyAC4Channels = 'immersive_stereo';

// DeeZy options
export type DeezyStereoDownmix = 'loro' | 'ltrt';
export type DeezyDRCProfile =
  | 'film_standard'
  | 'film_light'
  | 'music_standard'
  | 'music_light'
  | 'speech'
  | 'none';

// Base DeeZy config
export interface BaseDeezyConfig extends BaseAudioConfig {
  encoder_type: 'deezy';
  codec_format: DeezyCodecFormat;
  stereo_downmix?: DeezyStereoDownmix;
  drc_line_mode?: DeezyDRCProfile;
  drc_rf_mode?: DeezyDRCProfile;
  dialnorm?: number; // -31 to 0 (0 disables it)
}

// Dolby Digital (DD/AC-3)
export interface DeezyDDConfig extends BaseDeezyConfig {
  codec_format: 'dd';
  channels: DeezyDDChannels;
  bitrate: number | null; // null for AUTO
}

// Dolby Digital Plus (DDP/E-AC-3)
export interface DeezyDDPConfig extends BaseDeezyConfig {
  codec_format: 'ddp';
  channels: DeezyDDPChannels;
  bitrate: number | null; // null for AUTO
}

// Dolby Atmos
export interface DeezyAtmosConfig extends BaseDeezyConfig {
  codec_format: 'atmos';
  atmos_mode: DeezyAtmosMode;
  bitrate: number;
}

// Dolby AC-4
export interface DeezyAC4Config extends BaseDeezyConfig {
  codec_format: 'ac4';
  channels: DeezyAC4Channels;
  bitrate: number;
}

// Discriminated union of all DeeZy configs
export type DeezyConfig = DeezyDDConfig | DeezyDDPConfig | DeezyAtmosConfig | DeezyAC4Config;

// Discriminated union of all audio encoder configs
export type AudioEncoderConfig = DeezyConfig | CopyConfig;

// ============================================================================
// Output Track Configuration (for AudioTrackManager)
// ============================================================================

export interface OutputAudioTrack {
  id: string; // Unique ID for React keys
  config: AudioEncoderConfig; // The actual encoder config
  title?: string; // Title
}

// ============================================================================
// Audio Capabilities API Response Types
// ============================================================================

export interface ChannelCapability {
  value: number | string;
  name: string;
  label: string;
  description: string;
  default_bitrate: number | null;
  valid_bitrates: number[];
}

export interface EncoderOption {
  label: string;
  description?: string;
  type?: 'select' | 'integer' | 'boolean';
  default?: any;
  choices?: Array<{
    value: string;
    label: string;
    description?: string;
  }>;
  min?: number;
  max?: number;
}

export interface EncoderAvailabilityResponse {
  ok: boolean;
  availability: Record<string, boolean>;
  message?: string;
}

// ============================================================================
// Preset Types
// ============================================================================

export interface AudioPreset {
  id: string;
  name: string;
  description?: string;
  encoder_type: AudioEncoderType;
  codec_format?: string;
  config: AudioEncoderConfig;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface AudioPresetCreate {
  name: string;
  description?: string;
  config: AudioEncoderConfig;
}

export interface AudioPresetListResponse {
  ok: boolean;
  presets: AudioPreset[];
  total: number;
}
