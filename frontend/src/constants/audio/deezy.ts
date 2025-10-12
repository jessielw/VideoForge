/**
 * DeeZy Audio Encoder Constants
 *
 * These constants mirror the backend enums in:
 * backend/app/enums/audio/deezy.py
 *
 * IMPORTANT: Keep in sync with backend when adding/changing encoder capabilities!
 */

// ============================================================================
// Dolby Digital (DD/AC-3) Constants
// ============================================================================

export const DEEZY_DD_CHANNELS = {
  AUTO: {
    value: 0,
    label: 'Auto (match source)',
    description: 'Automatically select channels based on source audio',
    defaultBitrate: null,
    validBitrates: [] as number[],
  },
  MONO: {
    value: 1,
    label: 'Mono (1.0)',
    description: 'Single channel audio (center channel only)',
    defaultBitrate: 192,
    validBitrates: [96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640],
  },
  STEREO: {
    value: 2,
    label: 'Stereo (2.0)',
    description: 'Standard stereo (left and right channels)',
    defaultBitrate: 224,
    validBitrates: [96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640],
  },
  SURROUND: {
    value: 6,
    label: '5.1 Surround',
    description: 'Full 5.1 surround sound (L/R/C/LFE/Ls/Rs)',
    defaultBitrate: 448,
    validBitrates: [224, 256, 320, 384, 448, 512, 576, 640],
  },
} as const;

// ============================================================================
// Dolby Digital Plus (DDP/E-AC-3) Constants
// ============================================================================

export const DEEZY_DDP_CHANNELS = {
  AUTO: {
    value: 0,
    label: 'Auto (match source)',
    description: 'Automatically select channels based on source audio',
    defaultBitrate: null,
    validBitrates: [] as number[],
  },
  MONO: {
    value: 1,
    label: 'Mono (1.0)',
    description: 'Single channel audio (center channel only)',
    defaultBitrate: 64,
    validBitrates: [
      32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 144, 160, 176, 192, 200, 208, 216,
      224, 232, 240, 248, 256, 272, 288, 304, 320, 336, 352, 368, 384, 400, 448, 512, 576, 640, 704,
      768, 832, 896, 960, 1008, 1024,
    ],
  },
  STEREO: {
    value: 2,
    label: 'Stereo (2.0)',
    description: 'Standard stereo (left and right channels)',
    defaultBitrate: 128,
    validBitrates: [
      96, 104, 112, 120, 128, 144, 160, 176, 192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288,
      304, 320, 336, 352, 368, 384, 400, 448, 512, 576, 640, 704, 768, 832, 896, 960, 1008, 1024,
    ],
  },
  SURROUND: {
    value: 6,
    label: '5.1 Surround',
    description: '5.1 surround sound (L/R/C/LFE/Ls/Rs)',
    defaultBitrate: 192,
    validBitrates: [
      192, 200, 208, 216, 224, 232, 240, 248, 256, 272, 288, 304, 320, 336, 352, 368, 384, 400, 448,
      512, 576, 640, 704, 768, 832, 896, 960, 1008, 1024,
    ],
  },
  SURROUNDEX: {
    value: 8,
    label: '7.1 Surround EX',
    description: '7.1 surround sound with side and rear surrounds',
    defaultBitrate: 384,
    validBitrates: [384, 448, 504, 576, 640, 704, 768, 832, 896, 960, 1008, 1024],
  },
} as const;

// ============================================================================
// Dolby Atmos Constants
// ============================================================================

export const DEEZY_ATMOS_MODES = {
  STREAMING: {
    value: 'streaming',
    label: 'Streaming (5.1 + Objects)',
    description: 'Optimized for streaming platforms with 5.1 bed and immersive objects',
    channels: 6,
    channelStr: '5.1',
    defaultBitrate: 448,
    validBitrates: [384, 448, 512, 576, 640, 768, 1024],
  },
  BLURAY: {
    value: 'bluray',
    label: 'Blu-ray (7.1 + Objects)',
    description: 'Blu-ray specification with 7.1 bed and higher bitrates for physical media',
    channels: 8,
    channelStr: '7.1',
    defaultBitrate: 1280,
    validBitrates: [1152, 1280, 1408, 1512, 1536, 1664],
  },
} as const;

