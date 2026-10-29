import type { AudioBundle, AudioPresetSettings, Preset } from './types'

export const MAX_AUDIO_BYTES = 5 * 1024 * 1024

export function audioBundle(entries: Preset<AudioPresetSettings>[]): AudioBundle {
  return {
    format: 'videoforge.audio',
    version: 1,
    audio: entries.map((entry) => ({
      label: entry.label ?? entry.name,
      group: [...(entry.group ?? [])],
      data: structuredClone(entry.data),
    })),
  }
}

export function downloadAudio(bundle: AudioBundle, filename: string) {
  const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' })
  if (blob.size > MAX_AUDIO_BYTES) throw new Error('The exported file exceeds 5 MiB. Select fewer presets.')
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
