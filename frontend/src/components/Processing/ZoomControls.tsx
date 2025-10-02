import React from 'react';

interface ZoomControlsProps {
  zoomLevel: number;
  onZoomChange: (zoom: number) => void;
}

export default function ZoomControls({ zoomLevel, onZoomChange }: ZoomControlsProps): JSX.Element {
  const zoomLevels = [100, 150, 200, 300, 400, 500, 600, 700, 800];

  return (
    <div className="zoom-controls">
      <button
        onClick={() => onZoomChange(100)}
        className={`zoom-button ${zoomLevel === 100 ? 'active' : ''}`}
      >
        Fit
      </button>
      {zoomLevels.slice(1).map(level => (
        <button
          key={level}
          onClick={() => onZoomChange(level)}
          className={`zoom-button ${zoomLevel === level ? 'active' : ''}`}
        >
          {level}%
        </button>
      ))}
      <span className="zoom-info">{zoomLevel}%</span>
    </div>
  );
}
