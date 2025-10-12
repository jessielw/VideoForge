import React, { useEffect, useState } from 'react';

import logger from '../../utils/logger';
import DeezyEncoderOptions from './DeezyEncoderOptions';
import { fetchEncoderAvailability } from '../../api/audio';
import { AudioTrack } from '../../types/mediaInfoContext';
import {
  getAtmosModeByValue,
  getDDChannelByValue,
  getDDPChannelByValue,
} from '../../constants/audio/deezy';
import {
  AudioEncoderConfig,
  CopyConfig,
  DeezyConfig,
  EncoderAvailabilityResponse,
  OutputAudioTrack,
} from '../../types/audio';

interface AudioTrackManagerProps {
  sourceAudioTracks: AudioTrack[]; // Detected from source file
  outputTracks: OutputAudioTrack[];
  onChange: (tracks: OutputAudioTrack[]) => void;
}

export default function AudioTrackManager({
  sourceAudioTracks,
  outputTracks,
  onChange,
}: AudioTrackManagerProps): JSX.Element {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const [editingTrackId, setEditingTrackId] = useState<string | null>(null);
  const [availability, setAvailability] = useState<EncoderAvailabilityResponse | null>(null);
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(true);

  // Fetch encoder availability on mount
  useEffect(() => {
    fetchEncoderAvailability()
      .then(avail => {
        setAvailability(avail);
        setIsLoadingAvailability(false);
      })
      .catch(err => {
        logger.error('Failed to load encoder availability:', err);
        setIsLoadingAvailability(false);
      });
  }, []);

  const handleAddTrack = () => {
    if (!availability) return;

    let defaultConfig: AudioEncoderConfig;

    // Check if DeeZy is available, otherwise fall back to copy
    if (availability.availability.deezy) {
      // Default to DD 5.1 @ 448kbps
      defaultConfig = {
        encoder_type: 'deezy',
        codec_format: 'dd',
        source_track: 0,
        channels: 6,
        bitrate: 448,
        dialnorm: 0,
        language: sourceAudioTracks?.[0]?.language,
        title: sourceAudioTracks?.[0]?.title,
      };
    } else {
      // Fallback to copy (always available)
      defaultConfig = {
        encoder_type: 'copy',
        source_track: 0,
        language: sourceAudioTracks?.[0]?.language,
        title: sourceAudioTracks?.[0]?.title,
      } as CopyConfig;
    }
    logger.debug('Adding new track with default config:', JSON.stringify(defaultConfig, null, 2));

    const newTrack: OutputAudioTrack = {
      id: `track_${Date.now()}_${Math.random()}`,
      config: defaultConfig,
    };

    onChange([...outputTracks, newTrack]);
  };

  const handleRemoveTrack = (index: number) => {
    const newTracks = outputTracks.filter((_, i) => i !== index);
    onChange(newTracks);
  };

  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) {
      setDropIndex(index);
      return;
    }

    setDropIndex(index);
    const newTracks = [...outputTracks];
    const draggedTrack = newTracks[draggedIndex];
    newTracks.splice(draggedIndex, 1);
    newTracks.splice(index, 0, draggedTrack);

    setDraggedIndex(index);
    onChange(newTracks);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    setDropIndex(null);
  };

  if (isLoadingAvailability) {
    return (
      <div className="audio-track-manager">
        <div className="audio-track-manager__header">
          <h3>Audio Tracks</h3>
        </div>
        <div className="audio-track-manager__loading">Checking encoder availability...</div>
      </div>
    );
  }

  if (!availability) {
    return (
      <div className="audio-track-manager">
        <div className="audio-track-manager__header">
          <h3>Audio Tracks</h3>
        </div>
        <div className="audio-track-manager__error">
          Failed to check encoder availability. Please check backend connection.
        </div>
      </div>
    );
  }

  return (
    <div className="audio-track-manager">
      <div className="audio-track-manager__header">
        <h3>Audio Tracks</h3>
        <button className="themed-btn" onClick={handleAddTrack} type="button">
          <span>+</span> Add Track
        </button>
      </div>

      {outputTracks.length === 0 ? (
        <div className="audio-track-manager__empty">
          <p>No audio tracks configured. Click "Add Track" to add an audio track to the output.</p>
        </div>
      ) : (
        <div className="audio-track-manager__list">
          {outputTracks.map((track, index) => (
            <React.Fragment key={track.id}>
              {draggedIndex !== null && dropIndex === index && (
                <div className="audio-track-drop-indicator" />
              )}

              <AudioTrackCard
                track={track}
                index={index}
                sourceAudioTracks={sourceAudioTracks}
                onRemove={() => handleRemoveTrack(index)}
                onDragStart={() => handleDragStart(index)}
                onDragOver={e => handleDragOver(e, index)}
                onDragEnd={handleDragEnd}
                isDragging={draggedIndex === index}
                onEdit={() => setEditingTrackId(track.id)}
              />
            </React.Fragment>
          ))}

          {draggedIndex !== null && dropIndex === outputTracks.length && (
            <div className="audio-track-drop-indicator" />
          )}
        </div>
      )}

      {editingTrackId && (
        <AudioTrackEditorModal
          editingTrackId={editingTrackId}
          onClose={() => setEditingTrackId(null)}
          outputTracks={outputTracks}
          onChange={onChange}
          sourceAudioTracks={sourceAudioTracks}
        />
      )}
    </div>
  );
}