// ============================================================================
// Dolby AC-4 Constants
// ============================================================================

export const DEEZY_AC4_CHANNELS = {
  IMMERSIVE_STEREO: {
    value: 'immersive_stereo',
    label: 'Immersive Stereo (2.0 + Objects)',
    description: 'Next-generation AC-4 codec with immersive audio objects in stereo layout',
    defaultBitrate: 256,
    validBitrates: [64, 72, 112, 144, 256, 320],
  },
} as const;

// ============================================================================
// Common DeeZy Options
// ============================================================================

export const DEEZY_STEREO_DOWNMIX = {
  LORO: {
    value: 'loro',
    label: 'Lo/Ro (Stereo)',
    description: 'Left Only / Right Only - Simple stereo downmix',
  },
  LTRT: {
    value: 'ltrt',
    label: 'Lt/Rt (Matrix Encoded)',
    description: 'Left Total / Right Total - Matrix-encoded for Dolby Surround compatible playback',
  },
} as const;

export const DEEZY_DRC_PROFILES = {
  FILM_STANDARD: {
    value: 'film_standard',
    label: 'Film Standard',
    description: 'Standard compression for film content (recommended for most users)',
  },
  FILM_LIGHT: {
    value: 'film_light',
    label: 'Film Light',
    description: 'Light compression for film content (preserves more dynamics)',
  },
  MUSIC_STANDARD: {
    value: 'music_standard',
    label: 'Music Standard',
    description: 'Standard compression for music content',
  },
  MUSIC_LIGHT: {
    value: 'music_light',
    label: 'Music Light',
    description: 'Light compression for music content',
  },
  SPEECH: {
    value: 'speech',
    label: 'Speech',
    description: 'Optimized for speech/dialogue (maximum intelligibility)',
  },
} as const;

// ============================================================================
// Codec Format Display Names
// ============================================================================

export const DEEZY_CODEC_FORMATS = {
  dd: {
    value: 'dd',
    displayName: 'Dolby Digital (AC-3)',
    fileExtension: 'ac3',
  },
  ddp: {
    value: 'ddp',
    displayName: 'Dolby Digital Plus (E-AC-3)',
    fileExtension: 'ec3',
  },
  atmos: {
    value: 'atmos',
    displayName: 'Dolby Atmos',
    fileExtension: 'ec3',
  },
  ac4: {
    value: 'ac4',
    displayName: 'Dolby AC-4',
    fileExtension: 'ac4',
  },
} as const;

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get channel configuration by value
 */
export function getDDChannelByValue(value: number) {
  return Object.values(DEEZY_DD_CHANNELS).find(ch => ch.value === value);
}

export function getDDPChannelByValue(value: number) {
  return Object.values(DEEZY_DDP_CHANNELS).find(ch => ch.value === value);
}

export function getAtmosModeByValue(value: string) {
  return Object.values(DEEZY_ATMOS_MODES).find(mode => mode.value === value);
}

/**
 * Get valid bitrates for a specific configuration
 */
export function getValidBitratesForDD(channelValue: number): readonly number[] {
  const channel = getDDChannelByValue(channelValue);
  return channel?.validBitrates ?? [];
}

export function getValidBitratesForDDP(channelValue: number): readonly number[] {
  const channel = getDDPChannelByValue(channelValue);
  return channel?.validBitrates ?? [];
}

export function getValidBitratesForAtmos(modeValue: string): readonly number[] {
  const mode = getAtmosModeByValue(modeValue);
  return mode?.validBitrates ?? [];
}

export function getValidBitratesForAC4(): readonly number[] {
  return DEEZY_AC4_CHANNELS.IMMERSIVE_STEREO.validBitrates;
}
