/**
 * AudioTrackManager - StaxRip-style multi-track audio management
 * 
 * Features:
 * - Add multiple output tracks from same/different source tracks
 * - Configure each output track independently (encoder, bitrate, language, name)
 * - Reorder output tracks via drag & drop
 * - Remove tracks
 * - Visual source → output mapping
 */

import React, { useState } from 'react';
import { AudioTrack } from '../../context/MediaInfoContext';

// Output track configuration (what goes in final file)
export interface OutputAudioTrack {
  id: string; // Unique ID for React keys
  sourceTrack: number; // Which source track to use
  encoder: 'aac' | 'opus' | 'copy';
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

  const handleAddTrack = () => {
    const newTrack: OutputAudioTrack = {
      id: `track_${Date.now()}_${Math.random()}`,
      sourceTrack: 0,
      encoder: 'aac',
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
    <div className="audio-track-manager">
      <div className="audio-track-manager__header">
        <h3>Audio Tracks</h3>
        <button className="btn-add-track" onClick={handleAddTrack} type="button">
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
            <AudioTrackCard
              key={track.id}
              track={track}
              index={index}
              sourceAudioTracks={sourceAudioTracks}
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

      <div className="audio-track-manager__info">
        <p>💡 Tip: You can select the same source track multiple times with different encoders/bitrates</p>
      </div>
    </div>
  );
}

interface AudioTrackCardProps {
  track: OutputAudioTrack;
  index: number;
  sourceAudioTracks: AudioTrack[];
  onUpdate: (updates: Partial<OutputAudioTrack>) => void;
  onRemove: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}

function AudioTrackCard({
  track,
  index,
  sourceAudioTracks,
  onUpdate,
  onRemove,
  onDragStart,
  onDragOver,
  onDragEnd,
  isDragging,
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
        <button
          className="audio-track-card__remove"
          onClick={onRemove}
          type="button"
          title="Remove track"
        >
          ✕
        </button>
      </div>

      <div className="audio-track-card__body">
        {/* Source Track Selection */}
        <div className="form-group">
          <label>Source Track</label>
          <select
            value={track.sourceTrack}
            onChange={e => onUpdate({ sourceTrack: parseInt(e.target.value) })}
          >
            {sourceAudioTracks.length === 0 ? (
              <option value={0}>No audio tracks in source</option>
            ) : (
              sourceAudioTracks.map((srcTrack, idx) => (
                <option key={idx} value={idx}>
                  Track {idx + 1}: {srcTrack.format?.toUpperCase() || 'Unknown'}{' '}
                  {srcTrack.channels ? `${srcTrack.channels}ch` : ''}{' '}
                  {srcTrack.language ? `(${srcTrack.language})` : ''}
                </option>
              ))
            )}
          </select>
          {sourceTrack && (
            <div className="form-hint">
              {sourceTrack.format} • {sourceTrack.channels}ch •{' '}
              {sourceTrack.sampling_rate ? `${sourceTrack.sampling_rate}Hz` : 'Unknown rate'}
            </div>
          )}
        </div>

        {/* Encoder Selection */}
        <div className="form-group">
          <label>Encoder</label>
          <select value={track.encoder} onChange={e => onUpdate({ encoder: e.target.value as any })}>
            <option value="aac">AAC (Universal compatibility)</option>
            <option value="opus">Opus (Best quality/size - MKV only)</option>
            <option value="copy">Copy (No re-encoding)</option>
          </select>
        </div>

        {/* Bitrate (only for encoders, not copy) */}
        {track.encoder !== 'copy' && (
          <div className="form-group">
            <label>Bitrate</label>
            <div className="input-with-unit">
              <input
                type="number"
                value={track.bitrate}
                onChange={e => onUpdate({ bitrate: parseInt(e.target.value) || 192 })}
                min={64}
                max={512}
                step={32}
              />
              <span className="unit">kbps</span>
            </div>
            <div className="form-hint">
              Recommended: 128 (stereo good), 192 (stereo great), 256-384 (5.1/7.1)
            </div>
          </div>
        )}

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
            placeholder="e.g., English Stereo, Japanese 5.1, Commentary"
          />
        </div>
      </div>
    </div>
  );
}