// ============================================================================
// AudioTrackCard Component
// ============================================================================

interface AudioTrackCardProps {
  track: OutputAudioTrack;
  index: number;
  sourceAudioTracks: AudioTrack[];
  onRemove: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  isDragging: boolean;
  onEdit?: () => void;
}

function AudioTrackCard({
  track,
  index,
  sourceAudioTracks,
  onRemove,
  onDragStart,
  onDragOver,
  onDragEnd,
  isDragging,
  onEdit,
}: AudioTrackCardProps): JSX.Element {
  const sourceTrack = sourceAudioTracks[track.config.source_track];
  const encoderLabel = getEncoderSummary(track.config);

  return (
    <div
      className={`audio-track-card ${isDragging ? 'dragging' : ''}`}
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
    >
      <div className="audio-track-card__header">
        <div className="audio-track-card__drag-handle">
          <span>⋮⋮</span>
        </div>
        <div className="audio-track-card__title">
          <strong>Output Track #{index + 1}</strong>
        </div>
        <div className="audio-track-card__collapsed-summary">
          {sourceTrack
            ? `Track ${track.config.source_track + 1} (${
                sourceTrack.format || 'unknown'
              }) → ${encoderLabel}`
            : `Track ${track.config.source_track + 1} → ${encoderLabel}`}
        </div>
        <button className="themed-btn-icon" onClick={onEdit} type="button" title="Edit in modal">
          ✎
        </button>
        <button className="themed-btn-icon" onClick={onRemove} type="button" title="Remove track">
          ✕
        </button>
      </div>
    </div>
  );
}

// ============================================================================
// Helper Functions
// ============================================================================

function getEncoderSummary(config: AudioEncoderConfig): string {
  if (config.encoder_type === 'copy') {
    return 'Copy (no re-encode)';
  }

  if (config.encoder_type === 'deezy') {
    const deezyConfig = config as DeezyConfig;
    const format = deezyConfig.codec_format.toUpperCase();

    if (deezyConfig.codec_format === 'dd') {
      const channelConfig = getDDChannelByValue(deezyConfig.channels);
      const channelLabel = channelConfig?.label ?? String(deezyConfig.channels);
      const bitrate = deezyConfig.bitrate !== null ? `${deezyConfig.bitrate}kbps` : 'Auto';
      return `${format} ${channelLabel} @ ${bitrate}`;
    }

    if (deezyConfig.codec_format === 'ddp') {
      const channelConfig = getDDPChannelByValue(deezyConfig.channels);
      const channelLabel = channelConfig?.label ?? String(deezyConfig.channels);
      const bitrate = deezyConfig.bitrate !== null ? `${deezyConfig.bitrate}kbps` : 'Auto';
      return `${format} ${channelLabel} @ ${bitrate}`;
    }

    if (deezyConfig.codec_format === 'atmos') {
      const modeConfig = getAtmosModeByValue(deezyConfig.atmos_mode);
      const modeLabel = modeConfig?.label ?? deezyConfig.atmos_mode;
      return `Atmos ${modeLabel} @ ${deezyConfig.bitrate}kbps`;
    }

    if (deezyConfig.codec_format === 'ac4') {
      return `AC-4 Immersive Stereo @ ${deezyConfig.bitrate}kbps`;
    }
  }

  return 'Unknown';
}

// ============================================================================
// AudioTrackEditorModal Component
// ============================================================================

interface AudioTrackEditorModalProps {
  editingTrackId: string | null;
  onClose: () => void;
  outputTracks: OutputAudioTrack[];
  onChange: (tracks: OutputAudioTrack[]) => void;
  sourceAudioTracks: AudioTrack[];
}

