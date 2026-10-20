import { emptyOverride, isEmpty } from './format'
import type { Overrides, SubTrack } from './types'

export const subtitleLanguage = (t: SubTrack, overrides: Overrides) =>
  (overrides.tracks[t.key]?.language ?? t.language).trim().toLowerCase() || 'und'

export const subtitleFormat = (t: SubTrack) => t.format.trim().toLowerCase() || 'unknown'

// Change all subtitle choices in one save, preserving order and other track edits.
export function selectSubtitles(overrides: Overrides, tracks: SubTrack[], include: (t: SubTrack) => boolean) {
  for (const t of tracks) {
    const on = include(t)
    const ov = overrides.tracks[t.key] ?? emptyOverride()
    ov.exclude = on ? null : true
    // Burn-in is independent of exclusion on the server: leaving a track out must clear it too.
    if (!on) ov.burn = null
    if (isEmpty(ov)) delete overrides.tracks[t.key]
    else overrides.tracks[t.key] = ov
  }
}
