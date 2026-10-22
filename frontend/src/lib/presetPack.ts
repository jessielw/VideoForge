import type { ConfigurationBundle, PresetPack } from './types.ts'

// Explicit allowlists: settings, defaults, machine paths, and local storage identities never enter a pack.
export function presetPack(libraries: ConfigurationBundle['presets']): PresetPack {
  return { format: 'videoforge.presets', version: 1, presets: {
    template: libraries.template.map(({ name, data }) => ({ name, data: structuredClone(data) })),
    video: libraries.video.map(({ name, data }) => ({ name, data: structuredClone(data) })),
    encoder: libraries.encoder.map(({ name, label, group, data }) => ({ label: label ?? name, group: [...(group ?? [])], data: structuredClone(data) })),
    audio: libraries.audio.map(({ name, label, group, data }) => ({ label: label ?? name, group: [...(group ?? [])], data: structuredClone(data) })),
  } }
}
