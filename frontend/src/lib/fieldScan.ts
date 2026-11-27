// The source's field scan (core/video/fieldscan.py), as the job view sends it (server/views.py field_scan_view):
// what its fields hold, and what the Video tab's Apply sets (core filters.FieldFix).
import type { FieldScanFix, FieldScanReport, VideoSettings } from './types'

// The strip's characters, from the least to the most combing (a cell of several shows the most)
export const STRIP_KINDS = [
  { id: '.', label: 'Too little motion', cell: 'bg-muted' },
  { id: 'P', label: 'Progressive', cell: 'bg-muted-foreground/40' },
  { id: 'T', label: 'Telecine: field matching fixes it', cell: 'bg-primary/70' },
  { id: 'h', label: 'Partly combed after field matching', cell: 'bg-warning' },
  { id: 'I', label: 'Combed after field matching (video)', cell: 'bg-destructive' },
] as const

// m:ss, or h:mm:ss (format.ts duration's, here so the unit tests can load this file alone)
function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const pad = (n: number) => String(n).padStart(2, '0')
  const h = Math.floor(s / 3600)
  const m = Math.floor(s / 60) % 60
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`
}

const rank = (c: string) =>
  Math.max(
    0,
    STRIP_KINDS.findIndex((k) => k.id === c),
  )

export interface StripCell {
  kind: (typeof STRIP_KINDS)[number]
  from: number // seconds
  to: number
}

// The strip in at most `width` cells, each the most combed of the characters it covers, so a short stretch of
// video still shows on a long film.
export function stripCells(report: FieldScanReport, width: number): StripCell[] {
  const { strip, chunk, fps_num, fps_den } = report
  if (!strip.length || width < 1) return []
  const per = Math.max(1, Math.ceil(strip.length / width))
  const seconds = (chars: number) => (fps_num ? (chars * chunk * fps_den) / fps_num : 0)
  const cells: StripCell[] = []
  for (let i = 0; i < strip.length; i += per) {
    const part = strip.slice(i, i + per)
    let worst = 0
    for (const c of part) worst = Math.max(worst, rank(c))
    cells.push({ kind: STRIP_KINDS[worst], from: seconds(i), to: seconds(i + part.length) })
  }
  return cells
}

// The stretches field matching leaves combed, as times: "4:02–4:12 (35 frames)"
export function stretchTimes(report: FieldScanReport, count = 5): string[] {
  const { fps_num, fps_den } = report
  const at = (frame: number) => clock(fps_num ? (frame * fps_den) / fps_num : 0)
  return report.stretches
    .slice(0, count)
    .map(
      ([first, last, frames]) =>
        `${at(first)}${last > first ? `–${at(last)}` : ''} (${frames} frame${frames === 1 ? '' : 's'})`,
    )
}

// The settings with the scan's Apply (core filters.FieldFix.apply): the Field steps out, its step first (Field is
// the chain's first category), and Apply pulldown and the source filter as it needs them.
export function applyFieldFix(video: VideoSettings, fix: FieldScanFix): VideoSettings {
  const rest = video.filters.filter((s) => s.category !== 'field')
  return {
    ...video,
    filters: fix.step ? [{ ...fix.step, enabled: true }, ...rest] : rest,
    pulldown: fix.pulldown,
    source_filter: fix.source_filter,
  }
}

// What Apply changes, for its button's note
export function fixChanges(video: VideoSettings, fix: FieldScanFix): string {
  const fieldSteps = video.filters.filter((s) => s.category === 'field').map((s) => s.name)
  const parts: string[] = []
  if (fix.step) parts.push(`adds ${fix.step.name} first in the chain`)
  if (fieldSteps.length) parts.push(`removes ${fieldSteps.join(', ')}`)
  if (fix.pulldown && !video.pulldown) parts.push('turns on Apply pulldown')
  if (fix.source_filter !== video.source_filter)
    parts.push(`switches the source filter to ${fix.source_filter === 'bestsource' ? 'BestSource' : fix.source_filter}`)
  return parts.length ? `Apply ${parts.join(', ')}.` : ''
}

// What the verdict means, under it in the Scan section
export function verdictNote(r: FieldScanReport): string {
  switch (r.verdict) {
    case 'progressive':
      return 'Each frame is whole: nothing to match or deinterlace. Progressive video stored as fields (PsF) looks interlaced to MediaInfo.'
    case 'telecine':
      return 'Film in 3:2 pulldown. IVTC matches the fields back into 23.976 fps film frames.'
    case 'shifted':
      return 'Progressive video with its fields a frame apart, in no 3:2 pattern. VFM matches them back into whole frames and drops none.'
    case 'hybrid':
      return `Telecined film, but field matching leaves ${r.fallback} frames combed (layers telecined out of step, fades, video). IVTC, with QTGMC on those frames only.`
    case 'interlaced':
      return 'Video: each field is its own moment. Bwdif deinterlaces it; QTGMC from the Field filters is slower.'
    case 'unknown':
      return 'Too little motion to tell. Check the preview for combing.'
  }
}

// The share of moving frames, for the numbers line ("4.0%")
export function share(n: number, of: number): string {
  return of ? `${((100 * n) / of).toFixed(1)}%` : 'n/a'
}
