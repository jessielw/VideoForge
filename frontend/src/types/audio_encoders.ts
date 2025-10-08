// must match backend backend/enums/audio.py
export const AUDIO_ENCODER_VALUES = ['copy', 'ffmpeg aac', 'ffmpeg opus'] as const;

export type AudioEncoder = (typeof AUDIO_ENCODER_VALUES)[number];

export const AUDIO_ENCODER_OPTIONS: { value: AudioEncoder; label: string }[] =
  AUDIO_ENCODER_VALUES.map(v => {
    let label: string = v;
    if (v === 'copy') label = 'Copy';
    if (v === 'ffmpeg aac') label = 'AAC (ffmpeg)';
    if (v === 'ffmpeg opus') label = 'Opus (ffmpeg)';
    return { value: v as AudioEncoder, label };
  });
