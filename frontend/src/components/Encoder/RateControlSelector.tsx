/**
 * RateControlSelector - Common rate control mode selector
 */

import React from 'react';
import { RateControlMode } from '../../types/encoder';

interface RateControlSelectorProps {
  mode: RateControlMode;
  onChange: (mode: RateControlMode) => void;
  supportedModes: RateControlMode[];
  disabled?: boolean;
}

const RATE_CONTROL_INFO: Record<RateControlMode, { label: string; description: string }> = {
  crf: {
    label: 'CRF (Constant Rate Factor)',
    description: 'Best quality - adjusts bitrate dynamically',
  },
  '2pass': {
    label: '2-Pass Encoding',
    description: 'Target file size - analyzes video twice',
  },
  bitrate: {
    label: 'Single-Pass Bitrate',
    description: 'Target bitrate - one pass encoding',
  },
  vbr: {
    label: 'VBR (Variable Bitrate)',
    description: 'Variable bitrate within constraints',
  },
  cbr: {
    label: 'CBR (Constant Bitrate)',
    description: 'Fixed bitrate - for streaming',
  },
  cq: {
    label: 'CQ (Constant Quality)',
    description: 'GPU constant quality mode',
  },
  lossless: {
    label: 'Lossless',
    description: 'No quality loss - large files',
  },
};

export default function RateControlSelector({
  mode,
  onChange,
  supportedModes,
  disabled = false,
}: RateControlSelectorProps): JSX.Element {
  if (supportedModes.length === 0) {
    return <></>;
  }

  return (
    <div className="form-group">
      <label htmlFor="rate-control">Rate Control Mode</label>
      <div className="radio-group">
        {supportedModes.map(m => {
          const info = RATE_CONTROL_INFO[m];
          return (
            <label key={m} className="radio-label">
              <input
                type="radio"
                name="rate-control"
                value={m}
                checked={mode === m}
                onChange={e => onChange(e.target.value as RateControlMode)}
                disabled={disabled}
              />
              <span>
                <strong>{info.label}</strong>
                <br />
                <small>{info.description}</small>
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
