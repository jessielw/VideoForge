import AudioTrackManager from './AudioTrackManager';
import { OutputAudioTrack } from '../../types/audio';
import { AudioTrack } from '../../types/mediaInfoContext';

import '../../styles/components/AudioTrackManager.css';
import '../../styles/components/AudioConfigSection.css';

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
              const sourceTrack = sourceAudioTracks[track.config.source_track];
              const sourceLabel = sourceTrack
                ? `Track ${track.config.source_track + 1} (${sourceTrack.format})`
                : `Track ${track.config.source_track + 1}`;

              let encoderLabel = 'Unknown';
              if (track.config.encoder_type === 'copy') {
                encoderLabel = 'Copy (no re-encode)';
              } else if (track.config.encoder_type === 'deezy') {
                const deezyConfig = track.config as any;
                const format = deezyConfig.codec_format.toUpperCase();
                if (deezyConfig.codec_format === 'dd' || deezyConfig.codec_format === 'ddp') {
                  const bitrate =
                    deezyConfig.bitrate !== null ? `${deezyConfig.bitrate}kbps` : 'Auto';
                  encoderLabel = `${format} @ ${bitrate}`;
                } else if (deezyConfig.codec_format === 'atmos') {
                  encoderLabel = `Atmos @ ${deezyConfig.bitrate}kbps`;
                } else if (deezyConfig.codec_format === 'ac4') {
                  encoderLabel = `AC-4 @ ${deezyConfig.bitrate}kbps`;
                }
              }

              return (
                <li key={track.id}>
                  <strong>Output #{idx + 1}:</strong> {sourceLabel} → {encoderLabel}
                  {track.title && ` - "${track.title}"`}
                  {track.config.language && ` [${track.config.language}]`}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
