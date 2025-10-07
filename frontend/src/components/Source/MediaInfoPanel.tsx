import React, { useState } from 'react';
import { useMediaInfo } from '../../context/MediaInfoContext';

interface VideoTrack {
  track_id?: number;
  format?: string;
  format_profile?: string;
  format_level?: string;
  width?: number;
  height?: number;
  display_aspect_ratio?: string;
  pixel_aspect_ratio?: string;
  frame_rate?: number;
  frame_count?: number;
  bit_rate?: number;
  bit_depth?: number;
  chroma_subsampling?: string;
  color_space?: string;
  color_range?: string;
  color_primaries?: string;
  transfer_characteristics?: string;
  matrix_coefficients?: string;
  scan_type?: string;
  codec_id?: string;
  encoded_library_name?: string;
  encoded_library_version?: string;
}

interface AudioTrack {
  track_id?: number;
  format?: string;
  format_profile?: string;
  codec_id?: string;
  channels?: number;
  channel_layout?: string;
  sampling_rate?: number;
  bit_rate?: number;
  bit_depth?: number;
  language?: string;
  title?: string;
  default?: string;
  forced?: string;
  compression_mode?: string;
  encoded_library_name?: string;
}

interface SubtitleTrack {
  track_id?: number;
  format?: string;
  codec_id?: string;
  language?: string;
  title?: string;
  default?: string;
  forced?: string;
}

interface GeneralInfo {
  filename?: string;
  format?: string;
  file_size?: number;
  duration?: number;
  overall_bitrate?: number;
  format_profile?: string;
  encoded_date?: string;
  writing_application?: string;
  writing_library?: string;
}

interface MediaInfo {
  ok: boolean;
  general?: GeneralInfo;
  video_tracks?: VideoTrack[];
  audio_tracks?: AudioTrack[];
  subtitle_tracks?: SubtitleTrack[];
  vapoursynth?: {
    frames?: number;
    width?: number;
    height?: number;
    fps?: number;
    error?: string;
  };
}

