import React, { useState, useEffect } from 'react';

interface DisplayEffectsProps {
  displayEffect: 'none' | 'edge_detect';
  onEffectChange: (effect: 'none' | 'edge_detect') => void;
  onAutoCropDetect: () => void;
  autoCropDetecting: boolean;
  disabled: boolean;
  sampleCount?: number;
  onSampleCountChange?: (n: number) => void;
}

export default function DisplayEffects({
  displayEffect,
  onEffectChange,
  onAutoCropDetect,
  autoCropDetecting,
  disabled,
  sampleCount,
  onSampleCountChange,
}: DisplayEffectsProps): JSX.Element {
  // Local state so the range control always feels responsive even if the
  // parent update is delayed or rebinding occurs. Keep it in sync with the
  // optional `sampleCount` prop.
  const [localSample, setLocalSample] = useState<number>(sampleCount ?? 20);

  useEffect(() => {
    setLocalSample(sampleCount ?? 20);
  }, [sampleCount]);

  const handleSampleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    setLocalSample(v);
    if (onSampleCountChange) onSampleCountChange(v);
  };

  return (
    <div className="display-effects">
      <span className="effects-label">Display:</span>
      <button
        onClick={() => onEffectChange('none')}
        className={`effect-button ${displayEffect === 'none' ? 'active' : ''}`}
      >
        Normal
      </button>
      <button
        onClick={() => onEffectChange('edge_detect')}
        className={`effect-button ${displayEffect === 'edge_detect' ? 'active' : ''}`}
      >
        🔍 Edges
      </button>
      <div className="auto-crop-controls">
        <label className="auto-crop-button">
          <input
            type="range"
            min={10}
            max={100}
            step={2}
            value={localSample}
            onChange={handleSampleChange}
            disabled={autoCropDetecting || disabled}
            aria-label="Auto crop sample count"
            title="Auto-crop sample count — higher = more accurate, slower"
          />
          <span>{localSample}</span>
        </label>

        <button
          onClick={onAutoCropDetect}
          className="effect-button auto-crop-button"
          disabled={autoCropDetecting || disabled}
        >
          {autoCropDetecting ? '\u23f3 Detecting...' : '\u2702\ufe0f Auto Crop'}
        </button>
      </div>
    </div>
  );
}
