/**
 * AudioEncoderSelector - Dropdown to select audio encoder
 */

import React from 'react';
import { AudioEncoderRegistry } from './registry';
import { AudioEncoderType } from '../../types/audio';

interface AudioEncoderSelectorProps {
  value: AudioEncoderType;
  onChange: (encoderType: AudioEncoderType) => void;
  registry: AudioEncoderRegistry;
  disabled?: boolean;
}

export default function AudioEncoderSelector({
  value,
  onChange,
  registry,
  disabled = false,
}: AudioEncoderSelectorProps): JSX.Element {
  const encoderEntries = Object.entries(registry);

  return (
    <div className="form-group">
      <label htmlFor="audio-encoder">Audio Encoder</label>
      <select
        id="audio-encoder"
        value={value}
        onChange={e => onChange(e.target.value as AudioEncoderType)}
        className="form-control"
        disabled={disabled}
      >
        {encoderEntries.map(([type, plugin]) => (
          <option key={type} value={type}>
            {plugin.icon && `${plugin.icon} `}
            {plugin.displayName} — {plugin.description}
          </option>
        ))}
      </select>
      <small className="form-help">Choose the audio codec for encoding.</small>
    </div>
  );
}
