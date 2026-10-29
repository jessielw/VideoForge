import type { EncoderBundle, EncoderSettings, Preset } from './types'

export const MAX_ENCODER_BYTES = 5 * 1024 * 1024

export function encoderBundle(entries: Preset<EncoderSettings>[]): EncoderBundle {
  return {
    format: 'videoforge.encoders',
    version: 1,
    encoders: entries.map((entry) => ({
      label: entry.label ?? entry.name,
      group: [...(entry.group ?? [])],
      data: structuredClone(entry.data),
    })),
  }
}

export function downloadEncoders(bundle: EncoderBundle, filename: string) {
  const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' })
  if (blob.size > MAX_ENCODER_BYTES) throw new Error('The exported file exceeds 5 MiB. Select fewer presets.')
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
