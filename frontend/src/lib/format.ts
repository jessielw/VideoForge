import type {
  EncodeOptionInfo,
  JobSummary,
  PreviewStage,
  Priority,
  Progress,
  Severity,
  Status,
  TrackOverride,
  VideoColor,
  VideoHdr,
} from './types'

export const PRIORITY_LABEL: Record<Priority, string> = {
  idle: 'Idle',
  below_normal: 'Below normal',
  normal: 'Normal',
  above_normal: 'Above normal',
  high: 'High',
}

export const STATUS_LABEL: Record<Status, string> = {
  probing: 'Reading tracks',
  error: 'Error',
  cropping: 'Detecting crop',
  indexing: 'Indexing',
  sampling: 'Test encode',
  'index-queued': 'Waiting to index',
  ready: 'Ready',
  warn: 'Ready with warnings',
  blocked: 'Blocked',
  queued: 'Queued',
  running: 'Running',
  done: 'Done',
  invalid: 'Invalid',
  failed: 'Failed',
  skipped: 'Skipped',
  cancelled: 'Canceled',
  paused: 'Paused after pass 1',
}

/** Tailwind text colour per job status. */
export const STATUS_TONE: Record<Status, string> = {
  probing: 'text-muted-foreground',
  error: 'text-destructive',
  cropping: 'text-muted-foreground',
  indexing: 'text-info',
  sampling: 'text-info',
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
  paused: 'text-info',
}

export const SEVERITY_TONE: Record<Severity, string> = {
  block: 'text-destructive',
  warn: 'text-warning',
  info: 'text-muted-foreground',
}

/** A job's errors and warnings as counts ("1 error", "2 warnings"), leaving out a kind with none. */
export function issueCounts(counts: { block: number; warn: number }): string[] {
  return [
    counts.block ? `${counts.block} ${counts.block === 1 ? 'error' : 'errors'}` : '',
    counts.warn ? `${counts.warn} ${counts.warn === 1 ? 'warning' : 'warnings'}` : '',
  ].filter(Boolean)
}

export function basename(path: string | null | undefined): string {
  if (!path) return ''
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path
}

// A saved preview frame's file name: the source's name, the frame number padded to the clip's length
// (so a folder of them sorts in frame order), and the crop view marked (its frame has the margins on), as are the
// compare's frames (a test encode's are numbered by the sample's frames).
const STAGE_MARK: Record<PreviewStage, string> = {
  crop: ' (crop view)',
  output: '',
  unfiltered: ' (unfiltered)',
  encode: ' (encode)',
  'sample-in': ' (test encode input)',
  sample: ' (test encode)',
}

export function frameFilename(source: string, n: number, frames: number, stage: PreviewStage): string {
  const stem = basename(source).replace(/\.[^.]+$/, '')
  const safe =
    stem
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
      .replace(/[. ]+$/g, '')
      .slice(0, 120) || 'frame'
  const num = String(n).padStart(String(Math.max(frames - 1, 0)).length, '0')
  return `${safe} - ${num}${STAGE_MARK[stage]}.png`
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

/** A size as the server sends it ("1920x1040", or a rule set's class like "1080p"), with a times sign for display. */
export function sizeLabel(resolution: string): string {
  return resolution.replace(/^(\d+)x(\d+)$/, '$1×$2')
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
  ['ar', 'Arabic'],
  ['eu', 'Basque'],
  ['bg', 'Bulgarian'],
  ['ca', 'Catalan'],
  ['zh', 'Chinese'],
  ['hr', 'Croatian'],
  ['cs', 'Czech'],
  ['da', 'Danish'],
  ['et', 'Estonian'],
  ['fil', 'Filipino'],
  ['fi', 'Finnish'],
  ['fr', 'French'],
  ['gl', 'Galician'],
  ['el', 'Greek'],
  ['he', 'Hebrew'],
  ['hi', 'Hindi'],
  ['hu', 'Hungarian'],
  ['is', 'Icelandic'],
  ['id', 'Indonesian'],
  ['kn', 'Kannada'],
  ['kk', 'Kazakh'],
  ['lv', 'Latvian'],
  ['lt', 'Lithuanian'],
  ['ms', 'Malay'],
  ['ml', 'Malayalam'],
  ['no', 'Norwegian'],
  ['fa', 'Persian'],
  ['pl', 'Polish'],
  ['pt-BR', 'Portuguese (Brazil)'],
  ['ro', 'Romanian'],
  ['ru', 'Russian'],
  ['sr', 'Serbian'],
  ['sk', 'Slovak'],
  ['sl', 'Slovenian'],
  ['es', 'Spanish'],
  ['sv', 'Swedish'],
  ['tl', 'Tagalog'],
  ['ta', 'Tamil'],
  ['te', 'Telugu'],
  ['th', 'Thai'],
  ['tr', 'Turkish'],
  ['uk', 'Ukrainian'],
  ['vi', 'Vietnamese'],
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

const SHORT_COMMERCIAL: [RegExp, string][] = [
  [/^DTS-HD Master Audio$/i, 'DTS-HD MA'],
  [/^DTS-HD High Resolution(?: Audio)?$/i, 'DTS-HD HRA'],
  [/^Dolby Digital Plus/i, 'DD+'],
  [/^Dolby Digital$/i, 'DD'],
]
/** An audio track's format as it is sold: MediaInfo's commercial name ("DTS-HD MA", "Dolby TrueHD with Dolby Atmos"),
 * else its raw format ("DTS"), else the codec. */
export function audioFormat(t: { commercial_name?: string; format_name: string; codec: string }): string {
  const c = t.commercial_name?.trim()
  if (!c) return t.format_name || t.codec
  return SHORT_COMMERCIAL.find(([re]) => re.test(c))?.[1] ?? c
}

/** `fmt` with " Atmos" / " DTS:X" added when the track carries it and `fmt` does not already say so
 * (MediaInfo's commercial name "Dolby TrueHD with Dolby Atmos" already does). */
export function withImmersive(fmt: string, t: { atmos?: boolean; dtsx?: boolean }): string {
  if (t.atmos && !/atmos/i.test(fmt)) return `${fmt} Atmos`
  if (!t.atmos && t.dtsx && !/dts:?x/i.test(fmt)) return `${fmt} DTS:X`
  return fmt
}

/** A subtitle's title from its language and flags: "English", "English (Forced)", "Spanish (Latin America) (SDH)".
 * The same names as the server's (core/template.py sub_title), which templates use. */
export function subtitleName(
  language: string,
  flags: { forced?: boolean; hearing_impaired?: boolean; commentary?: boolean },
): string {
  const tags = [flags.forced && 'Forced', flags.hearing_impaired && 'SDH', flags.commentary && 'Commentary'].filter(
    Boolean,
  )
  return [languageName(language.trim() || 'und'), ...tags.map((t) => `(${t})`)].join(' ')
}

export function debounce<A extends unknown[]>(fn: (...a: A) => void, ms: number): (...a: A) => void {
  let t: ReturnType<typeof setTimeout> | undefined
  return (...a: A) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...a), ms)
  }
}

