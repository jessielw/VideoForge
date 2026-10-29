import type { EncodeOptionInfo, Priority, Progress, Severity, Status, TrackOverride, VideoColor, VideoHdr } from './types'

export const PRIORITY_LABEL: Record<Priority, string> = {
  idle: 'Idle',
  below_normal: 'Below normal',
  normal: 'Normal',
  above_normal: 'Above normal',
  high: 'High',
}

export const STATUS_LABEL: Record<Status, string> = {
  probing: 'Probing',
  error: 'Error',
  cropping: 'Detecting crop',
  indexing: 'Indexing',
  'index-queued': 'Index queued',
  ready: 'Ready',
  warn: 'Warn',
  blocked: 'Blocked',
  queued: 'Queued',
  running: 'Running',
  done: 'Done',
  invalid: 'Invalid',
  failed: 'Failed',
  skipped: 'Skipped',
  cancelled: 'Cancelled',
}

/** Tailwind text colour per job status. */
export const STATUS_TONE: Record<Status, string> = {
  probing: 'text-muted-foreground',
  error: 'text-destructive',
  cropping: 'text-muted-foreground',
  indexing: 'text-info',
  'index-queued': 'text-muted-foreground',
  ready: 'text-success',
  warn: 'text-warning',
  blocked: 'text-destructive',
  queued: 'text-info',
  running: 'text-info',
  done: 'text-success',
  invalid: 'text-destructive',
  failed: 'text-destructive',
  skipped: 'text-warning',
  cancelled: 'text-warning',
}

export const SEVERITY_TONE: Record<Severity, string> = {
  block: 'text-destructive',
  warn: 'text-warning',
  info: 'text-muted-foreground',
}

export function basename(path: string | null | undefined): string {
  if (!path) return ''
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path
}

// A saved preview frame's file name: the source's name, the frame number padded to the clip's length
// (so a folder of them sorts in frame order), and the crop view marked (its frame has the margins on).
export function frameFilename(source: string, n: number, frames: number, stage: 'crop' | 'output'): string {
  const stem = basename(source).replace(/\.[^.]+$/, '')
  const safe = stem.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[. ]+$/g, '').slice(0, 120) || 'frame'
  const num = String(n).padStart(String(Math.max(frames - 1, 0)).length, '0')
  return `${safe} - ${num}${stage === 'crop' ? ' (crop view)' : ''}.png`
}

export function bytes(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`
}

export function percent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`
}

