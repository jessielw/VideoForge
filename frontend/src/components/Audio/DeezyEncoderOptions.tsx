import { DeezyConfig } from '../../types/audio';
import {
  DEEZY_AC4_CHANNELS,
  DEEZY_ATMOS_MODES,
  DEEZY_CODEC_FORMATS,
  DEEZY_DD_CHANNELS,
  DEEZY_DDP_CHANNELS,
  DEEZY_DRC_PROFILES,
  DEEZY_STEREO_DOWNMIX,
  getDDChannelByValue,
  getDDPChannelByValue,
  getValidBitratesForAC4,
  getValidBitratesForAtmos,
  getValidBitratesForDD,
  getValidBitratesForDDP,
} from '../../constants/audio/deezy';

interface DeezyEncoderOptionsProps {
  config: DeezyConfig;
  onChange: (config: DeezyConfig) => void;
}

/**
 * DeeZy encoder configuration UI
 * Handles all DeeZy formats: DD, DDP, Atmos, AC-4
 *
 * Uses static constants from constants/audio/deezy.ts which mirror backend enums.
 */
export default function DeezyEncoderOptions({ config, onChange }: DeezyEncoderOptionsProps) {
  const handleFormatChange = (newFormat: string) => {
    // Build a clean base config with only common DeeZy fields
    // Preserves: encoder_type, source_track, language, custom_args, and DeeZy-specific options
    const baseConfig = {
      encoder_type: 'deezy' as const,
      source_track: config.source_track ?? 0,
      language: config.language,
      custom_args: config.custom_args,
      // Common DeeZy options (preserved across format changes)
      stereo_downmix: config.stereo_downmix,
      drc_line_mode: config.drc_line_mode,
      drc_rf_mode: config.drc_rf_mode,
      dialnorm: config.dialnorm ?? 0,
    };

    let newConfig: DeezyConfig;

    // Build format-specific config from scratch (no spreading old format-specific fields)
    if (newFormat === 'dd') {
      newConfig = {
        ...baseConfig,
        codec_format: 'dd',
        channels: 6,
        bitrate: 448,
      };
    } else if (newFormat === 'ddp') {
      newConfig = {
        ...baseConfig,
        codec_format: 'ddp',
        channels: 6,
        bitrate: 448,
      };
    } else if (newFormat === 'atmos') {
      newConfig = {
        ...baseConfig,
        codec_format: 'atmos',
        atmos_mode: 'streaming',
        bitrate: 768,
      };
    } else if (newFormat === 'ac4') {
      newConfig = {
        ...baseConfig,
        codec_format: 'ac4',
        channels: 'immersive_stereo',
        bitrate: 256,
      };
    } else {
      return;
    }

    onChange(newConfig);
  };

  return (
    <>
      {/* Codec Format Selector */}
      <div className="form-group">
        <label>Codec Format</label>
        <select value={config.codec_format} onChange={e => handleFormatChange(e.target.value)}>
          {Object.entries(DEEZY_CODEC_FORMATS).map(([formatId, formatMeta]) => (
            <option key={formatId} value={formatId}>
              {formatMeta.displayName}
            </option>
          ))}
        </select>
      </div>

      {/* Format-specific options */}
      {(config.codec_format === 'dd' || config.codec_format === 'ddp') && (
        <DDPOptions config={config} onChange={onChange} />
      )}

      {config.codec_format === 'atmos' && <AtmosOptions config={config} onChange={onChange} />}

      {config.codec_format === 'ac4' && <AC4Options config={config} onChange={onChange} />}

      {/* Common DeeZy Options */}
      <CommonDeezyOptions config={config} onChange={onChange} />
    </>
  );
}

// ============================================================================
// DD/DDP Options
// ============================================================================

interface DDPOptionsProps {
  config: DeezyConfig;
  onChange: (config: DeezyConfig) => void;
}

