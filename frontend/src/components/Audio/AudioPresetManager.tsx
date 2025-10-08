/**
 * AudioPresetManager - Manage audio encoder presets (save/load/delete)
 */

import React, { useState, useEffect } from 'react';
import { AudioEncoderConfig } from '../../types/audio';

interface AudioPreset {
  id: string;
  name: string;
  description: string;
  config: AudioEncoderConfig;
  isBuiltin: boolean;
  createdAt: string;
  updatedAt: string;
}

interface AudioPresetManagerProps {
  currentConfig: AudioEncoderConfig;
  onLoadPreset: (config: AudioEncoderConfig) => void;
}

export default function AudioPresetManager({
  currentConfig,
  onLoadPreset,
}: AudioPresetManagerProps): JSX.Element {
  const [presets, setPresets] = useState<AudioPreset[]>([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [presetName, setPresetName] = useState('');
  const [presetDescription, setPresetDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch presets from backend
  const fetchPresets = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/presets/audio');
      const data = await response.json();
      if (data.ok) {
        setPresets(data.presets);
      } else {
        setError('Failed to load presets');
      }
    } catch (err) {
      console.error('Failed to fetch audio presets:', err);
      setError('Network error');
    }
  };

  useEffect(() => {
    fetchPresets();
  }, []);

  const handleSavePreset = async () => {
    if (!presetName.trim()) {
      alert('Please enter a preset name');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/presets/audio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: presetName,
          description: presetDescription,
          config: currentConfig,
        }),
      });

      const result = await response.json();
      if (result.ok) {
        setShowSaveDialog(false);
        setPresetName('');
        setPresetDescription('');
        fetchPresets(); // Refresh list
        alert(`✅ Preset "${presetName}" saved successfully`);
      } else {
        alert(`❌ Failed to save preset: ${result.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to save preset:', err);
      alert('❌ Failed to save preset');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadPreset = (preset: AudioPreset) => {
    onLoadPreset(preset.config);
    alert(`✅ Loaded preset: ${preset.name}`);
  };

  const handleDeletePreset = async (presetId: string, presetName: string) => {
    if (!confirm(`Delete preset "${presetName}"?`)) return;

    try {
      const response = await fetch(`http://localhost:8000/api/presets/audio/${presetId}`, {
        method: 'DELETE',
      });

      const result = await response.json();
      if (result.ok) {
        fetchPresets(); // Refresh list
        alert(`✅ Preset "${presetName}" deleted`);
      } else {
        alert(`❌ Failed to delete preset: ${result.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to delete preset:', err);
      alert('❌ Failed to delete preset');
    }
  };

  return (
    <div className="audio-preset-manager">
      <div className="preset-header">
        <h3>Audio Presets</h3>
        <button className="save-preset-btn" onClick={() => setShowSaveDialog(true)}>
          💾 Save Current Settings
        </button>
      </div>

      {error && <div className="preset-error">{error}</div>}

      {/* Preset List */}
      <div className="preset-list">
        {presets.length === 0 ? (
          <div className="no-presets">
            No saved presets. Save your current settings to create one!
          </div>
        ) : (
          presets.map(preset => (
            <div key={preset.id} className="preset-item">
              <div className="preset-info">
                <div className="preset-name">
                  {preset.name}
                  {preset.isBuiltin && <span className="builtin-badge">Built-in</span>}
                </div>
                <div className="preset-description">{preset.description}</div>
                <div className="preset-details">
                  Encoder: {preset.config.encoderType}
                  {'bitrate' in preset.config && ` • Bitrate: ${preset.config.bitrate} kbps`}
                </div>
              </div>
              <div className="preset-actions">
                <button
                  className="load-preset-btn"
                  onClick={() => handleLoadPreset(preset)}
                  title="Load this preset"
                >
                  📂 Load
                </button>
                {!preset.isBuiltin && (
                  <button
                    className="delete-preset-btn"
                    onClick={() => handleDeletePreset(preset.id, preset.name)}
                    title="Delete this preset"
                  >
                    🗑️
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Save Dialog */}
      {showSaveDialog && (
        <div className="preset-dialog-overlay" onClick={() => setShowSaveDialog(false)}>
          <div className="preset-dialog" onClick={e => e.stopPropagation()}>
            <h3>Save Audio Preset</h3>
            <div className="dialog-content">
              <div className="form-group">
                <label>Preset Name *</label>
                <input
                  type="text"
                  value={presetName}
                  onChange={e => setPresetName(e.target.value)}
                  placeholder="e.g., AC3 5.1 Surround 640kbps"
                  maxLength={100}
                />
              </div>
              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={presetDescription}
                  onChange={e => setPresetDescription(e.target.value)}
                  placeholder="Optional description..."
                  rows={3}
                  maxLength={500}
                />
              </div>
              <div className="current-settings">
                <strong>Current Settings:</strong>
                <div>Encoder: {currentConfig.encoderType}</div>
                {'bitrate' in currentConfig && <div>Bitrate: {currentConfig.bitrate} kbps</div>}
                <div>Source Track: {currentConfig.sourceTrack}</div>
              </div>
            </div>
            <div className="dialog-actions">
              <button
                className="cancel-btn"
                onClick={() => setShowSaveDialog(false)}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                className="save-btn"
                onClick={handleSavePreset}
                disabled={loading || !presetName.trim()}
              >
                {loading ? 'Saving...' : 'Save Preset'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
