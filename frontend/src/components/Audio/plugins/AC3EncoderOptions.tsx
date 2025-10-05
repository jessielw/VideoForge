/**
 * AC3 (Dolby Digital) Audio Encoder Plugin
 */

import React from 'react';
import { AC3Config } from '../../../types/audio';
import { AudioEncoderPluginProps, AudioEncoderPlugin } from '../registry';

// Standard AC3 bitrates (in kbps)
const AC3_BITRATES = [96, 128, 192, 256, 320, 384, 448, 640];

// Channel configurations
const CHANNEL_OPTIONS: { value: '1.0' | '2.0' | '5.1'; label: string; description: string }[] = [
  { value: '1.0', label: 'Mono (1.0)', description: 'Single channel' },
  { value: '2.0', label: 'Stereo (2.0)', description: 'Standard stereo' },
  { value: '5.1', label: '5.1 Surround', description: 'Full surround sound' },
];

function AC3EncoderOptions({
  config,
  onChange,
  disabled = false,
}: AudioEncoderPluginProps<AC3Config>): JSX.Element {
  const handleFieldChange = <K extends keyof AC3Config>(field: K, value: AC3Config[K]) => {
    onChange({ ...config, [field]: value });
  };

  return (
    <div className="audio-encoder-plugin ac3-options">
      <h3>AC3 (Dolby Digital) Options</h3>

      {/* Bitrate Selection */}
      <div className="form-group">
        <label htmlFor="ac3-bitrate">Bitrate</label>
        <select
          id="ac3-bitrate"
          value={config.bitrate}
          onChange={e => handleFieldChange('bitrate', parseInt(e.target.value, 10))}
          className="form-control"
          disabled={disabled}
        >
          {AC3_BITRATES.map(br => (
            <option key={br} value={br}>
              {br} kbps
            </option>
          ))}
        </select>
        <small className="form-help">
          Higher bitrate = better quality. Recommended: 192 kbps (stereo), 448 kbps (5.1 surround).
        </small>
      </div>

      {/* Channel Configuration */}
      <div className="form-group">
        <label htmlFor="ac3-channels">Channels (Downmix)</label>
        <select
          id="ac3-channels"
          value={config.channels ?? '2.0'}
          onChange={e => handleFieldChange('channels', e.target.value as '1.0' | '2.0' | '5.1')}
          className="form-control"
          disabled={disabled}
        >
          {CHANNEL_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label} — {opt.description}
            </option>
          ))}
        </select>
        <small className="form-help">
          Choose output channel configuration. Source will be downmixed if it has more channels.
        </small>
      </div>

      {/* Info Box */}
      <div className="info-box">
        <strong>ℹ️ About AC3:</strong>
        <ul>
          <li>Also known as Dolby Digital</li>
          <li>Widely supported in media players and devices</li>
          <li>Good for compatibility with older hardware</li>
          <li>Maximum 640 kbps bitrate</li>
        </ul>
      </div>
    </div>
  );
}

// Plugin definition
export const ac3Plugin: AudioEncoderPlugin<AC3Config> = {
  component: AC3EncoderOptions,
  displayName: 'AC3 (Dolby Digital)',
  description: 'Widely compatible, standard quality',
  icon: '🔊',
  defaultConfig: (sourceTrack = 0) => ({
    encoderType: 'ac3',
    sourceTrack,
    bitrate: 192,
    channels: '2.0',
  }),
  generateArgs: config => {
    const args: string[] = [];

    // Codec
    args.push('-c:a', 'ac3');

    // Bitrate
    args.push('-b:a', `${config.bitrate}k`);

    // Channel configuration
    if (config.channels === '1.0') {
      args.push('-ac', '1');
    } else if (config.channels === '2.0') {
      args.push('-ac', '2');
    } else if (config.channels === '5.1') {
      args.push('-ac', '6');
    }

    return args;
  },
  validateConfig: config => {
    const errors: string[] = [];

    if (!AC3_BITRATES.includes(config.bitrate)) {
      errors.push(
        `Invalid AC3 bitrate: ${config.bitrate}. Must be one of: ${AC3_BITRATES.join(', ')}`
      );
    }

    if (config.sourceTrack < 0) {
      errors.push('Source track index must be non-negative');
    }

    return errors;
  },
};

export default AC3EncoderOptions;
