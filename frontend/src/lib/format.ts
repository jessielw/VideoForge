import type { Severity, Status, TrackOverride } from './types'

export const STATUS_LABEL: Record<Status, string> = {
  probing: 'Probing',
  error: 'Error',
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
  probing: 'text-muted',
  error: 'text-bad',
  ready: 'text-ok',
  warn: 'text-warn',
  blocked: 'text-bad',
  queued: 'text-info',
  running: 'text-info',
  done: 'text-ok',
  invalid: 'text-bad',
  failed: 'text-bad',
  skipped: 'text-warn',
  cancelled: 'text-warn',
}

export const SEVERITY_TONE: Record<Severity, string> = {
  block: 'text-bad',
  warn: 'text-warn',
  info: 'text-muted',
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