/** Seconds as m:ss, or h:mm:ss from an hour. */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const pad = (n: number) => String(n).padStart(2, '0')
  const h = Math.floor(s / 3600)
  const m = Math.floor(s / 60) % 60
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`
}

/** A run's speed and times for one line: "23.4 fps · 1:23 · ~4:56 left" (what the run has so far). */
export function progressTimes(p: Progress): string {
  return [
    p.fps !== null && p.fps !== undefined ? `${p.fps < 10 ? p.fps.toFixed(2) : p.fps.toFixed(1)} fps` : '',
    p.elapsed !== undefined ? duration(p.elapsed) : '',
    p.left !== null && p.left !== undefined ? `~${duration(p.left)} left` : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

/** Languages offered in pickers; any other IETF tag can be typed. */
export const LANGUAGES: [string, string][] = [
  ['en', 'English'],
  ['ja', 'Japanese'],
  ['ko', 'Korean'],
  ['zh-Hans', 'Chinese (Simplified)'],
  ['zh-Hant', 'Chinese (Traditional)'],
  ['yue', 'Cantonese'],
  ['nl', 'Dutch'],
  ['fr-FR', 'French (France)'],
  ['fr-CA', 'French (Canada)'],
  ['de', 'German'],
  ['es-419', 'Spanish (Latin America)'],
  ['es-ES', 'Spanish (Spain)'],
  ['it', 'Italian'],
  ['pt', 'Portuguese'],
]

// The rest of the languages the server names (core/lang.py), whole families too: the picker lists these
// after the common ones.
const MORE_LANGUAGES: [string, string][] = [
  ['ar', 'Arabic'], ['eu', 'Basque'], ['bg', 'Bulgarian'], ['ca', 'Catalan'], ['zh', 'Chinese'],
  ['hr', 'Croatian'], ['cs', 'Czech'], ['da', 'Danish'], ['et', 'Estonian'], ['fil', 'Filipino'],
  ['fi', 'Finnish'], ['fr', 'French'], ['gl', 'Galician'], ['el', 'Greek'], ['he', 'Hebrew'],
  ['hi', 'Hindi'], ['hu', 'Hungarian'], ['is', 'Icelandic'], ['id', 'Indonesian'], ['kn', 'Kannada'],
  ['kk', 'Kazakh'], ['lv', 'Latvian'], ['lt', 'Lithuanian'], ['ms', 'Malay'], ['ml', 'Malayalam'],
  ['no', 'Norwegian'], ['fa', 'Persian'], ['pl', 'Polish'], ['pt-BR', 'Portuguese (Brazil)'], ['ro', 'Romanian'],
  ['ru', 'Russian'], ['sr', 'Serbian'], ['sk', 'Slovak'], ['sl', 'Slovenian'], ['es', 'Spanish'],
  ['sv', 'Swedish'], ['tl', 'Tagalog'], ['ta', 'Tamil'], ['te', 'Telugu'], ['th', 'Thai'],
  ['tr', 'Turkish'], ['uk', 'Ukrainian'], ['vi', 'Vietnamese'],
]
export const PICKER_LANGUAGES: [string, string][] = [...LANGUAGES, ...MORE_LANGUAGES, ['und', 'Unknown']]

const displayNames = new Intl.DisplayNames(['en'], { type: 'language' })
/** A language tag's English name: the picker's own, else the browser's, else the tag ("eng" -> "English"). */
export function languageName(tag: string): string {
  const t = tag.trim()
  const known = PICKER_LANGUAGES.find(([code]) => code.toLowerCase() === t.toLowerCase())?.[1]
  if (known) return known
  try {
    return displayNames.of(t) ?? t
  } catch {
    return t
  }
}

/** A subtitle's title from its language and flags: "English", "English (Forced)", "Spanish (Latin America) (SDH)".
 * The same names as the server's (core/template.py sub_title), which templates use. */
export function subtitleName(language: string, flags: { forced?: boolean; hearing_impaired?: boolean; commentary?: boolean }): string {
  const tags = [flags.forced && 'Forced', flags.hearing_impaired && 'SDH', flags.commentary && 'Commentary'].filter(Boolean)
  return [languageName(language.trim() || 'und'), ...tags.map(t => `(${t})`)].join(' ')
}

export function debounce<A extends unknown[]>(fn: (...a: A) => void, ms: number): (...a: A) => void {
  let t: ReturnType<typeof setTimeout> | undefined
  return (...a: A) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...a), ms)
  }
}

// An encode's options to show: one used only with another's value (loudnorm's targets) only then.
export function shownOptions(options: EncodeOptionInfo[], valueOf: (o: EncodeOptionInfo) => string): EncodeOptionInfo[] {
  return options.filter(o => {
    const by = o.when && options.find(x => x.key === o.when?.key)
    return !by || valueOf(by) === o.when?.value
  })
}

export function emptyOverride(): TrackOverride {
  return { exclude: null, language: null, title: null, flags: {}, action: null, bitrate_kbps: null, layout: null, options: {} }
}

// An override that changes nothing (the server drops those too).
export function isEmpty(ov: TrackOverride): boolean {
  return (
    ov.exclude === null &&
    (ov.burn ?? null) === null &&
    ov.language === null &&
    ov.title === null &&
    !Object.keys(ov.flags).length &&
    ov.action === null &&
    ov.bitrate_kbps === null &&
    ov.layout === null &&
    !Object.keys(ov.options ?? {}).length &&
    !ov.sync_ms
  )
}

// The source's HDR formats: ['HDR10', 'HDR10+', 'Dolby Vision 7.6 FEL (BL+EL+RPU)']; [] for SDR.
export function hdrFormats(color: VideoColor, hdr: VideoHdr | undefined): string[] {
  const out = []
  if (color.transfer === 'arib-std-b67') out.push('HLG')
  else if (color.transfer === 'smpte2084') out.push(color.master_display || color.max_cll ? 'HDR10' : 'PQ')
  if (hdr?.hdr10plus) out.push('HDR10+')
  if (hdr?.dv_profile) {
    const name = `${hdr.dv_profile}${hdr.dv_compat !== null ? `.${hdr.dv_compat}` : ''}${hdr.dv_el ? ` ${hdr.dv_el}` : ''}`
    out.push(`Dolby Vision ${name}${hdr.dv_layers ? ` (${hdr.dv_layers})` : ''}`)
  }
  return out
}

// A clip's running time (frames / fps) as h:mm:ss.mmm.
export function clipLength(frames: number, fpsNum: number, fpsDen: number): string {
  if (!fpsNum) return '?'
  const ms = Math.round((frames * fpsDen * 1000) / fpsNum)
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor(ms / 60_000) % 60
  const s = Math.floor(ms / 1000) % 60
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${h}:${pad(m)}:${pad(s)}.${pad(ms % 1000, 3)}`
}
