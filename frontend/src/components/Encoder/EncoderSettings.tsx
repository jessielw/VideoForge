/**
 * EncoderSettings - Main video encoder configuration UI (Plugin System)
 */

import React, { useState } from 'react';
import { EncoderConfig, VideoEncoderConfig, EncoderType } from '../../types/encoder';
import { useEncoderPresets } from '../../hooks/useEncoderPresets';
import EncoderPresetManager from './EncoderPresetManager';
import EncoderSelector from './EncoderSelector';
import RateControlSelector from './RateControlSelector';
import CommandPreview from './CommandPreview';
import { ENCODER_REGISTRY } from './plugins';

interface EncoderSettingsProps {
  config: EncoderConfig;
  onChange: (config: EncoderConfig) => void;
}

export default function EncoderSettings({ config, onChange }: EncoderSettingsProps): JSX.Element {
  const { allPresets, savePreset, deletePreset, getPreset, isLoading, error } = useEncoderPresets();

  // Convert legacy EncoderConfig to VideoEncoderConfig
  const currentConfig: any = {
    encoderType: config.encoder as EncoderType,
    rateControlMode: config.mode,
    crf: config.crf,
    targetBitrate: config.bitrate,
    preset: config.preset,
    tune: config.tune === 'none' ? undefined : config.tune,
    customArgs: config.customArgs,
    selectedPresetId: config.selectedPresetId,
  };

  // Get current encoder plugin
  const currentPlugin = ENCODER_REGISTRY[currentConfig.encoderType];
  if (!currentPlugin) {
    return (
      <div className="encoder-settings">
        <div className="error-banner">Unknown encoder type: {currentConfig.encoderType}</div>
      </div>
    );
  }

  const EncoderComponent = currentPlugin.component;

  const handleEncoderChange = (newType: EncoderType) => {
    const plugin = ENCODER_REGISTRY[newType];
    if (!plugin) return;

    const newConfig = plugin.defaultConfig();

    // Convert back to legacy format
    onChange({
      encoder: newConfig.encoderType as 'x264' | 'x265',
      mode: newConfig.rateControlMode,
      crf: (newConfig as any).crf ?? 23,
      bitrate: newConfig.targetBitrate ?? 5000,
      preset: (newConfig as any).preset ?? 'medium',
      tune: (newConfig as any).tune ?? 'none',
      customArgs: (newConfig as any).customArgs ?? '',
    });
  };

  const handleRateControlChange = (mode: typeof currentConfig.rateControlMode) => {
    onChange({
      ...config,
      mode,
    });

    // Update current config
    currentConfig.rateControlMode = mode;
  };

  const handleEncoderConfigChange = (newConfig: VideoEncoderConfig) => {
    // Convert back to legacy format
    onChange({
      encoder: newConfig.encoderType as 'x264' | 'x265',
      mode: newConfig.rateControlMode,
      crf: (newConfig as any).crf ?? 23,
      bitrate: newConfig.targetBitrate ?? 5000,
      preset: (newConfig as any).preset ?? 'medium',
      tune: (newConfig as any).tune ?? 'none',
      customArgs: (newConfig as any).customArgs ?? '',
      selectedPresetId: newConfig.selectedPresetId,
    });
  };

  const handlePresetLoad = (presetId: string) => {
    const preset = getPreset(presetId);
    if (!preset) return;

    // For now, just load old-style presets
    // TODO: Update preset system to use VideoEncoderConfig
    onChange({
      ...config,
      encoder: preset.encoder,
      mode: preset.mode,
      crf: preset.crf ?? config.crf,
      bitrate: preset.bitrate ?? config.bitrate,
      preset: preset.preset ?? config.preset,
      tune: preset.tune ?? config.tune,
      customArgs: preset.customArgs ?? config.customArgs,
      selectedPresetId: presetId,
    });
  };

  const handlePresetSave = async (name: string, description: string) => {
    await savePreset({
      name,
      description,
      encoder: config.encoder,
      mode: config.mode,
      crf: config.crf,
      bitrate: config.bitrate,
      preset: config.preset as any,
      tune: config.tune as any,
      customArgs: config.customArgs,
    });
  };

  // Generate command preview
  const commandArgs = currentPlugin.generateCommand?.(currentConfig, 'output.mkv');

  return (
    <div className="encoder-settings">
      <div className="encoder-header">
        <h2>Video Encoder Configuration</h2>
      </div>

      {error && <div className="error-banner">⚠️ Failed to load presets from backend: {error}</div>}

      <EncoderPresetManager
        presets={allPresets}
        selectedPresetId={config.selectedPresetId}
        onLoad={handlePresetLoad}
        onSave={handlePresetSave}
        onDelete={deletePreset}
        isLoading={isLoading}
      />

      <div className="encoder-form">
        {/* Encoder Selection */}
        <EncoderSelector
          value={currentConfig.encoderType}
          onChange={handleEncoderChange}
          registry={ENCODER_REGISTRY}
        />

        {/* Rate Control Mode */}
        <RateControlSelector
          mode={currentConfig.rateControlMode}
          onChange={handleRateControlChange}
          supportedModes={currentPlugin.supportsRateControl}
        />

        {/* Encoder-Specific Options */}
        <div className="encoder-specific-options">
          <EncoderComponent
            config={currentConfig as any}
            onChange={handleEncoderConfigChange as any}
          />
        </div>

        {/* Command Preview */}
        <CommandPreview command={commandArgs} />
      </div>
    </div>
  );
}