// An encode's options to show: one used only with another's value (loudnorm's targets) only then.
export function shownOptions(
  options: EncodeOptionInfo[],
  valueOf: (o: EncodeOptionInfo) => string,
): EncodeOptionInfo[] {
  return options.filter((o) => {
    const by = o.when && options.find((x) => x.key === o.when?.key)
    return !by || valueOf(by) === o.when?.value
  })
}

export function emptyOverride(): TrackOverride {
  return {
    exclude: null,
    language: null,
    title: null,
    flags: {},
    action: null,
    bitrate_kbps: null,
    layout: null,
    options: {},
  }
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

// A time in seconds as h:mm:ss.mmm (the frame preview's position).
export function timecode(seconds: number): string {
  const ms = Math.max(0, Math.round(seconds * 1000))
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${Math.floor(ms / 3_600_000)}:${pad(Math.floor(ms / 60_000) % 60)}:${pad(Math.floor(ms / 1000) % 60)}.${pad(ms % 1000, 3)}`
}

// What the frame preview's box was given, as a frame: a frame number (`1234`), or a time as
// [[h:]m:]s (`1:23.5`, `1:02:03.250`) or seconds (`83.5s`). The time's frame is the one it rounds to,
// so a time shown by `timecode` comes back as its own frame. Null when it's neither.
export function parseSeek(text: string, fps: number): number | null {
  const t = text.trim().replace(',', '.')
  if (/^\d+$/.test(t)) return +t
  let seconds: number
  const secs = /^(\d+(?:\.\d*)?|\.\d+)\s*s$/i.exec(t)
  if (secs) seconds = +secs[1]
  else if (/^\d+(:\d+){1,2}(\.\d*)?$/.test(t)) {
    const parts = t.split(':').map(Number)
    if (parts.slice(1).some((p) => p >= 60)) return null
    seconds = parts.reduce((total, p) => total * 60 + p, 0)
  } else return null
  return Math.round(seconds * (fps || 24))
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

export type FactKey = 'resolution' | 'length' | 'interlaced' | 'hdr' | 'encoder' | 'extras' | 'audio' | 'subs'
/** One fact of a job's facts line, as shown; `tags` is the HDR set (shown as badges). */
export interface Fact {
  key: FactKey
  text: string
  tags?: string[]
}

/** A job's facts, in the order its row shows them; one it has no value for (or no source facts yet) is left out. */
export function jobFacts(job: JobSummary): Fact[] {
  const f = job.source_facts
  const c = job.crop
  const facts: (Fact | false | null | undefined)[] = [
    f && { key: 'resolution', text: sizeLabel(f.resolution) },
    !!f?.duration_ms && { key: 'length', text: duration(f.duration_ms / 1000) },
    f?.interlaced && { key: 'interlaced', text: 'interlaced' },
    !!f?.hdr.length && { key: 'hdr', text: f.hdr.join(' '), tags: f.hdr },
    { key: 'encoder', text: job.encoder },
    job.custom_script
      ? { key: 'extras', text: 'custom script' }
      : c &&
        !!(c.top || c.bottom || c.left || c.right) && {
          key: 'extras',
          text: `crop ${c.left}/${c.top}/${c.right}/${c.bottom}`,
        },
    { key: 'audio', text: `${job.audio.length} audio` },
    { key: 'subs', text: `${job.subs} subs` },
  ]
  return facts.filter((x) => !!x)
}

/** A facts line as one string, the HDR set as its tags. */
export function factsText(facts: Fact[]): string {
  return facts.flatMap((f) => f.tags ?? f.text).join(' · ')
}

/** Whether a facts line has a Dolby Vision tag that ends in "?" (profile 7, enhancement layer not read yet). */
export const needsDvNote = (facts: Fact[]): boolean => facts.some((f) => f.tags?.some((n) => n.endsWith('?')))

/** "1 job", "3 jobs": a count with a regular "s" plural. */
export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}
