/**
 * EncoderSettings - Main video encoder configuration UI for Phase 2
 */

import React, { useState, useEffect } from 'react';
import { EncoderConfig, EncoderType, RateControlMode } from '../../types/encoder';
import { useEncoderPresets } from '../../hooks/useEncoderPresets';
import EncoderPresetManager from './EncoderPresetManager';

interface EncoderSettingsProps {
  config: EncoderConfig;
  onChange: (config: EncoderConfig) => void;
}

const ENCODER_OPTIONS: { value: EncoderType; label: string; description: string }[] = [
  {
    value: 'x264',
    label: 'x264 (H.264/AVC)',
    description: 'Fast, widely compatible, good quality',
  },
  {
    value: 'x265',
    label: 'x265 (H.265/HEVC)',
    description: 'Better compression, slower encoding',
  },
];

const PRESET_OPTIONS = [
  'ultrafast',
  'superfast',
  'veryfast',
  'faster',
  'fast',
  'medium',
  'slow',
  'slower',
  'veryslow',
  'placebo',
];

const TUNE_OPTIONS = [
  'none',
  'film',
  'animation',
  'grain',
  'stillimage',
  'fastdecode',
  'zerolatency',
];

export default function EncoderSettings({ config, onChange }: EncoderSettingsProps): JSX.Element {
  const { allPresets, savePreset, deletePreset, getPreset, isLoading, error } = useEncoderPresets();
  const [showCommandPreview, setShowCommandPreview] = useState(false);

  // CRF ranges based on encoder
  const crfMin = config.encoder.includes('265') ? 0 : 0;
  const crfMax = config.encoder.includes('265') ? 51 : 51;
  const crfDefault = config.encoder.includes('265') ? 25 : 23;

  const handleFieldChange = (field: keyof EncoderConfig, value: any) => {
    onChange({ ...config, [field]: value });
  };

  const handlePresetLoad = (presetId: string) => {
    const preset = getPreset(presetId);
    if (!preset) return;

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

  const handlePresetSave = (name: string, description: string) => {
    savePreset({
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
        <div className="form-group">
          <label htmlFor="encoder">Encoder</label>
          <select
            id="encoder"
            value={config.encoder}
            onChange={e => handleFieldChange('encoder', e.target.value as EncoderType)}
            className="form-control"
          >
            {ENCODER_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>
                {opt.label} — {opt.description}
              </option>
            ))}
          </select>
        </div>

        {/* Rate Control Mode */}
        <div className="form-group">
          <label htmlFor="mode">Rate Control Mode</label>
          <div className="radio-group">
            <label className="radio-label">
              <input
                type="radio"
                name="mode"
                value="crf"
                checked={config.mode === 'crf'}
                onChange={e => handleFieldChange('mode', e.target.value as RateControlMode)}
              />
              <span>CRF (Constant Rate Factor)</span>
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="mode"
                value="2pass"
                checked={config.mode === '2pass'}
                onChange={e => handleFieldChange('mode', e.target.value as RateControlMode)}
              />
              <span>2-Pass (Target Bitrate)</span>
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="mode"
                value="bitrate"
                checked={config.mode === 'bitrate'}
                onChange={e => handleFieldChange('mode', e.target.value as RateControlMode)}
              />
              <span>Single-Pass Bitrate</span>
            </label>
          </div>
        </div>

        {/* CRF Slider (only for CRF mode) */}
        {config.mode === 'crf' && (
          <div className="form-group">
            <label htmlFor="crf">
              CRF Quality: {config.crf}
              <span className="quality-hint">
                {config.crf <= 18
                  ? ' (Visually Lossless)'
                  : config.crf <= 23
                    ? ' (High Quality)'
                    : config.crf <= 28
                      ? ' (Good Quality)'
                      : ' (Lower Quality)'}
              </span>
            </label>
            <input
              type="range"
              id="crf"
              min={crfMin}
              max={crfMax}
              step={1}
              value={config.crf}
              onChange={e => handleFieldChange('crf', parseInt(e.target.value, 10))}
              className="form-range"
            />
            <div className="range-labels">
              <span>Better Quality (larger file)</span>
              <span>Smaller File (lower quality)</span>
            </div>
            <small className="form-help">
              Lower CRF = higher quality & larger file. Recommended: 18-23 for x264, 20-28 for x265.
            </small>
          </div>
        )}

        {/* Bitrate Input (for 2pass and bitrate modes) */}
        {(config.mode === '2pass' || config.mode === 'bitrate') && (
          <div className="form-group">
            <label htmlFor="bitrate">Target Bitrate (kbps)</label>
            <input
              type="number"
              id="bitrate"
              min={500}
              max={50000}
              step={100}
              value={config.bitrate}
              onChange={e => handleFieldChange('bitrate', parseInt(e.target.value, 10))}
              className="form-control"
            />
            <small className="form-help">
              Typical values: 2500-5000 kbps for 1080p, 5000-10000 kbps for 4K.
            </small>
          </div>
        )}

        {/* Preset Dropdown */}
        <div className="form-group">
          <label htmlFor="preset">Encoding Preset</label>
          <select
            id="preset"
            value={config.preset}
            onChange={e => handleFieldChange('preset', e.target.value)}
            className="form-control"
          >
            {PRESET_OPTIONS.map(p => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <small className="form-help">
            Faster presets = quicker encode but larger files. Slower presets = better compression.
          </small>
        </div>

        {/* Tune Dropdown */}
        <div className="form-group">
          <label htmlFor="tune">Tune</label>
          <select
            id="tune"
            value={config.tune}
            onChange={e => handleFieldChange('tune', e.target.value)}
            className="form-control"
          >
            {TUNE_OPTIONS.map(t => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <small className="form-help">
            Tune encoder for specific content types (film, animation, grain, etc.)
          </small>
        </div>

        {/* Custom Arguments */}
        <div className="form-group">
          <label htmlFor="customArgs">Custom Arguments (Advanced)</label>
          <input
            type="text"
            id="customArgs"
            value={config.customArgs}
            onChange={e => handleFieldChange('customArgs', e.target.value)}
            className="form-control"
            placeholder="e.g., --aq-mode 3 --psy-rd 1.0:0.15"
          />
          <small className="form-help">
            Additional CLI arguments passed directly to the encoder. Use with caution.
          </small>
        </div>

        {/* Command Preview */}
        <div className="command-preview-section">
          <button
            type="button"
            className="command-preview-toggle"
            onClick={() => setShowCommandPreview(!showCommandPreview)}
          >
            <span className="toggle-icon">{showCommandPreview ? '▼' : '▶'}</span>
            <span>Command Preview</span>
          </button>
          {showCommandPreview && (
            <div className="command-preview">
              <code>{generateCommandPreview(config)}</code>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function generateCommandPreview(config: EncoderConfig): string {
  const { encoder, mode, crf, bitrate, preset, tune, customArgs } = config;

  // Native CLI format for x264/x265
  let cmd = `${encoder}.exe`;
  cmd += ` --demuxer raw --input-res WIDTHxHEIGHT --input-csp i420 --fps FPS`;
  cmd += ` --preset ${preset}`;

  if (tune && tune !== 'none') {
    cmd += ` --tune ${tune}`;
  }

  if (mode === 'crf') {
    cmd += ` --crf ${crf}`;
  } else if (mode === '2pass') {
    cmd += ` --bitrate ${bitrate} --pass 1`;
    // (second pass would be similar with --pass 2)
  } else if (mode === 'bitrate') {
    cmd += ` --bitrate ${bitrate}`;
  }

  if (customArgs) {
    cmd += ` ${customArgs}`;
  }

  cmd += ` -o output.${encoder === 'x264' ? 'h264' : 'hevc'} -`;

  return cmd;
}
