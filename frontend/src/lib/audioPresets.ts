import type { AudioEncodeInfo, AudioPresetSettings, AudioTrack, Preset, TrackOverride } from './types'

export const channels = (layout: string) => layout.split('.').reduce((sum, part) => sum + Number(part), 0)
const copySettings = (): AudioPresetSettings => ({ action: 'copy', layout: null, bitrate_kbps: null, options: {} })

export function audioPresetSettings(value?: Partial<TrackOverride>): AudioPresetSettings {
  if (!value?.action || value.action === 'copy') return copySettings()
  return { action: value.action, layout: value.layout ?? null, bitrate_kbps: value.bitrate_kbps ?? null, options: { ...value.options } }
}

export function applyAudioPreset(value: TrackOverride, preset: AudioPresetSettings): TrackOverride {
  const settings = preset.action === 'copy' ? copySettings() : preset
  return { ...value, action: settings.action,
    layout: settings.layout, bitrate_kbps: settings.bitrate_kbps, options: { ...settings.options } }
}

function defaultLayout(enc: AudioEncodeInfo, source: string): string {
  if (enc.id === 'ddp' && source === '5.0') return '5.1'
  const cap = enc.default_max ? Math.min(channels(source), channels(enc.default_max)) : channels(source)
  const fits = enc.layouts.filter(layout => channels(layout) <= cap)
  if (fits.includes(source)) return source
  return fits.sort((a, b) => channels(b) - channels(a) || Number(b.split('.')[1]) - Number(a.split('.')[1]))[0] ?? enc.layouts[0]
}

export function audioPresetProblem(settings: AudioPresetSettings, encodes: AudioEncodeInfo[], source?: AudioTrack): string {
  if (settings.action === 'copy') return ''
  const enc = encodes.find(e => e.id === settings.action)
  if (!enc) return 'Encoder information is unavailable'
  if (settings.layout && !enc.layouts.includes(settings.layout)) return `${enc.label} does not support ${settings.layout}`
  if (source && settings.action === 'atmos' && !(source.codec === 'truehd' && source.atmos)) return 'Requires a TrueHD Atmos source'
  const layout = settings.layout ?? (source ? defaultLayout(enc, source.layout) : null)
  if (source && layout && channels(layout) > channels(source.layout)
    && !(enc.id === 'ddp' && source.layout === '5.0' && layout === '5.1')) return `${layout} requires more channels than this ${source.layout} source`
  const bitrate = settings.bitrate_kbps
  if (bitrate !== null) {
    if (!Number.isInteger(bitrate) || bitrate <= 0) return 'Bitrate must be a positive whole number'
    if (enc.bitrates === null) return 'Lossless encoders do not take a bitrate'
    if (enc.bitrate_choices.length && !enc.bitrate_choices.includes(bitrate)) return `${bitrate} kb/s is not supported by ${enc.label}`
    if (enc.bitrate_range && (bitrate < enc.bitrate_range[0] || bitrate > enc.bitrate_range[1])) return `${enc.label} takes ${enc.bitrate_range.join(' to ')} kb/s`
    if (layout && enc.per_channel_max && bitrate > enc.per_channel_max * channels(layout)) return `${bitrate} kb/s exceeds the limit for ${layout}`
  }
  if (source && enc.missing.length) return `Needs ${enc.missing.join(', ')}`
  return ''
}

// These are derived from the encoder registry, so common configurations are available immediately.
export function audioPresetDefaults(encodes: AudioEncodeInfo[]): (Preset<AudioPresetSettings> & { builtin: boolean })[] {
  const choices = [{ name: 'copy', label: 'Copy', data: copySettings(), builtin: true }]
  for (const enc of encodes) {
    choices.push({ name: `${enc.id}:auto`, label: 'Encoder defaults',
      data: { action: enc.id, layout: null, bitrate_kbps: null, options: {} }, builtin: true })
    for (const layout of enc.layouts) {
      const rates = Object.keys(enc.bitrates ?? {}).map(Number).sort((a, b) => Math.abs(a - channels(layout)) - Math.abs(b - channels(layout)) || a - b)
      const bitrate = enc.bitrates && !enc.vbr_default ? enc.bitrates[String(rates[0])] ?? null : null
      choices.push({ name: `${enc.id}:${layout}`, label: `${layout} ${bitrate ? `${bitrate} kb/s` : enc.bitrates === null ? 'lossless' : enc.vbr_default ? 'VBR' : 'auto bitrate'}`,
        data: { action: enc.id, layout, bitrate_kbps: bitrate, options: {} }, builtin: true })
    }
  }
  return choices
}
