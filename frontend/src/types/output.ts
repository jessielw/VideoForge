/**
 * Output configuration types
 */

// Supported container formats
export type ContainerFormat = 'mkv' | 'mp4';

// Muxer tools
export type MuxerTool = 'mkvmerge' | 'mp4box' | 'ffmpeg';

// Output configuration
export interface OutputConfig {
  outputPath: string;
  container: ContainerFormat;
  muxer?: MuxerTool; // Auto-selected based on container if not specified

  // Optional settings
  fastStart?: boolean; // MP4 only: move moov atom to beginning for web streaming
  overwrite?: boolean; // Overwrite existing file without prompting
}

// Container-specific capabilities
export interface ContainerInfo {
  format: ContainerFormat;
  displayName: string;
  extension: string;
  muxer: MuxerTool;
  description: string;
  icon: string;
  supportsChapters: boolean;
  supportsMultipleAudioTracks: boolean;
  supportsMultipleSubtitleTracks: boolean;
  supportsAttachments: boolean;
}

// Container registry
export const CONTAINER_INFO: Record<ContainerFormat, ContainerInfo> = {
  mkv: {
    format: 'mkv',
    displayName: 'Matroska (MKV)',
    extension: '.mkv',
    muxer: 'mkvmerge',
    description: 'Universal container with excellent codec support, chapters, and attachments',
    icon: '📦',
    supportsChapters: true,
    supportsMultipleAudioTracks: true,
    supportsMultipleSubtitleTracks: true,
    supportsAttachments: true,
  },
  mp4: {
    format: 'mp4',
    displayName: 'MPEG-4 (MP4)',
    extension: '.mp4',
    muxer: 'mp4box',
    description: 'Widely compatible container, best for web streaming and mobile devices',
    icon: '🎬',
    supportsChapters: true,
    supportsMultipleAudioTracks: true,
    supportsMultipleSubtitleTracks: false, // MP4 subtitle support is limited
    supportsAttachments: false,
  },
};
