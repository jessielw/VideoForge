import type { AudioEncodeInfo, AudioPresetSettings, AudioTrack, Preset, TrackOverride } from './types'

export const channels = (layout: string) => layout.split('.').reduce((sum, part) => sum + Number(part), 0)
const copySettings = (): AudioPresetSettings => ({
  action: 'copy',
  layout: null,
  bitrate_kbps: null,
  options: {},
  title: null,
})

const speakers = (layout: string) => layout.split('.').map(Number) as [number, number]

// The encode as its options make it (AudioEncode.configured): a mode such as DDP's Blu-ray or a 7.1 Atmos mode
// brings its own layouts and bitrates. An option left out counts as its default.
export function configuredEncode(enc: AudioEncodeInfo, options: Record<string, string> = {}): AudioEncodeInfo {
  const chosen = (key: string) => options[key] ?? enc.options.find((o) => o.key === key)?.default
  const mode = enc.modes.find((m) => chosen(m.key) === m.value)
  if (!mode) return enc
  const { key: _key, value: _value, ...limits } = mode
  return { ...enc, ...limits }
}

export function audioEncodeLayouts(enc: AudioEncodeInfo, options: Record<string, string> = {}): string[] {
  return configuredEncode(enc, options).layouts
}

// The bitrates a (configured) encode takes at a layout, when it takes only some ([] = any in its range). Auto
// channels count as the encode's one layout, when it has one.
export function bitrateChoices(enc: AudioEncodeInfo, layout: string | null): number[] {
  if (enc.bitrate_choices.length) return enc.bitrate_choices
  const at = layout ?? (enc.layouts.length === 1 ? enc.layouts[0] : null)
  return (at && enc.layout_rates[at]) || []
}

// True when this layout needs speakers the source doesn't have (AudioEncode.upmixes): more channels, or for an
// encode that codes the source's own speakers, a center or LFE it lacks. DDP may make 5.1 from 5.0.
export function upmixes(enc: AudioEncodeInfo, source: string, layout: string): boolean {
  if (enc.id === 'ddp' && source === '5.0' && layout === '5.1') return false
  const [main, lfe] = speakers(layout)
  const [srcMain, srcLfe] = speakers(source)
  return channels(layout) > channels(source) || (enc.adds_no_speakers && (main > srcMain || lfe > srcLfe))
}

// Why a (configured) encode won't take this bitrate at this layout ('' when it will). null layout: not known yet.
export function bitrateProblem(enc: AudioEncodeInfo, bitrate: number, layout: string | null): string {
  if (!Number.isInteger(bitrate) || bitrate <= 0) return 'Bitrate must be a positive whole number'
  if (enc.bitrates === null) return 'Lossless encoders do not take a bitrate'
  if (enc.bitrate_choices.length && !enc.bitrate_choices.includes(bitrate))
    return `${bitrate} kb/s is not supported by ${enc.label}`
  if (enc.bitrate_range && (bitrate < enc.bitrate_range[0] || bitrate > enc.bitrate_range[1]))
    return `${enc.label} takes ${enc.bitrate_range.join(' to ')} kb/s`
  if (layout && enc.per_channel_max && bitrate > enc.per_channel_max * channels(layout))
    return `${bitrate} kb/s exceeds the limit for ${layout}`
  const rates = bitrateChoices({ ...enc, bitrate_choices: [] }, layout)
  if (rates.length && !rates.includes(bitrate)) {
    const near = [rates.filter((r) => r < bitrate).at(-1), rates.find((r) => r > bitrate)].filter((r) => r)
    return `${enc.label} at ${layout ?? enc.layouts[0]} takes ${near.join(' or ')} kb/s, not ${bitrate}`
  }
  return ''
}

// A layout and bitrate after the encode, its options or the layout changed: each one it no longer takes goes back
// to auto (a bitrate goes with the layout it was set for).
export function fitLayoutAndBitrate(
  enc: AudioEncodeInfo,
  options: Record<string, string>,
  layout: string | null,
  bitrate: number | null,
): { layout: string | null; bitrate_kbps: number | null } {
  const conf = configuredEncode(enc, options)
  const fitted = layout && conf.layouts.includes(layout) ? layout : null
  const keep = bitrate !== null && !bitrateProblem(conf, bitrate, fitted)
  return { layout: fitted, bitrate_kbps: keep ? bitrate : null }
}

export function audioPresetSettings(value?: Partial<TrackOverride>): AudioPresetSettings {
  const title = { title: value?.title ?? null }
  if (!value?.action || value.action === 'copy') return { ...copySettings(), ...title }
  return {
    action: value.action,
    layout: value.layout ?? null,
    bitrate_kbps: value.bitrate_kbps ?? null,
    options: { ...value.options },
    ...title,
  }
}

