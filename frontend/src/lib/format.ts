import type { Progress, Severity, Status, TrackOverride, VideoColor, VideoHdr } from './types'

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

export function debounce<A extends unknown[]>(fn: (...a: A) => void, ms: number): (...a: A) => void {
  let t: ReturnType<typeof setTimeout> | undefined
  return (...a: A) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...a), ms)
  }
}

export function emptyOverride(): TrackOverride {
  return { exclude: null, language: null, title: null, flags: {}, action: null, bitrate_kbps: null, layout: null, options: {} }
}

// An override that changes nothing (the server drops those too).
export function isEmpty(ov: TrackOverride): boolean {
  return (
    ov.exclude === null &&
    ov.language === null &&
    ov.title === null &&
    !Object.keys(ov.flags).length &&
    ov.action === null &&
    ov.bitrate_kbps === null &&
    ov.layout === null &&
    !Object.keys(ov.options ?? {}).length
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
