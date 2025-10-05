/**
 * AudioSettings - Main audio encoder configuration UI (Plugin System)
 */

import React, { useState } from 'react';
import { SimpleAudioConfig, AudioEncoderType, AudioEncoderConfig } from '../../types/audio';
import AudioEncoderSelector from './AudioEncoderSelector';
import AudioTrackSelector from './AudioTrackSelector';
import AudioPresetManager from './AudioPresetManager';
import { AUDIO_ENCODER_REGISTRY } from './plugins';

interface AudioSettingsProps {
  config: SimpleAudioConfig;
  onChange: (config: SimpleAudioConfig) => void;
}

export default function AudioSettings({ config, onChange }: AudioSettingsProps): JSX.Element {
  // Convert simple config to full encoder config
  const currentConfig: any = {
    encoderType: config.encoder,
    sourceTrack: config.sourceTrack,
    bitrate: config.bitrate,
    channels: '2.0', // Default
  };

  // Get current encoder plugin
  const currentPlugin = AUDIO_ENCODER_REGISTRY[currentConfig.encoderType];
  if (!currentPlugin) {
    return (
      <div className="audio-settings">
        <div className="error-banner">Unknown audio encoder type: {currentConfig.encoderType}</div>
      </div>
    );
  }

  const AudioEncoderComponent = currentPlugin.component;

  const handleEncoderChange = (newType: AudioEncoderType) => {
    const plugin = AUDIO_ENCODER_REGISTRY[newType];
    if (!plugin) return;

    const newConfig = plugin.defaultConfig(config.sourceTrack);

    // Convert back to simple format
    onChange({
      encoder: newConfig.encoderType,
      sourceTrack: newConfig.sourceTrack,
      bitrate: (newConfig as any).bitrate ?? 192,
    });
  };

  const handleAudioConfigChange = (newConfig: AudioEncoderConfig) => {
    // Convert back to simple format
    onChange({
      encoder: newConfig.encoderType,
      sourceTrack: newConfig.sourceTrack,
      bitrate: (newConfig as any).bitrate ?? 192,
    });
  };

  // Generate command preview
  const commandArgs = currentPlugin.generateArgs?.(currentConfig);
  const commandString = commandArgs ? commandArgs.join(' ') : '';

  const handleLoadPreset = (presetConfig: AudioEncoderConfig) => {
    // Convert to simple format
    onChange({
      encoder: presetConfig.encoderType,
      sourceTrack: presetConfig.sourceTrack,
      bitrate: (presetConfig as any).bitrate ?? 192,
    });
  };

  return (
    <div className="audio-settings">
      <div className="audio-header">
        <h2>Audio Encoder Configuration</h2>
      </div>

      <div className="audio-form">
        {/* Audio Preset Manager */}
        <AudioPresetManager currentConfig={currentConfig} onLoadPreset={handleLoadPreset} />

        {/* Source Track Selection */}
        <AudioTrackSelector
          selectedTrack={config.sourceTrack}
          onChange={trackIndex =>
            onChange({
              ...config,
              sourceTrack: trackIndex,
            })
          }
        />

        {/* Encoder Selection */}
        <AudioEncoderSelector
          value={currentConfig.encoderType}
          onChange={handleEncoderChange}
          registry={AUDIO_ENCODER_REGISTRY}
        />

        {/* Encoder-Specific Options */}
        <div className="audio-encoder-specific-options">
          <AudioEncoderComponent
            config={currentConfig as any}
            onChange={handleAudioConfigChange as any}
          />
        </div>

        {/* Command Preview */}
        {commandString && (
          <div className="command-preview-section">
            <h4>FFmpeg Audio Arguments</h4>
            <div className="command-preview">
              <code>{commandString}</code>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
