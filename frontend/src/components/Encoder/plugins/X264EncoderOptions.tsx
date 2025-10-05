/**
 * X264 Encoder Plugin - H.264/AVC encoding options
 */

import React from 'react';
import { X264Config, X264Preset, X264Tune } from '../../../types/encoder';
import { EncoderPluginProps, EncoderPlugin } from '../registry';

const PRESET_OPTIONS: X264Preset[] = [
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

const TUNE_OPTIONS: (X264Tune | 'none')[] = [
  'none',
  'film',
  'animation',
  'grain',
  'stillimage',
  'fastdecode',
  'zerolatency',
];

function X264EncoderOptions({
  config,
  onChange,
  disabled = false,
}: EncoderPluginProps<X264Config>): JSX.Element {
  const handleFieldChange = <K extends keyof X264Config>(field: K, value: X264Config[K]) => {
    onChange({ ...config, [field]: value });
  };

  const getCRFHint = (crf: number): string => {
    if (crf <= 18) return '(Visually Lossless)';
    if (crf <= 23) return '(High Quality)';
    if (crf <= 28) return '(Good Quality)';
    return '(Lower Quality)';
  };

  return (
    <div className="encoder-plugin x264-options">
      <h3>x264 Options</h3>

      {/* CRF Slider (only for CRF mode) */}
      {config.rateControlMode === 'crf' && (
        <div className="form-group">
          <label htmlFor="x264-crf">
            CRF Quality: {config.crf ?? 23}
            <span className="quality-hint"> {getCRFHint(config.crf ?? 23)}</span>
          </label>
          <input
            type="range"
            id="x264-crf"
            min={0}
            max={51}
            step={1}
            value={config.crf ?? 23}
            onChange={e => handleFieldChange('crf', parseInt(e.target.value, 10))}
            className="form-range"
            disabled={disabled}
          />
          <div className="range-labels">
            <span>Better Quality (larger file)</span>
            <span>Smaller File (lower quality)</span>
          </div>
          <small className="form-help">
            Lower CRF = higher quality & larger file. Recommended: 18-23.
          </small>
        </div>
      )}

      {/* Bitrate Input (for 2pass and bitrate modes) */}
      {(config.rateControlMode === '2pass' || config.rateControlMode === 'bitrate') && (
        <div className="form-group">
          <label htmlFor="x264-bitrate">Target Bitrate (kbps)</label>
          <input
            type="number"
            id="x264-bitrate"
            value={config.targetBitrate ?? 5000}
            onChange={e => handleFieldChange('targetBitrate', parseInt(e.target.value, 10))}
            className="form-control"
            min={100}
            max={100000}
            step={100}
            disabled={disabled}
          />
          <small className="form-help">
            Higher bitrate = better quality. Typical: 2000-8000 kbps for 1080p.
          </small>
        </div>
      )}

      {/* Encoding Preset */}
      <div className="form-group">
        <label htmlFor="x264-preset">Encoding Preset</label>
        <select
          id="x264-preset"
          value={config.preset}
          onChange={e => handleFieldChange('preset', e.target.value as X264Preset)}
          className="form-control"
          disabled={disabled}
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

      {/* Tune */}
      <div className="form-group">
        <label htmlFor="x264-tune">Tune (optional)</label>
        <select
          id="x264-tune"
          value={config.tune ?? 'none'}
          onChange={e =>
            handleFieldChange(
              'tune',
              e.target.value === 'none' ? undefined : (e.target.value as X264Tune)
            )
          }
          className="form-control"
          disabled={disabled}
        >
          {TUNE_OPTIONS.map(t => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <small className="form-help">
          Tune encoder for specific content types (film, animation, grain, etc.).
        </small>
      </div>

      {/* Custom Arguments */}
      <div className="form-group">
        <label htmlFor="x264-custom-args">Custom Arguments (Advanced)</label>
        <textarea
          id="x264-custom-args"
          value={config.customArgs ?? ''}
          onChange={e => handleFieldChange('customArgs', e.target.value)}
          className="form-control"
          placeholder="e.g., --aq-mode 3 --psy-rd 1.0:0.0"
          rows={2}
          disabled={disabled}
        />
        <small className="form-help">Additional CLI arguments passed directly to x264.</small>
      </div>
    </div>
  );
}

// Plugin definition
export const x264Plugin: EncoderPlugin<X264Config> = {
  component: X264EncoderOptions,
  displayName: 'x264 (H.264/AVC)',
  description: 'Fast, widely compatible, excellent quality',
  icon: '🎬',
  supportsRateControl: ['crf', '2pass', 'bitrate'],
  defaultConfig: () => ({
    encoderType: 'x264',
    rateControlMode: 'crf',
    crf: 23,
    preset: 'medium',
    tune: undefined,
    customArgs: '',
  }),
  generateCommand: (config, outputPath) => {
    const args: string[] = ['x264'];

    // Rate control
    if (config.rateControlMode === 'crf' && config.crf !== undefined) {
      args.push('--crf', config.crf.toString());
    } else if (config.rateControlMode === '2pass' && config.targetBitrate) {
      args.push('--bitrate', config.targetBitrate.toString());
      args.push('--pass', '1'); // Would need two invocations
    } else if (config.rateControlMode === 'bitrate' && config.targetBitrate) {
      args.push('--bitrate', config.targetBitrate.toString());
    }

    // Preset and tune
    args.push('--preset', config.preset);
    if (config.tune && config.tune !== 'none') {
      args.push('--tune', config.tune);
    }

    // Custom args
    if (config.customArgs) {
      args.push(...config.customArgs.split(' ').filter(Boolean));
    }

    // Output
    args.push('--output', outputPath);
    args.push('-'); // stdin

    return args;
  },
};

export default X264EncoderOptions;
