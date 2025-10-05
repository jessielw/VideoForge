/**
 * X265 Encoder Plugin - H.265/HEVC encoding options
 */

import React from 'react';
import { X265Config, X264Preset } from '../../../types/encoder';
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

const TUNE_OPTIONS: ('none' | 'grain' | 'fastdecode' | 'zerolatency' | 'animation')[] = [
  'none',
  'grain',
  'fastdecode',
  'zerolatency',
  'animation',
];

function X265EncoderOptions({
  config,
  onChange,
  disabled = false,
}: EncoderPluginProps<X265Config>): JSX.Element {
  const handleFieldChange = <K extends keyof X265Config>(field: K, value: X265Config[K]) => {
    onChange({ ...config, [field]: value });
  };

  const getCRFHint = (crf: number): string => {
    if (crf <= 22) return '(Visually Lossless)';
    if (crf <= 28) return '(High Quality)';
    if (crf <= 32) return '(Good Quality)';
    return '(Lower Quality)';
  };

  return (
    <div className="encoder-plugin x265-options">
      <h3>x265 Options</h3>

      {/* CRF Slider (only for CRF mode) */}
      {config.rateControlMode === 'crf' && (
        <div className="form-group">
          <label htmlFor="x265-crf">
            CRF Quality: {config.crf ?? 28}
            <span className="quality-hint"> {getCRFHint(config.crf ?? 28)}</span>
          </label>
          <input
            type="range"
            id="x265-crf"
            min={0}
            max={51}
            step={1}
            value={config.crf ?? 28}
            onChange={e => handleFieldChange('crf', parseInt(e.target.value, 10))}
            className="form-range"
            disabled={disabled}
          />
          <div className="range-labels">
            <span>Better Quality (larger file)</span>
            <span>Smaller File (lower quality)</span>
          </div>
          <small className="form-help">
            Lower CRF = higher quality & larger file. Recommended: 20-28 for x265.
          </small>
        </div>
      )}

      {/* Bitrate Input (for 2pass and bitrate modes) */}
      {(config.rateControlMode === '2pass' || config.rateControlMode === 'bitrate') && (
        <div className="form-group">
          <label htmlFor="x265-bitrate">Target Bitrate (kbps)</label>
          <input
            type="number"
            id="x265-bitrate"
            value={config.targetBitrate ?? 3000}
            onChange={e => handleFieldChange('targetBitrate', parseInt(e.target.value, 10))}
            className="form-control"
            min={100}
            max={100000}
            step={100}
            disabled={disabled}
          />
          <small className="form-help">
            x265 achieves similar quality to x264 at ~50% lower bitrate. Typical: 1500-5000 kbps for
            1080p.
          </small>
        </div>
      )}

      {/* Encoding Preset */}
      <div className="form-group">
        <label htmlFor="x265-preset">Encoding Preset</label>
        <select
          id="x265-preset"
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
          x265 is slower than x264. Medium preset recommended for most cases. Slower presets take
          significantly longer.
        </small>
      </div>

      {/* Tune */}
      <div className="form-group">
        <label htmlFor="x265-tune">Tune (optional)</label>
        <select
          id="x265-tune"
          value={config.tune ?? 'none'}
          onChange={e =>
            handleFieldChange(
              'tune',
              e.target.value === 'none'
                ? undefined
                : (e.target.value as 'grain' | 'fastdecode' | 'zerolatency' | 'animation')
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
          Tune encoder for specific content (grain, animation, etc.).
        </small>
      </div>

      {/* Custom Arguments */}
      <div className="form-group">
        <label htmlFor="x265-custom-args">Custom Arguments (Advanced)</label>
        <textarea
          id="x265-custom-args"
          value={config.customArgs ?? ''}
          onChange={e => handleFieldChange('customArgs', e.target.value)}
          className="form-control"
          placeholder="e.g., --aq-mode 3 --psy-rd 2.0"
          rows={2}
          disabled={disabled}
        />
        <small className="form-help">Additional CLI arguments passed directly to x265.</small>
      </div>
    </div>
  );
}

// Plugin definition
export const x265Plugin: EncoderPlugin<X265Config> = {
  component: X265EncoderOptions,
  displayName: 'x265 (H.265/HEVC)',
  description: 'Better compression, slower encoding',
  icon: '🎞️',
  supportsRateControl: ['crf', '2pass', 'bitrate'],
  defaultConfig: () => ({
    encoderType: 'x265',
    rateControlMode: 'crf',
    crf: 28,
    preset: 'medium',
    tune: undefined,
    customArgs: '',
  }),
  generateCommand: (config, outputPath) => {
    const args: string[] = ['x265'];

    // Rate control
    if (config.rateControlMode === 'crf' && config.crf !== undefined) {
      args.push('--crf', config.crf.toString());
    } else if (config.rateControlMode === '2pass' && config.targetBitrate) {
      args.push('--bitrate', config.targetBitrate.toString());
      args.push('--pass', '1');
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

export default X265EncoderOptions;
