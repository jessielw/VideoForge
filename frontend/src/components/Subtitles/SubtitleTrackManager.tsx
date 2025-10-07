/**
 * SubtitleTrackManager - Multi-track subtitle management UI
 * 
 * Features:
 * - Add multiple subtitle tracks from source
 * - Configure each track independently (mode, language, name, flags)
 * - Reorder tracks via drag & drop
 * - Remove tracks
 * - Modes: Copy (embed), Extract (external .srt), Burn (hardcode into video)
 */

import React, { useState } from 'react';
import { SubtitleTrack } from '../../context/MediaInfoContext';

// Output subtitle track configuration
export interface OutputSubtitleTrack {
  id: string; // Unique ID for React keys
  sourceTrack: number; // Which source track to use
  mode: 'copy' | 'extract' | 'burn'; // Processing mode
  language?: string; // Language tag (eng, jpn, etc.)
  name?: string; // Track name/title
  forced?: boolean; // Forced subtitle flag
  default?: boolean; // Default track flag
}

interface SubtitleTrackManagerProps {
  sourceSubtitleTracks: SubtitleTrack[]; // Detected from source file
  outputTracks: OutputSubtitleTrack[];
  onChange: (tracks: OutputSubtitleTrack[]) => void;
}

export default function SubtitleTrackManager({
  sourceSubtitleTracks,
  outputTracks,
  onChange,
}: SubtitleTrackManagerProps): JSX.Element {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  const handleAddTrack = () => {
    const newTrack: OutputSubtitleTrack = {
      id: `subtitle_${Date.now()}_${Math.random()}`,
      sourceTrack: 0,
      mode: 'copy',
      language: undefined,
      name: undefined,
      forced: false,
      default: false,
    };
    onChange([...outputTracks, newTrack]);
  };

  const handleRemoveTrack = (index: number) => {
    const newTracks = outputTracks.filter((_, i) => i !== index);
    onChange(newTracks);
  };

  const handleUpdateTrack = (index: number, updates: Partial<OutputSubtitleTrack>) => {
    const newTracks = [...outputTracks];
    newTracks[index] = { ...newTracks[index], ...updates };
    onChange(newTracks);
  };

  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;

    const newTracks = [...outputTracks];
    const draggedTrack = newTracks[draggedIndex];
    newTracks.splice(draggedIndex, 1);
    newTracks.splice(index, 0, draggedTrack);

    setDraggedIndex(index);
    onChange(newTracks);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  return (
    <div className="subtitle-track-manager">
      <div className="subtitle-track-manager__header">
        <h3>Subtitle Tracks</h3>
        <button className="themed-btn" onClick={handleAddTrack} type="button">
          <span>+</span> Add Subtitle
        </button>
      </div>

      {outputTracks.length === 0 ? (
        <div className="subtitle-track-manager__empty">
          <p>No subtitle tracks configured. Click "Add Subtitle" to include subtitles in the output.</p>
        </div>
      ) : (
        <div className="subtitle-track-manager__list">
          {outputTracks.map((track, index) => (
            <SubtitleTrackCard
              key={track.id}
              track={track}
              index={index}
              sourceSubtitleTracks={sourceSubtitleTracks}
              onUpdate={updates => handleUpdateTrack(index, updates)}
              onRemove={() => handleRemoveTrack(index)}
              onDragStart={() => handleDragStart(index)}
              onDragOver={e => handleDragOver(e, index)}
              onDragEnd={handleDragEnd}
              isDragging={draggedIndex === index}
            />
          ))}
        </div>
      )}

      <div className="subtitle-track-manager__info">
        <p>
          💡 <strong>Copy:</strong> Embed subtitle in container (soft sub)
          {' | '}
          <strong>Extract:</strong> Save as external .srt file
          {' | '}
          <strong>Burn:</strong> Hardcode into video (not yet implemented)
        </p>
      </div>
    </div>
  );
}