export function applyAudioPreset(value: TrackOverride, preset: AudioPresetSettings): TrackOverride {
  const settings = preset.action === 'copy' ? copySettings() : preset
  return {
    ...value,
    action: settings.action,
    layout: settings.layout,
    bitrate_kbps: settings.bitrate_kbps,
    options: { ...settings.options },
    ...(preset.title != null ? { title: preset.title } : {}),
  }
}

// AudioEncode.default_layout: the source's own layout when the encode takes it, else the biggest that fits.
function defaultLayout(enc: AudioEncodeInfo, source: string): string {
  const cap = enc.default_max ? Math.min(channels(source), channels(enc.default_max)) : channels(source)
  const fits = enc.layouts.filter((layout) => channels(layout) <= cap && !upmixes(enc, source, layout))
  if (fits.includes(source)) return source
  return (
    fits.sort((a, b) => channels(b) - channels(a) || Number(b.split('.')[1]) - Number(a.split('.')[1]))[0] ??
    enc.layouts[0]
  )
}

export function audioPresetProblem(
  settings: AudioPresetSettings,
  encodes: AudioEncodeInfo[],
  source?: AudioTrack,
): string {
  if (settings.action === 'copy') return ''
  let problem = ''
  const enc = encodes.find((e) => e.id === settings.action)
  if (!enc) return 'Encoder information is unavailable'
  const conf = configuredEncode(enc, settings.options)
  if (settings.layout && !conf.layouts.includes(settings.layout))
    return `${enc.label} does not support ${settings.layout} in this mode`
  if (source && settings.action === 'atmos' && !(source.codec === 'truehd' && source.atmos))
    return 'Requires a TrueHD Atmos source'
  const layout =
    settings.layout ??
    (source ? defaultLayout(conf, source.layout) : conf.layouts.length === 1 ? conf.layouts[0] : null)
  // Atmos is rendered from the source's objects: its bed is the mode's, whatever the TrueHD core has
  if (source && layout && enc.id !== 'atmos' && upmixes(conf, source.layout, layout))
    return channels(layout) > channels(source.layout)
      ? `${layout} requires more channels than this ${source.layout} source`
      : `${layout} adds a speaker this ${source.layout} source doesn't have`
  const bitrate = settings.bitrate_kbps
  if (bitrate !== null && (problem = bitrateProblem(conf, bitrate, layout))) return problem
  if (source && enc.missing.length) return `Needs ${enc.missing.join(', ')}`
  return ''
}

// These are derived from the encoder registry, so common configurations are available immediately.
export function audioPresetDefaults(
  encodes: AudioEncodeInfo[],
): (Preset<AudioPresetSettings> & { builtin: boolean })[] {
  const choices = [{ name: 'copy', label: 'Copy', data: copySettings(), builtin: true }]
  for (const enc of encodes) {
    choices.push({
      name: `${enc.id}:auto`,
      label: 'Encoder defaults',
      data: { action: enc.id, layout: null, bitrate_kbps: null, options: {}, title: null },
      builtin: true,
    })
    // one per layout, and per layout of each mode (DDP Blu-ray 7.1, the 7.1 Atmos modes), named after the mode
    const modes = [
      { conf: enc, options: {} as Record<string, string>, name: '', note: '' },
      ...enc.modes.map((m) => {
        const choice = enc.options.find((o) => o.key === m.key)?.choices.find((c) => c.value === m.value)
        const note = ` · ${(choice?.label ?? m.value).replace(/\s*\(.*\)$/, '')}`
        return {
          conf: configuredEncode(enc, { [m.key]: m.value }),
          options: { [m.key]: m.value },
          name: `${m.key}=${m.value}:`,
          note,
        }
      }),
    ]
    for (const { conf, options, name, note } of modes) {
      for (const layout of conf.layouts) {
        const rates = Object.keys(conf.bitrates ?? {})
          .map(Number)
          .sort((a, b) => Math.abs(a - channels(layout)) - Math.abs(b - channels(layout)) || a - b)
        const bitrate = conf.bitrates && !conf.vbr_default ? (conf.bitrates[String(rates[0])] ?? null) : null
        choices.push({
          name: `${enc.id}:${name}${layout}`,
          label: `${layout} ${bitrate ? `${bitrate} kb/s` : conf.bitrates === null ? 'lossless' : conf.vbr_default ? 'VBR' : 'auto bitrate'}${note}`,
          data: { action: enc.id, layout, bitrate_kbps: bitrate, options: { ...options }, title: null },
          builtin: true,
        })
      }
    }
  }
  return choices
}
