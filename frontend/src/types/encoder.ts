/**
 * Video encoder configuration types - Plugin System
 */

// Supported encoder types
export type EncoderType = 'x264' | 'x265' | 'av1-svt' | 'nvenc-h264' | 'nvenc-h265';

// Rate control modes
export type RateControlMode = 'crf' | '2pass' | 'bitrate' | 'vbr' | 'cbr' | 'cq' | 'lossless';

// Preset types for x264/x265
export type X264Preset =
  | 'ultrafast'
  | 'superfast'
  | 'veryfast'
  | 'faster'
  | 'fast'
  | 'medium'
  | 'slow'
  | 'slower'
  | 'veryslow'
  | 'placebo';
export type X264Tune =
  | 'film'
  | 'animation'
  | 'grain'
  | 'stillimage'
  | 'fastdecode'
  | 'zerolatency'
  | 'none';

// Base encoder configuration (common fields)
export interface BaseEncoderConfig {
  encoderType: EncoderType;
  rateControlMode: RateControlMode;
  targetBitrate?: number;
  selectedPresetId?: string;
}

// x264 specific configuration
export interface X264Config extends BaseEncoderConfig {
  encoderType: 'x264';
  crf?: number; // 0-51
  preset: X264Preset;
  tune?: X264Tune;
  customArgs?: string;
}

// x265 specific configuration
export interface X265Config extends BaseEncoderConfig {
  encoderType: 'x265';
  crf?: number; // 0-51
  preset: X264Preset; // x265 uses same preset names
  tune?: 'grain' | 'fastdecode' | 'zerolatency' | 'animation' | 'none';
  customArgs?: string;
}

// AV1 (SVT-AV1) specific configuration
export interface AV1Config extends BaseEncoderConfig {
  encoderType: 'av1-svt';
  crf?: number; // 0-63
  preset: number; // 0-13 (0=slowest, 13=fastest)
  filmGrainSynthesis?: number; // 0-50
  tileRows?: number;
  tileCols?: number;
  customArgs?: string;
}

// NVENC (NVIDIA GPU) specific configuration
export interface NVENCConfig extends BaseEncoderConfig {
  encoderType: 'nvenc-h264' | 'nvenc-h265';
  rateControlMode: 'cq' | 'vbr' | 'cbr';
  qualityPreset: 'p1' | 'p2' | 'p3' | 'p4' | 'p5' | 'p6' | 'p7';
  cq?: number; // Constant Quality (0-51)
  lookahead?: number; // 0-32
  spatialAq?: boolean;
  bframes?: number; // 0-4
  customArgs?: string;
}

// Union type for all video encoders (discriminated union)
export type VideoEncoderConfig = X264Config | X265Config | AV1Config | NVENCConfig;

// Encoder preset (for save/load) - keeping old format for now
export interface EncoderPreset {
  id: string;
  name: string;
  description?: string;
  encoder: 'x264' | 'x265'; // Will expand later
  mode: RateControlMode;
  crf?: number;
  bitrate?: number;
  preset?: string;
  tune?: string;
  customArgs?: string;
  isBuiltIn?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

// Legacy support - keep for backward compatibility with existing code
// TODO: Gradually migrate to VideoEncoderConfig
export interface EncoderConfig {
  encoder: 'x264' | 'x265'; // Legacy field
  mode: RateControlMode; // Legacy field
  crf: number;
  bitrate: number;
  preset: string;
  tune: string;
  customArgs: string;
  selectedPresetId?: string;
}
