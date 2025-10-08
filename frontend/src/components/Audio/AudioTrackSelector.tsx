/**
 * AudioTrackSelector - Dropdown showing available audio tracks from source
 *
 * Displays track metadata: language, codec, channels, sample rate, bitrate
 */

import { useMediaInfo } from '../../context/MediaInfoContext';
import type { AudioTrack } from '../../types/mediaInfoContext';

interface AudioTrackSelectorProps {
  selectedTrack: number;
  onChange: (trackIndex: number) => void;
}

export default function AudioTrackSelector({
  selectedTrack,
  onChange,
}: AudioTrackSelectorProps): JSX.Element {
  const { getAudioTracks } = useMediaInfo();
  const tracks = getAudioTracks();

  // Format channel count for display
  const formatChannels = (channels?: number, layout?: string): string => {
    if (layout) return layout;
    if (!channels) return 'Unknown';

    const channelMap: Record<number, string> = {
      1: 'Mono',
      2: 'Stereo',
      6: '5.1',
      8: '7.1',
    };

    return channelMap[channels] || `${channels}ch`;
  };

  // Format bitrate for display
  const formatBitrate = (bitrate?: number): string => {
    if (!bitrate) return '';
    return ` • ${Math.round(bitrate / 1000)} kbps`;
  };

  // Format sample rate for display
  const formatSampleRate = (rate?: number): string => {
    if (!rate) return '';
    return ` • ${(rate / 1000).toFixed(1)} kHz`;
  };

  // Get language code or default to 'und' (undefined)
  const getLanguage = (track: AudioTrack): string => {
    return track.language || 'und';
  };

  // Build display label for track
  const getTrackLabel = (track: AudioTrack, index: number): string => {
    const parts: string[] = [];

    // Track number
    parts.push(`Track ${index + 1}`);

    // Language (if not undefined/unknown)
    const lang = getLanguage(track);
    if (lang && lang !== 'und') {
      parts.push(lang.toUpperCase());
    }

    // Codec
    if (track.format) {
      parts.push(track.format);
    }

    // Channels
    const channels = formatChannels(track.channels, track.channel_layout);
    parts.push(channels);

    return parts.join(' • ');
  };

  // Build secondary info line (sample rate, bitrate)
  const getTrackSecondaryInfo = (track: AudioTrack): string => {
    const parts: string[] = [];

    if (track.sampling_rate) {
      parts.push(formatSampleRate(track.sampling_rate).trim());
    }

    if (track.bit_rate) {
      parts.push(formatBitrate(track.bit_rate).trim().replace('•', '').trim());
    }

    // Title if available
    if (track.title) {
      parts.push(`"${track.title}"`);
    }

    return parts.filter(p => p).join(' • ');
  };

  if (tracks.length === 0) {
    return (
      <div className="audio-track-selector">
        <label>
          Source Audio Track
          <div className="no-tracks-message">
            No audio tracks detected. Load a video file to see available tracks.
          </div>
        </label>
      </div>
    );
  }

  return (
    <div className="audio-track-selector">
      <label>
        Source Audio Track
        <select
          value={selectedTrack}
          onChange={e => onChange(parseInt(e.target.value, 10))}
          className="track-dropdown"
        >
          {tracks.map((track, index) => (
            <option key={index} value={index}>
              {getTrackLabel(track, index)}
            </option>
          ))}
        </select>
      </label>

      {/* Show detailed info for selected track */}
      {tracks[selectedTrack] && (
        <div className="track-details">
          <div className="track-info-line">{getTrackSecondaryInfo(tracks[selectedTrack])}</div>
        </div>
      )}
    </div>
  );
}
