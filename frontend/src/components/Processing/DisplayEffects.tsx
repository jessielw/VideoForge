import React from 'react';

interface DisplayEffectsProps {
  displayEffect: 'none' | 'edge_detect';
  onEffectChange: (effect: 'none' | 'edge_detect') => void;
  onAutoCropDetect: () => void;
  autoCropDetecting: boolean;
  disabled: boolean;
}

export default function DisplayEffects({ 
  displayEffect, 
  onEffectChange, 
  onAutoCropDetect, 
  autoCropDetecting, 
  disabled 
}: DisplayEffectsProps): JSX.Element {
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
      <button 
        onClick={onAutoCropDetect}
        className="effect-button auto-crop-button"
        disabled={autoCropDetecting || disabled}
      >
        {autoCropDetecting ? '⏳ Detecting...' : '✂️ Auto Crop'}
      </button>
    </div>
  );
}