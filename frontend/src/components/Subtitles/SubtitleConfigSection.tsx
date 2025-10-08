/**
 * SubtitleConfigSection - Multi-track subtitle configuration UI wrapper
 */

import React from 'react';
import SubtitleTrackManager, { OutputSubtitleTrack } from './SubtitleTrackManager';
import type { SubtitleTrack } from '../../types/mediaInfoContext';
import './SubtitleTrackManager.css';
import './SubtitleConfigSection.css';

export interface MultiTrackSubtitleConfig {
  tracks: OutputSubtitleTrack[];
}

interface SubtitleConfigSectionProps {
  sourceSubtitleTracks: SubtitleTrack[]; // Detected subtitle tracks from source file
  config: MultiTrackSubtitleConfig;
  onChange: (config: MultiTrackSubtitleConfig) => void;
}

export default function SubtitleConfigSection({
  sourceSubtitleTracks,
  config,
  onChange,
}: SubtitleConfigSectionProps): JSX.Element {
  const handleTracksChange = (tracks: OutputSubtitleTrack[]) => {
    onChange({ tracks });
  };

  return (
    <div className="subtitle-config-section">
      <SubtitleTrackManager
        sourceSubtitleTracks={sourceSubtitleTracks}
        outputTracks={config.tracks}
        onChange={handleTracksChange}
      />

      {/* Summary */}
      {config.tracks.length > 0 && (
        <div className="subtitle-config-summary">
          <h4>Configuration Summary</h4>
          <ul>
            {config.tracks.map((track, idx) => {
              const sourceTrack = sourceSubtitleTracks[track.sourceTrack];
              const modeLabel =
                track.mode === 'copy'
                  ? 'Embedded (soft sub)'
                  : track.mode === 'extract'
                    ? 'External .srt file'
                    : 'Burned (hardcoded)';
              const sourceLabel = sourceTrack
                ? `Track ${track.sourceTrack + 1} (${sourceTrack.format})`
                : `Track ${track.sourceTrack + 1}`;

              const flags = [];
              if (track.default) flags.push('Default');
              if (track.forced) flags.push('Forced');
              const flagsStr = flags.length > 0 ? ` [${flags.join(', ')}]` : '';

              return (
                <li key={track.id}>
                  <strong>Subtitle #{idx + 1}:</strong> {sourceLabel} → {modeLabel}
                  {track.name && ` - "${track.name}"`}
                  {track.language && ` [${track.language}]`}
                  {flagsStr}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
