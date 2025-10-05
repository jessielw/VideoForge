/**
 * Encoder Plugin System - Registry and Interface
 */

import React from 'react';
import { VideoEncoderConfig, RateControlMode } from '../../types/encoder';

// Props for encoder-specific components
export interface EncoderPluginProps<T extends VideoEncoderConfig> {
  config: T;
  onChange: (config: T) => void;
  disabled?: boolean;
}

// Encoder plugin definition
export interface EncoderPlugin<T extends VideoEncoderConfig = VideoEncoderConfig> {
  // Component to render encoder-specific options
  component: React.FC<EncoderPluginProps<T>>;

  // Display information
  displayName: string;
  description: string;
  icon?: string;

  // Capabilities
  supportsRateControl: RateControlMode[];

  // Factory function to create default config
  defaultConfig: () => T;

  // Optional: Validate configuration
  validateConfig?: (config: T) => string[];

  // Optional: Generate CLI command arguments
  generateCommand?: (config: T, outputPath: string) => string[];

  // Optional: Check if encoder is available on system
  isAvailable?: () => Promise<boolean>;
}

// Registry type
export type EncoderRegistry = Record<string, EncoderPlugin>;

// Will be populated by plugin components
export const ENCODER_REGISTRY: EncoderRegistry = {};