interface SubtitleTrackCardProps {
  track: OutputSubtitleTrack;
  index: number;
  sourceSubtitleTracks: SubtitleTrack[];
  onUpdate: (updates: Partial<OutputSubtitleTrack>) => void;
  onRemove: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}

function SubtitleTrackCard({
  track,
  index,
  sourceSubtitleTracks,
  onUpdate,
  onRemove,
  onDragStart,
  onDragOver,
  onDragEnd,
  isDragging,
}: SubtitleTrackCardProps): JSX.Element {
  const sourceTrack = sourceSubtitleTracks[track.sourceTrack];

  return (
    <div
      className={`subtitle-track-card ${isDragging ? 'dragging' : ''}`}
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
    >
      <div className="subtitle-track-card__header">
        <div className="subtitle-track-card__drag-handle">
          <span>⋮⋮</span>
        </div>
        <div className="subtitle-track-card__title">
          <strong>Subtitle Track #{index + 1}</strong>
        </div>
        <button
          className="subtitle-track-card__remove"
          onClick={onRemove}
          type="button"
          title="Remove track"
        >
          ✕
        </button>
      </div>

      <div className="subtitle-track-card__body">
        {/* Source Track Selection */}
        <div className="form-group">
          <label>Source Track</label>
          <select
            value={track.sourceTrack}
            onChange={e => onUpdate({ sourceTrack: parseInt(e.target.value) })}
          >
            {sourceSubtitleTracks.length === 0 ? (
              <option value={0}>No subtitle tracks in source</option>
            ) : (
              sourceSubtitleTracks.map((srcTrack, idx) => (
                <option key={idx} value={idx}>
                  Track {idx + 1}: {srcTrack.format?.toUpperCase() || 'Unknown'}{' '}
                  {srcTrack.language ? `(${srcTrack.language})` : ''}
                  {srcTrack.title ? ` - ${srcTrack.title}` : ''}
                </option>
              ))
            )}
          </select>
          {sourceTrack && (
            <div className="form-hint">
              {sourceTrack.format} • {sourceTrack.language || 'No language tag'}
            </div>
          )}
        </div>

        {/* Mode Selection */}
        <div className="form-group">
          <label>Mode</label>
          <select value={track.mode} onChange={e => onUpdate({ mode: e.target.value as any })}>
            <option value="copy">Copy (Embed in container)</option>
            <option value="extract">Extract (External .srt file)</option>
            <option value="burn" disabled>
              Burn (Hardcode - Not Yet Implemented)
            </option>
          </select>
          <div className="form-hint">
            {track.mode === 'copy' && 'Subtitle embedded in output file (soft sub)'}
            {track.mode === 'extract' && 'Saves as external .srt file alongside video'}
            {track.mode === 'burn' && 'Permanently burns subtitle into video frames'}
          </div>
        </div>

        {/* Language Tag (optional) */}
        <div className="form-group">
          <label>Language (optional)</label>
          <input
            type="text"
            value={track.language || ''}
            onChange={e => onUpdate({ language: e.target.value || undefined })}
            placeholder="e.g., eng, jpn, spa"
            maxLength={3}
          />
          <div className="form-hint">3-letter ISO 639-2 code</div>
        </div>

        {/* Track Name (optional) */}
        <div className="form-group">
          <label>Track Name (optional)</label>
          <input
            type="text"
            value={track.name || ''}
            onChange={e => onUpdate({ name: e.target.value || undefined })}
            placeholder="e.g., English, Japanese, Signs/Songs"
          />
        </div>

        {/* Flags (only for copy mode) */}
        {track.mode === 'copy' && (
          <>
            <div className="form-group-checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={track.default || false}
                  onChange={e => onUpdate({ default: e.target.checked })}
                />
                <span>Default Track</span>
              </label>
              <div className="form-hint">Player will select this track by default</div>
            </div>

            <div className="form-group-checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={track.forced || false}
                  onChange={e => onUpdate({ forced: e.target.checked })}
                />
                <span>Forced Subtitle</span>
              </label>
              <div className="form-hint">For foreign language parts only</div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