interface MediaInfoPanelProps {
  filePath: string | null;
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return 'Unknown';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

function formatDuration(ms?: number): string {
  if (!ms) return 'Unknown';
  const seconds = Math.floor(ms / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  } else {
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }
}

function formatBitrate(bps?: number): string {
  if (!bps) return 'Unknown';
  if (bps >= 1000000) {
    return `${(bps / 1000000).toFixed(1)} Mbps`;
  } else if (bps >= 1000) {
    return `${(bps / 1000).toFixed(0)} kbps`;
  } else {
    return `${bps} bps`;
  }
}

export default function MediaInfoPanel({ filePath }: MediaInfoPanelProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<'general' | 'video' | 'audio' | 'subtitles'>(
    'general'
  );

  // MediaInfoPanel only displays the mediainfo fetched on selection. Probe/index
  // (vapoursynth) data is handled separately by the indexing/probe flows and
  // should not overwrite or mask mediainfo. Read mediaInfo from context only.
  const { mediaInfo } = useMediaInfo();
  const effectiveInfo: MediaInfo | null = (mediaInfo as any) || null;
  const vapoursynthFromMediaInfo = (mediaInfo as any)?.vapoursynth || null;

  if (!filePath || !effectiveInfo) {
    return (
      <div className="media-info-panel">
        <h3>Media Information</h3>
        <p className="no-file">No file selected</p>
      </div>
    );
  }

  if (!effectiveInfo.ok) {
    return (
      <div className="media-info-panel">
        <h3>Media Information</h3>
        <p className="error-message">Failed to analyze media file</p>
      </div>
    );
  }

  // mediainfo from backend
  const mi = (effectiveInfo as any).mediainfo || effectiveInfo;

  // Helper to safely parse numeric-like fields that sometimes come back as strings
  const parseNum = (v: any): number | undefined => {
    if (v === undefined || v === null) return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  };

  // Extract tracks from MediaInfo structure
  const tracks: any[] = Array.isArray(mi?.tracks) ? mi.tracks : [];
  const generalTrack = tracks.find(t => t.track_type === 'General') || {};
  const videoTracks = tracks.filter(t => t.track_type === 'Video');
  const audioTracks = tracks.filter(t => t.track_type === 'Audio');
  const subtitleTracks = tracks.filter(t => t.track_type === 'Text' || t.track_type === 'Subtitle');

  const renderGeneralInfo = () => (
    <div className="info-section">
      <div className="info-grid">
        <div className="info-item">
          <label>Filename:</label>
          <span>{generalTrack.file_name || 'Unknown'}</span>
        </div>
        <div className="info-item">
          <label>Format:</label>
          <span>{generalTrack.format || 'Unknown'}</span>
        </div>
        <div className="info-item">
          <label>File Size:</label>
          <span>{formatFileSize(parseNum(generalTrack.file_size))}</span>
        </div>
        <div className="info-item">
          <label>Duration:</label>
          <span>{formatDuration(parseNum(generalTrack.duration))}</span>
        </div>
        <div className="info-item">
          <label>Overall Bitrate:</label>
          <span>{formatBitrate(parseNum(generalTrack.overall_bit_rate))}</span>
        </div>
      </div>

      {/* Additional details section */}
      {(generalTrack.format_profile ||
        generalTrack.writing_application ||
        generalTrack.writing_library) && (
        <div className="additional-info">
          <h4>Additional Details</h4>
          <div className="info-grid">
            {generalTrack.format_profile && (
              <div className="info-item">
                <label>Profile:</label>
                <span>{generalTrack.format_profile}</span>
              </div>
            )}
            {generalTrack.writing_application && (
              <div className="info-item">
                <label>Encoded By:</label>
                <span>{generalTrack.writing_application}</span>
              </div>
            )}
            {generalTrack.writing_library && (
              <div className="info-item">
                <label>Library:</label>
                <span>{generalTrack.writing_library}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  const renderVideoInfo = () => (
    <div className="info-section">
      {videoTracks && videoTracks.length > 0 ? (
        videoTracks.map((track, index) => (
          <div key={index} className="track-info">
            <h4>Video Track {track.track_id || index + 1}</h4>

            {/* Basic Properties */}
            <div className="info-grid">
              <div className="info-item">
                <label>Codec:</label>
                <span>{track.format || 'Unknown'}</span>
              </div>
              <div className="info-item">
                <label>Resolution:</label>
                <span>
                  {track.width && track.height
                    ? `${track.width} × ${track.height}`
                    : (vapoursynthFromMediaInfo?.width || effectiveInfo?.vapoursynth?.width) &&
                      (vapoursynthFromMediaInfo?.height || effectiveInfo?.vapoursynth?.height)
                    ? `${vapoursynthFromMediaInfo?.width || effectiveInfo?.vapoursynth?.width} × ${
                        vapoursynthFromMediaInfo?.height || effectiveInfo?.vapoursynth?.height
                      }`
                    : 'Unknown'}
                </span>
              </div>
              <div className="info-item">
                <label>Frame Rate:</label>
                <span>
                  {track.frame_rate
                    ? `${track.frame_rate} fps`
                    : vapoursynthFromMediaInfo?.fps || effectiveInfo?.vapoursynth?.fps
                    ? `${(
                        (vapoursynthFromMediaInfo?.fps || effectiveInfo?.vapoursynth?.fps) as number
                      ).toFixed(3)} fps`
                    : 'Unknown'}
                </span>
              </div>
              <div className="info-item">
                <label>Total Frames:</label>
                <span>
                  {track.frame_count ||
                    vapoursynthFromMediaInfo?.frames ||
                    effectiveInfo?.vapoursynth?.frames ||
                    'Unknown'}
                </span>
              </div>
              <div className="info-item">
                <label>Bitrate:</label>
                <span>{formatBitrate(parseNum(track.bit_rate))}</span>
              </div>
              <div className="info-item">
                <label>Bit Depth:</label>
                <span>{track.bit_depth ? `${track.bit_depth} bit` : 'Unknown'}</span>
              </div>
              {track.display_aspect_ratio && (
                <div className="info-item">
                  <label>Aspect Ratio:</label>
                  <span>{track.display_aspect_ratio}</span>
                </div>
              )}
            </div>

            {/* Color Information */}
            {(track.color_space ||
              track.chroma_subsampling ||
              track.color_primaries ||
              track.transfer_characteristics ||
              track.matrix_coefficients) && (
              <div className="color-info">
                <h5>Color Information</h5>
                <div className="info-grid">
                  {track.color_space && (
                    <div className="info-item">
                      <label>Color Space:</label>
                      <span>{track.color_space}</span>
                    </div>
                  )}
                  {track.chroma_subsampling && (
                    <div className="info-item">
                      <label>Chroma:</label>
                      <span>{track.chroma_subsampling}</span>
                    </div>
                  )}
                  {track.color_primaries && (
                    <div className="info-item">
                      <label>Color Primaries:</label>
                      <span>{track.color_primaries}</span>
                    </div>
                  )}
                  {track.transfer_characteristics && (
                    <div className="info-item">
                      <label>Transfer:</label>
                      <span>{track.transfer_characteristics}</span>
                    </div>
                  )}
                  {track.matrix_coefficients && (
                    <div className="info-item">
                      <label>Matrix:</label>
                      <span>{track.matrix_coefficients}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Technical Details */}
            {(track.scan_type || track.format_profile || track.encoded_library_name) && (
              <div className="technical-info">
                <h5>Technical Details</h5>
                <div className="info-grid">
                  {track.scan_type && (
                    <div className="info-item">
                      <label>Scan Type:</label>
                      <span>{track.scan_type}</span>
                    </div>
                  )}
                  {track.format_profile && (
                    <div className="info-item">
                      <label>Profile:</label>
                      <span>{track.format_profile}</span>
                    </div>
                  )}
                  {track.encoded_library_name && (
                    <div className="info-item">
                      <label>Encoder:</label>
                      <span>{track.encoded_library_name}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))
      ) : (
        <p className="no-tracks">No video tracks found</p>
      )}
    </div>
  );

  const renderAudioInfo = () => (
    <div className="info-section">
      {audioTracks && audioTracks.length > 0 ? (
        audioTracks.map((track, index) => (
          <div key={index} className="track-info">
            <h4>
              Audio Track {track.track_id || index + 1}
              {track.language && ` (${track.language})`}
              {track.title && ` - ${track.title}`}
            </h4>

            {/* Basic Properties */}
            <div className="info-grid">
              <div className="info-item">
                <label>Codec:</label>
                <span>{track.format || 'Unknown'}</span>
              </div>
              <div className="info-item">
                <label>Channels:</label>
                <span>
                  {track.channels ? `${track.channels} channels` : 'Unknown'}
                  {track.channel_layout && ` (${track.channel_layout})`}
                </span>
              </div>
              <div className="info-item">
                <label>Sample Rate:</label>
                <span>{track.sampling_rate ? `${track.sampling_rate} Hz` : 'Unknown'}</span>
              </div>
              <div className="info-item">
                <label>Bitrate:</label>
                <span>{formatBitrate(track.bit_rate)}</span>
              </div>
              {track.bit_depth && (
                <div className="info-item">
                  <label>Bit Depth:</label>
                  <span>{track.bit_depth} bit</span>
                </div>
              )}
            </div>

            {/* Track Properties */}
            <div className="technical-info">
              <h5>Track Properties</h5>
              <div className="info-grid">
                <div className="info-item">
                  <label>Default:</label>
                  <span>{track.default === 'Yes' ? '✓ Yes' : '✗ No'}</span>
                </div>
                <div className="info-item">
                  <label>Forced:</label>
                  <span>{track.forced === 'Yes' ? '✓ Yes' : '✗ No'}</span>
                </div>
                {track.compression_mode && (
                  <div className="info-item">
                    <label>Compression:</label>
                    <span>{track.compression_mode}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))
      ) : (
        <p className="no-tracks">No audio tracks found</p>
      )}
    </div>
  );

  const renderSubtitleInfo = () => (
    <div className="info-section">
      {subtitleTracks && subtitleTracks.length > 0 ? (
        subtitleTracks.map((track, index) => (
          <div key={index} className="track-info">
            <h4>
              Subtitle Track {track.track_id || index + 1}
              {track.language && ` (${track.language})`}
              {track.title && ` - ${track.title}`}
            </h4>
            <div className="info-grid">
              <div className="info-item">
                <label>Format:</label>
                <span>{track.format || 'Unknown'}</span>
              </div>
              <div className="info-item">
                <label>Default:</label>
                <span>{track.default === 'Yes' ? '✓' : '✗'}</span>
              </div>
              <div className="info-item">
                <label>Forced:</label>
                <span>{track.forced === 'Yes' ? '✓' : '✗'}</span>
              </div>
            </div>
          </div>
        ))
      ) : (
        <p className="no-tracks">No subtitle tracks found</p>
      )}
    </div>
  );

  return (
    <div className="media-info-panel">
      <h3>Media Information</h3>

      {vapoursynthFromMediaInfo?.error && (
        <div className="vs-warning">
          <span>⚠️ VapourSynth probe reported in mediainfo: {vapoursynthFromMediaInfo.error}</span>
        </div>
      )}

      <div className="info-tabs">
        <button
          className={`info-tab ${activeTab === 'general' ? 'active' : ''}`}
          onClick={() => setActiveTab('general')}
        >
          General
        </button>
        <button
          className={`info-tab ${activeTab === 'video' ? 'active' : ''}`}
          onClick={() => setActiveTab('video')}
        >
          Video ({videoTracks.length || 0})
        </button>
        <button
          className={`info-tab ${activeTab === 'audio' ? 'active' : ''}`}
          onClick={() => setActiveTab('audio')}
        >
          Audio ({audioTracks.length || 0})
        </button>
        <button
          className={`info-tab ${activeTab === 'subtitles' ? 'active' : ''}`}
          onClick={() => setActiveTab('subtitles')}
        >
          Subtitles ({subtitleTracks.length || 0})
        </button>
      </div>

      <div className="info-content">
        {activeTab === 'general' && renderGeneralInfo()}
        {activeTab === 'video' && renderVideoInfo()}
        {activeTab === 'audio' && renderAudioInfo()}
        {activeTab === 'subtitles' && renderSubtitleInfo()}
      </div>
    </div>
  );
}
