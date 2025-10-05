/**
 * Audio Encoder Plugin System - Registry and Interface
 */

import React from 'react';
import { AudioEncoderConfig } from '../../types/audio';

// Props for audio encoder-specific components
export interface AudioEncoderPluginProps<T extends AudioEncoderConfig> {
  config: T;
  onChange: (config: T) => void;
  disabled?: boolean;
}

// Audio encoder plugin definition
export interface AudioEncoderPlugin<T extends AudioEncoderConfig = AudioEncoderConfig> {
  // Component to render encoder-specific options
  component: React.FC<AudioEncoderPluginProps<T>>;

  // Display information
  displayName: string;
  description: string;
  icon?: string;

  // Factory function to create default config
  defaultConfig: (sourceTrack?: number) => T;

  // Optional: Validate configuration
  validateConfig?: (config: T) => string[];

  // Optional: Generate FFmpeg audio codec arguments
  generateArgs?: (config: T) => string[];

  // Optional: Check if encoder is available
  isAvailable?: () => Promise<boolean>;
}

// Registry type
export type AudioEncoderRegistry = Record<string, AudioEncoderPlugin>;

// Will be populated by plugin components
export const AUDIO_ENCODER_REGISTRY: AudioEncoderRegistry = {};
