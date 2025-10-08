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
  file_name?: string;
  format?: string;
  file_size?: number;
  duration?: number;
  overall_bit_rate?: number;
  format_profile?: string;
  writing_application?: string;
}

export interface MediaInfoData {
  ok: boolean;
  path?: string;
  general?: GeneralInfo;
  video_tracks?: VideoTrack[];
  audio_tracks?: AudioTrack[];
  text_tracks?: SubtitleTrack[];
  mediainfo_data?: any; // raw mediainfo data
}
