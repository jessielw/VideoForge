import React, { useState } from 'react';
import type { AudioTrack } from '../../types/mediaInfoContext';
import { AudioEncoder, AUDIO_ENCODER_OPTIONS } from '../../types/audio_encoders';

// Output track configuration (what goes in final file)
export interface OutputAudioTrack {
  id: string; // Unique ID for React keys
  sourceTrack: number; // Which source track to use
  encoder: AudioEncoder;
  bitrate: number; // kbps (ignored for copy)
  language?: string; // Language tag (eng, jpn, etc.)
  name?: string; // Track name/title
}

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

  const handleAddTrack = () => {
    const newTrack: OutputAudioTrack = {
      id: `track_${Date.now()}_${Math.random()}`,
      sourceTrack: 0,
      encoder: AUDIO_ENCODER_OPTIONS[0].value,
      bitrate: 192,
      language: undefined,
      name: undefined,
    };
    onChange([...outputTracks, newTrack]);
  };

  const handleRemoveTrack = (index: number) => {
    const newTracks = outputTracks.filter((_, i) => i !== index);
    onChange(newTracks);
  };

  const handleUpdateTrack = (index: number, updates: Partial<OutputAudioTrack>) => {
    const newTracks = [...outputTracks];
    newTracks[index] = { ...newTracks[index], ...updates };
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

    // show where it will be dropped, and reorder immediately so UI updates
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
              {/* Drop indicator above the item when dragging */}
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

          {/* If dropping at the end of the list, show indicator */}
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

// Attach modal to main export render
// ...existing code...

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
  const sourceTrack = sourceAudioTracks[track.sourceTrack];

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
            ? `Track ${track.sourceTrack + 1} (${sourceTrack.format || 'unknown'}) → ${
                track.encoder
              } ${track.encoder !== 'copy' ? `@ ${track.bitrate}kbps` : '(copy)'} `
            : 'No source'}
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

// Modal editor (rendered in parent so it has access to outputTracks and onChange)
function AudioTrackEditorModal({
  editingTrackId,
  onClose,
  outputTracks,
  onChange,
  sourceAudioTracks,
}: {
  editingTrackId: string | null;
  onClose: () => void;
  outputTracks: OutputAudioTrack[];
  onChange: (tracks: OutputAudioTrack[]) => void;
  sourceAudioTracks: AudioTrack[];
}) {
  if (!editingTrackId) return null;

  const idx = outputTracks.findIndex(t => t.id === editingTrackId);
  if (idx === -1) return null;

  const track = outputTracks[idx];
  const sourceTrack = sourceAudioTracks[track.sourceTrack];

  const [local, setLocal] = React.useState<OutputAudioTrack>({ ...track });

  const handleSave = () => {
    const newTracks = [...outputTracks];
    newTracks[idx] = { ...newTracks[idx], ...local };
    onChange(newTracks);
    onClose();
  };

  return (
    <div className="preset-dialog-overlay" onClick={onClose}>
      <div className="preset-dialog" onClick={e => e.stopPropagation()}>
        <h3>Edit Output Track #{idx + 1}</h3>
        <div className="dialog-content">
          <div className="form-group">
            <label>Source Track</label>
            <select
              value={local.sourceTrack}
              onChange={e => setLocal({ ...local, sourceTrack: parseInt(e.target.value) })}
            >
              {sourceAudioTracks.length === 0 ? (
                <option value={0}>No audio tracks in source</option>
              ) : (
                sourceAudioTracks.map((srcTrack, sidx) => (
                  <option key={sidx} value={sidx}>
                    Track {sidx + 1}: {srcTrack.format?.toUpperCase() || 'Unknown'}{' '}
                    {srcTrack.channels ? `${srcTrack.channels}ch` : ''}{' '}
                    {srcTrack.language ? `(${srcTrack.language})` : ''}
                  </option>
                ))
              )}
            </select>
          </div>

          <div className="form-group">
            <label>Encoder</label>
            <select
              value={local.encoder}
              onChange={e => setLocal({ ...local, encoder: e.target.value as any })}
            >
              {AUDIO_ENCODER_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {local.encoder !== 'copy' && (
            <div className="form-group">
              <label>Bitrate</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  value={local.bitrate}
                  onChange={e => setLocal({ ...local, bitrate: parseInt(e.target.value) || 192 })}
                  min={64}
                  max={512}
                  step={32}
                />
                <span className="unit">kbps</span>
              </div>
            </div>
          )}

          <div className="form-group">
            <label>Language (optional)</label>
            <input
              type="text"
              value={local.language || ''}
              onChange={e => setLocal({ ...local, language: e.target.value || undefined })}
              placeholder="e.g., eng, jpn, spa"
              maxLength={3}
            />
          </div>

          <div className="form-group">
            <label>Track Name (optional)</label>
            <input
              type="text"
              value={local.name || ''}
              onChange={e => setLocal({ ...local, name: e.target.value || undefined })}
              placeholder="e.g., English Stereo, Japanese 5.1, Commentary"
            />
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
