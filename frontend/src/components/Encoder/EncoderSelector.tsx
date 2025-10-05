/**
 * EncoderSelector - Dropdown to select video encoder
 */

import React from 'react';
import { EncoderRegistry } from './registry';
import { EncoderType } from '../../types/encoder';

interface EncoderSelectorProps {
  value: EncoderType;
  onChange: (encoderType: EncoderType) => void;
  registry: EncoderRegistry;
  disabled?: boolean;
}

export default function EncoderSelector({
  value,
  onChange,
  registry,
  disabled = false,
}: EncoderSelectorProps): JSX.Element {
  const encoderEntries = Object.entries(registry);

  return (
    <div className="form-group">
      <label htmlFor="encoder">Video Encoder</label>
      <select
        id="encoder"
        value={value}
        onChange={e => onChange(e.target.value as EncoderType)}
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
      <small className="form-help">
        Choose the video codec for encoding. Different encoders offer different quality/speed
        tradeoffs.
      </small>
    </div>
  );
}
