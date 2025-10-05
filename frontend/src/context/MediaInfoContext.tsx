/**
 * MediaInfo Context - Global access to parsed media information
 *
 * Stores mediainfo data fetched on file selection so it can be
 * accessed by multiple components (Audio, Video, etc.) without
 * re-parsing or hitting the backend repeatedly.
 */

import React, { createContext, useContext, useState, ReactNode } from 'react';

// Match the structure from backend /api/mediainfo response
export interface VideoTrack {
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
  scan_type?: string;
  codec_id?: string;
}

export interface AudioTrack {
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
}

export interface SubtitleTrack {
  track_id?: number;
  format?: string;
  codec_id?: string;
  language?: string;
  title?: string;
  default?: string;
  forced?: string;
}

export interface GeneralInfo {
  filename?: string;
  format?: string;
  file_size?: number;
  duration?: number;
  overall_bitrate?: number;
  format_profile?: string;
  writing_application?: string;
}

export interface VapourSynthInfo {
  frames?: number;
  width?: number;
  height?: number;
  fps?: number;
  fps_num?: number;
  fps_den?: number;
  error?: string;
}

export interface MediaInfoData {
  ok: boolean;
  path?: string;
  general?: GeneralInfo;
  video_tracks?: VideoTrack[];
  audio_tracks?: AudioTrack[];
  subtitle_tracks?: SubtitleTrack[];
  vapoursynth?: VapourSynthInfo;
  mediainfo?: any; // Raw mediainfo data
}

interface MediaInfoContextValue {
  mediaInfo: MediaInfoData | null;
  setMediaInfo: (info: MediaInfoData | null) => void;
  // Helper to get audio tracks in a format ready for dropdowns
  getAudioTracks: () => AudioTrack[];
  // Helper to get a specific audio track by index
  getAudioTrack: (index: number) => AudioTrack | null;
  // Helper to get subtitle tracks
  getSubtitleTracks: () => SubtitleTrack[];
  // Helper to get a specific subtitle track by index
  getSubtitleTrack: (index: number) => SubtitleTrack | null;
}

const MediaInfoContext = createContext<MediaInfoContextValue | undefined>(undefined);

export function MediaInfoProvider({ children }: { children: ReactNode }) {
  const [mediaInfo, setMediaInfo] = useState<MediaInfoData | null>(null);

  const getAudioTracks = (): AudioTrack[] => {
    return mediaInfo?.audio_tracks || [];
  };

  const getAudioTrack = (index: number): AudioTrack | null => {
    const tracks = getAudioTracks();
    return tracks[index] || null;
  };

  const getSubtitleTracks = (): SubtitleTrack[] => {
    return mediaInfo?.subtitle_tracks || [];
  };

  const getSubtitleTrack = (index: number): SubtitleTrack | null => {
    const tracks = getSubtitleTracks();
    return tracks[index] || null;
  };

  return (
    <MediaInfoContext.Provider
      value={{
        mediaInfo,
        setMediaInfo,
        getAudioTracks,
        getAudioTrack,
        getSubtitleTracks,
        getSubtitleTrack,
      }}
    >
      {children}
    </MediaInfoContext.Provider>
  );
}

export function useMediaInfo() {
  const context = useContext(MediaInfoContext);
  if (context === undefined) {
    throw new Error('useMediaInfo must be used within a MediaInfoProvider');
  }
  return context;
}