function DDPOptions({ config, onChange }: DDPOptionsProps) {
  const channels = (config as any).channels as number;
  const bitrate = (config as any).bitrate as number | null;
  const isDD = config.codec_format === 'dd';

  const CHANNELS = isDD ? DEEZY_DD_CHANNELS : DEEZY_DDP_CHANNELS;
  const getChannelInfo = isDD ? getDDChannelByValue : getDDPChannelByValue;
  const getValidBitrates = isDD ? getValidBitratesForDD : getValidBitratesForDDP;

  const validBitrates = getValidBitrates(channels);

  return (
    <>
      <div className="form-group">
        <label>Channels</label>
        <select
          value={channels}
          onChange={e => {
            const newChannels = parseInt(e.target.value);
            const newChannelInfo = getChannelInfo(newChannels);
            const newBitrate = newChannelInfo?.defaultBitrate || bitrate;
            onChange({ ...config, channels: newChannels, bitrate: newBitrate } as any);
          }}
        >
          {Object.values(CHANNELS).map(ch => (
            <option key={ch.value} value={ch.value} title={ch.description}>
              {ch.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label>Bitrate</label>
        {validBitrates.length > 0 ? (
          <select
            value={bitrate ?? ''}
            onChange={e => onChange({ ...config, bitrate: parseInt(e.target.value) || null })}
          >
            {bitrate === null && <option value="">Auto</option>}
            {[...validBitrates].map(br => (
              <option key={br} value={br}>
                {br} kbps
              </option>
            ))}
          </select>
        ) : (
          <input type="text" value="Auto" disabled />
        )}
      </div>
    </>
  );
}

// ============================================================================
// Atmos Options
// ============================================================================

interface AtmosOptionsProps {
  config: DeezyConfig;
  onChange: (config: DeezyConfig) => void;
}

function AtmosOptions({ config, onChange }: AtmosOptionsProps) {
  const atmosMode = (config as any).atmos_mode as string;
  const bitrate = (config as any).bitrate as number;

  const validBitrates = getValidBitratesForAtmos(atmosMode);

  return (
    <>
      <div className="form-group">
        <label>Mode</label>
        <select
          value={atmosMode}
          onChange={e => {
            const newMode = e.target.value;
            const modeInfo = Object.values(DEEZY_ATMOS_MODES).find(m => m.value === newMode);
            const newBitrate = modeInfo?.defaultBitrate ?? bitrate;
            onChange({ ...config, atmos_mode: newMode, bitrate: newBitrate } as any);
          }}
        >
          {Object.values(DEEZY_ATMOS_MODES).map(mode => (
            <option key={mode.value} value={mode.value} title={mode.description}>
              {mode.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label>Bitrate</label>
        <select
          value={bitrate}
          onChange={e => onChange({ ...config, bitrate: parseInt(e.target.value) } as any)}
        >
          {[...validBitrates].map(br => (
            <option key={br} value={br}>
              {br} kbps
            </option>
          ))}
        </select>
      </div>
    </>
  );
}

// ============================================================================
// AC-4 Options
// ============================================================================

interface AC4OptionsProps {
  config: DeezyConfig;
  onChange: (config: DeezyConfig) => void;
}

function AC4Options({ config, onChange }: AC4OptionsProps) {
  const bitrate = (config as any).bitrate as number;
  const validBitrates = getValidBitratesForAC4();

  return (
    <>
      <div className="form-group">
        <label>Channels</label>
        <input
          type="text"
          value={DEEZY_AC4_CHANNELS.IMMERSIVE_STEREO.label}
          disabled
          title={DEEZY_AC4_CHANNELS.IMMERSIVE_STEREO.description}
        />
      </div>

      <div className="form-group">
        <label>Bitrate</label>
        <select
          value={bitrate}
          onChange={e => onChange({ ...config, bitrate: parseInt(e.target.value) } as any)}
        >
          {[...validBitrates].map(br => (
            <option key={br} value={br}>
              {br} kbps
            </option>
          ))}
        </select>
      </div>
    </>
  );
}

// ============================================================================
// Common DeeZy Options (DRC, Downmix, Dialnorm)
// ============================================================================

interface CommonDeezyOptionsProps {
  config: DeezyConfig;
  onChange: (config: DeezyConfig) => void;
}

function CommonDeezyOptions({ config, onChange }: CommonDeezyOptionsProps) {
  // Only show stereo downmix for DD/DDP (not Atmos or AC4)
  const showStereoDownmix = config.codec_format === 'dd' || config.codec_format === 'ddp';

  return (
    <>
      {showStereoDownmix && (
        <div className="form-group">
          <label>Stereo Downmix</label>
          <select
            value={config.stereo_downmix || 'loro'}
            onChange={e =>
              onChange({ ...config, stereo_downmix: e.target.value || undefined } as any)
            }
          >
            {Object.values(DEEZY_STEREO_DOWNMIX).map(option => (
              <option key={option.value} value={option.value} title={option.description}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="form-group">
        <label>DRC Line Mode</label>
        <select
          value={config.drc_line_mode || DEEZY_DRC_PROFILES.FILM_LIGHT.value}
          onChange={e => onChange({ ...config, drc_line_mode: e.target.value || undefined } as any)}
        >
          {Object.values(DEEZY_DRC_PROFILES).map(profile => (
            <option key={profile.value} value={profile.value} title={profile.description}>
              {profile.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label>DRC RF Mode</label>
        <select
          value={config.drc_rf_mode || DEEZY_DRC_PROFILES.FILM_LIGHT.value}
          onChange={e => onChange({ ...config, drc_rf_mode: e.target.value || undefined } as any)}
        >
          {Object.values(DEEZY_DRC_PROFILES).map(profile => (
            <option key={profile.value} value={profile.value} title={profile.description}>
              {profile.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label>Dialog Normalization</label>
        <div className="input-with-unit">
          <input
            type="number"
            value={config.dialnorm ?? 0}
            onChange={e => onChange({ ...config, dialnorm: parseInt(e.target.value) })}
            min={-31}
            max={0}
          />
          <span className="unit">dB</span>
        </div>
        <small>Valid range: -31 to 0 dB</small>
      </div>
    </>
  );
}
