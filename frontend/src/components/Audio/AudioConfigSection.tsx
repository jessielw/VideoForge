/**
 * AudioConfigSection - Multi-track audio configuration UI
 * Replaces the old single-track AudioSettings
 */

import React from 'react';
import AudioTrackManager, { OutputAudioTrack } from './AudioTrackManager';
import { AudioTrack } from '../../context/MediaInfoContext';
import './AudioTrackManager.css';
import './AudioConfigSection.css';

export interface MultiTrackAudioConfig {
  tracks: OutputAudioTrack[];
}

interface AudioConfigSectionProps {
  sourceAudioTracks: AudioTrack[]; // Detected audio tracks from source file
  config: MultiTrackAudioConfig;
  onChange: (config: MultiTrackAudioConfig) => void;
}

export default function AudioConfigSection({
  sourceAudioTracks,
  config,
  onChange,
}: AudioConfigSectionProps): JSX.Element {
  const handleTracksChange = (tracks: OutputAudioTrack[]) => {
    onChange({ tracks });
  };

  return (
    <div className="audio-config-section">
      <AudioTrackManager
        sourceAudioTracks={sourceAudioTracks}
        outputTracks={config.tracks}
        onChange={handleTracksChange}
      />

      {/* Summary */}
      {config.tracks.length > 0 && (
        <div className="audio-config-summary">
          <h4>Configuration Summary</h4>
          <ul>
            {config.tracks.map((track, idx) => {
              const sourceTrack = sourceAudioTracks[track.sourceTrack];
              const encoderLabel =
                track.encoder === 'copy'
                  ? 'Copy (no re-encode)'
                  : `${track.encoder.toUpperCase()} @ ${track.bitrate}kbps`;
              const sourceLabel = sourceTrack
                ? `Track ${track.sourceTrack + 1} (${sourceTrack.format})`
                : `Track ${track.sourceTrack + 1}`;

              return (
                <li key={track.id}>
                  <strong>Output #{idx + 1}:</strong> {sourceLabel} → {encoderLabel}
                  {track.name && ` - "${track.name}"`}
                  {track.language && ` [${track.language}]`}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