function AudioTrackEditorModal({
  editingTrackId,
  onClose,
  outputTracks,
  onChange,
  sourceAudioTracks,
}: AudioTrackEditorModalProps) {
  if (!editingTrackId) return null;

  const idx = outputTracks.findIndex(t => t.id === editingTrackId);
  if (idx === -1) return null;

  const track = outputTracks[idx];
  const [local, setLocal] = React.useState<OutputAudioTrack>({ ...track });

  const handleSave = () => {
    logger.debug('Saving track config:', JSON.stringify(local.config, null, 2));
    const newTracks = [...outputTracks];
    newTracks[idx] = local;
    onChange(newTracks);
    onClose();
  };

  const handleEncoderChange = (newEncoderType: string) => {
    let newConfig: AudioEncoderConfig;

    if (newEncoderType === 'copy') {
      newConfig = {
        encoder_type: 'copy',
        source_track: local.config.source_track,
        language: local.config.language,
        title: local.config.title,
      } as CopyConfig;
    } else if (newEncoderType === 'deezy') {
      // Default to DD 5.1 @ 448kbps
      newConfig = {
        encoder_type: 'deezy',
        codec_format: 'dd',
        source_track: local.config.source_track,
        language: local.config.language,
        title: local.config.title,
        channels: 6,
        bitrate: 448,
        dialnorm: 0,
      };
    } else {
      return; // Unknown encoder
    }

    setLocal({ ...local, config: newConfig });
  };

  return (
    <div className="preset-dialog-overlay" onClick={onClose}>
      <div className="preset-dialog audio-editor-modal" onClick={e => e.stopPropagation()}>
        <h3>Edit Output Track #{idx + 1}</h3>
        <div className="dialog-content">
          {/* Source Track Selection */}
          <div className="form-group">
            <label>Source Track</label>
            <select
              value={local.config.source_track}
              onChange={e => {
                const newSrcTrackNum = parseInt(e.target.value);
                const newConfig = {
                  ...local.config,
                  source_track: newSrcTrackNum,
                  language: sourceAudioTracks?.[newSrcTrackNum]?.language,
                  title: sourceAudioTracks?.[newSrcTrackNum]?.title,
                };
                logger.debug('After source_track change:', JSON.stringify(newConfig, null, 2));
                setLocal({
                  ...local,
                  config: newConfig,
                });
              }}
            >
              {sourceAudioTracks.length === 0 ? (
                <option value={0}>No audio tracks in source</option>
              ) : (
                sourceAudioTracks.map((srcTrack, sIDX) => (
                  <option key={sIDX} value={sIDX}>
                    Track {sIDX + 1}: {srcTrack.format?.toUpperCase() || 'Unknown'}{' '}
                    {srcTrack.channels ? `${srcTrack.channels}ch` : ''}{' '}
                    {srcTrack.language ? `(${srcTrack.language})` : ''}
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Encoder Type Selection */}
          <div className="form-group">
            <label>Encoder</label>
            <select
              value={local.config.encoder_type}
              onChange={e => handleEncoderChange(e.target.value)}
            >
              <option value="copy">Copy (No Re-encode)</option>
              <option value="deezy">DeeZy (Professional Dolby Encoding)</option>
            </select>
          </div>

          {/* DeeZy-specific options */}
          {local.config.encoder_type === 'deezy' && (
            <DeezyEncoderOptions
              config={local.config as DeezyConfig}
              onChange={newConfig => setLocal({ ...local, config: newConfig })}
            />
          )}

          {/* Language */}
          <div className="form-group">
            <label>Language (optional)</label>
            <input
              type="text"
              value={local.config.language || ''}
              onChange={e =>
                setLocal({
                  ...local,
                  config: { ...local.config, language: e.target.value || undefined },
                })
              }
              placeholder="e.g., eng, jpn, spa"
              maxLength={3}
            />
          </div>

          {/* Title */}
          <div className="form-group">
            <label>Track Title (optional)</label>
            <input
              type="text"
              value={local.config.title || ''}
              onChange={e =>
                setLocal({
                  ...local,
                  config: { ...local.config, title: e.target.value || undefined },
                })
              }
              placeholder="e.g., English Stereo, Japanese 5.1, Commentary"
            />
          </div>

          {/* Custom Arguments */}
          <div className="form-group">
            <label>Custom Arguments (optional)</label>
            <input
              type="text"
              value={local.config.custom_args || ''}
              onChange={e =>
                setLocal({
                  ...local,
                  config: { ...local.config, custom_args: e.target.value || undefined },
                })
              }
              placeholder="e.g., --extra-flag value"
            />
            <small>Additional command line arguments to append to the encoder command</small>
          </div>
        </div>

        <div className="dialog-actions">
          <button className="themed-btn" onClick={onClose}>
            Cancel
          </button>
          <button className="themed-btn" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export type { OutputAudioTrack };
