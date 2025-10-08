import { createContext, useContext, useState, ReactNode } from 'react';
import type {
  VideoTrack,
  AudioTrack,
  SubtitleTrack,
  MediaInfoData,
} from '../types/mediaInfoContext';

interface MediaInfoContextValue {
  setMediaInfo: (info: MediaInfoData | null) => void;
  // Helper to get video tracks (from backend-parsed transport)
  getVideoTracks: () => VideoTrack[];
  // Helper to get audio tracks in a format ready for dropdowns
  getAudioTracks: () => AudioTrack[];
  // Helper to get a specific audio track by index
  getAudioTrack: (index: number) => AudioTrack | null;
  // Helper to get subtitle tracks
  getSubtitleTracks: () => SubtitleTrack[];
  // Helper to get a specific subtitle track by index
  getSubtitleTrack: (index: number) => SubtitleTrack | null;
  // Raw transport as returned by /api/mediainfo
  mediaInfo: MediaInfoData | null;
}

const MediaInfoContext = createContext<MediaInfoContextValue | undefined>(undefined);

export function MediaInfoProvider({ children }: { children: ReactNode }) {
  const [mediaInfo, setMediaInfo] = useState<MediaInfoData | null>(null);

  const getAudioTracks = (): AudioTrack[] => {
    return mediaInfo?.audio_tracks || [];
  };

  const getVideoTracks = (): VideoTrack[] => {
    return mediaInfo?.video_tracks || [];
  };

  const getAudioTrack = (index: number): AudioTrack | null => {
    const tracks = getAudioTracks();
    return tracks[index] || null;
  };

  const getSubtitleTracks = (): SubtitleTrack[] => {
    return mediaInfo?.text_tracks || [];
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
        getVideoTracks,
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
