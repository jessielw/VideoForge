/**
 * EncoderPresetManager - UI for loading, saving, and deleting encoder presets
 */

import React, { useState } from 'react';
import { EncoderPreset } from '../../types/encoder';

interface EncoderPresetManagerProps {
  presets: EncoderPreset[];
  selectedPresetId?: string;
  onLoad: (presetId: string) => void;
  onSave: (name: string, description: string) => void;
  onDelete: (presetId: string) => void;
  isLoading?: boolean;
}

export default function EncoderPresetManager({
  presets,
  selectedPresetId,
  onLoad,
  onSave,
  onDelete,
  isLoading = false,
}: EncoderPresetManagerProps): JSX.Element {
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [newPresetName, setNewPresetName] = useState('');
  const [newPresetDescription, setNewPresetDescription] = useState('');

  const handleSaveClick = () => {
    if (!newPresetName.trim()) {
      alert('Please enter a preset name');
      return;
    }

    onSave(newPresetName.trim(), newPresetDescription.trim());
    setNewPresetName('');
    setNewPresetDescription('');
    setShowSaveDialog(false);
  };

  const handleDeleteClick = (presetId: string, presetName: string) => {
    if (confirm(`Delete preset "${presetName}"?`)) {
      onDelete(presetId);
    }
  };

  // Separate built-in and custom presets
  const builtInPresets = presets.filter(p => p.isBuiltIn);
  const customPresets = presets.filter(p => !p.isBuiltIn);

  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="preset-manager">
      <div className="preset-manager-header">
        <button className="preset-manager-toggle" onClick={() => setIsExpanded(!isExpanded)}>
          <span className="toggle-icon">{isExpanded ? '▼' : '▶'}</span>
          <h3>Encoder Presets</h3>
        </button>
        <button
          className="btn-save-preset"
          onClick={() => setShowSaveDialog(!showSaveDialog)}
          title="Save current settings as a new preset"
        >
          {showSaveDialog ? '✕ Cancel' : '+ Save Preset'}
        </button>
      </div>

      {isExpanded && (
        <>
          {showSaveDialog && (
            <div className="preset-save-dialog">
              <input
                type="text"
                id="preset-name"
                value={newPresetName}
                onChange={e => setNewPresetName(e.target.value)}
                className="preset-name-input"
                placeholder="Preset name..."
                autoFocus
              />
              <input
                type="text"
                id="preset-description"
                value={newPresetDescription}
                onChange={e => setNewPresetDescription(e.target.value)}
                className="preset-description-input"
                placeholder="Description (optional)..."
              />
              <button className="btn-save-confirm" onClick={handleSaveClick}>
                Save
              </button>
            </div>
          )}

          <div className="preset-grid">
            {isLoading ? (
              <div className="preset-loading">Loading presets...</div>
            ) : (
              builtInPresets.map(preset => (
                <button
                  key={preset.id}
                  className={`preset-card ${selectedPresetId === preset.id ? 'selected' : ''}`}
                  onClick={() => onLoad(preset.id)}
                >
                  <div className="preset-card-header">
                    <span className="preset-card-name">{preset.name}</span>
                    <span className="preset-card-badge">Built-in</span>
                  </div>
                  <div className="preset-card-details">
                    {preset.encoder.toUpperCase()} •{' '}
                    {preset.mode === 'crf' ? `CRF ${preset.crf}` : `${preset.bitrate}kbps`} •{' '}
                    {preset.preset}
                  </div>
                  {preset.description && (
                    <div className="preset-card-description">{preset.description}</div>
                  )}
                </button>
              ))
            )}

            {customPresets.map(preset => (
              <div key={preset.id} className="preset-card-wrapper">
                <button
                  className={`preset-card preset-card-custom ${selectedPresetId === preset.id ? 'selected' : ''}`}
                  onClick={() => onLoad(preset.id)}
                >
                  <div className="preset-card-header">
                    <span className="preset-card-name">{preset.name}</span>
                  </div>
                  <div className="preset-card-details">
                    {preset.encoder.toUpperCase()} •{' '}
                    {preset.mode === 'crf' ? `CRF ${preset.crf}` : `${preset.bitrate}kbps`} •{' '}
                    {preset.preset}
                  </div>
                  {preset.description && (
                    <div className="preset-card-description">{preset.description}</div>
                  )}
                </button>
                <button
                  className="preset-delete-btn"
                  onClick={() => handleDeleteClick(preset.id, preset.name)}
                  title="Delete preset"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>

          {presets.length === 0 && (
            <div className="preset-empty">
              <p>No presets available. Save your first preset above!</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
