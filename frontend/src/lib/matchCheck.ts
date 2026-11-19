// Checks on Matched files before Add: which jobs have a different number of subtitles than most do, so a
// missing synced file or an extra extracted one shows at a glance; how sure each subtitle's match is; and
// which part of a subtitle's name differs from its source's.

import type { SubtitleMatch } from './types'

/** What each match reason means, for the icon's tooltip; `sure` is false where a person should look. */
export const MATCH_NOTE: Record<SubtitleMatch, { text: string; sure: boolean }> = {
  manual: { text: 'You matched it to this source', sure: true },
  name: { text: 'Starts with the source’s name', sure: true },
  episode: { text: 'Same episode as the source', sure: true },
  number: { text: 'Its number lines up with this source’s, in a set of files named alike; check it', sure: false },
  similar: { text: 'Its name is closest to this source’s; check it', sure: false },
  staxrip: { text: 'From StaxRip’s temp folder for this source', sure: true },
  only_source: { text: 'Taken by the only source; nothing in its name ties it to that source', sure: false },
  other_episode: { text: 'Taken by the only source, but its name is for another episode', sure: false },
}

/** A subtitle's file name split at the end of what it shares with its source's (cut at a separator, so
 * "Show.S01E01." and not "Show.S01E0"), so the part that tells subtitles apart can stand out. */
export function nameParts(name: string, source: string): { shared: string; rest: string } {
  const stem = source.replace(/\.[^.]+$/, '') + '.'
  let n = 0
  while (n < name.length && n < stem.length && name[n].toLowerCase() === stem[n].toLowerCase()) n++
  while (n > 0 && !/[.\s_\-[\]()]/.test(name[n - 1])) n--
  return n < name.length ? { shared: name.slice(0, n), rest: name.slice(n) } : { shared: '', rest: name }
}

/** Ticked subtitles whose name is for a different episode than their job's source. */
export function wrongEpisodeCount(
  jobs: readonly { subtitle_info: readonly { path: string; match: SubtitleMatch | null }[] }[],
  excluded: readonly string[],
): number {
  const off = new Set(excluded)
  return jobs.flatMap((j) => j.subtitle_info).filter((s) => s.match === 'other_episode' && !off.has(s.path)).length
}

export interface OddSubtitles {
  count: number // this job's subtitles, less the unticked ones
  usual: number // what most jobs in the batch have
}

/** The jobs whose subtitle count isn't the batch's usual one, by source. Empty for one job, or no subtitles. */
export function oddSubtitleRows(
  jobs: readonly { source: string; subtitles: readonly string[] }[],
  excluded: readonly string[],
): Map<string, OddSubtitles> {
  const odd = new Map<string, OddSubtitles>()
  if (jobs.length < 2) return odd
  const off = new Set(excluded)
  const counts = jobs.map((j) => j.subtitles.filter((p) => !off.has(p)).length)
  if (counts.every((n) => n === 0)) return odd
  const tally = new Map<number, number>()
  for (const n of counts) tally.set(n, (tally.get(n) ?? 0) + 1)
  // The most common count; on a tie, the larger one (a missing file is likelier than an extra one).
  const usual = [...tally].sort(([a, x], [b, y]) => y - x || b - a)[0][0]
  jobs.forEach((j, i) => {
    if (counts[i] !== usual) odd.set(j.source, { count: counts[i], usual })
  })
  return odd
}

/** The Matched files header's words for the odd rows, or '' when there are none. */
export function oddSummary(odd: ReadonlyMap<string, OddSubtitles>): string {
  const without = [...odd.values()].filter((o) => o.count === 0).length
  const other = odd.size - without
  return [
    without ? `${without} without subtitles` : '',
    other ? `${other} with ${other === 1 ? 'a different number' : 'different numbers'} of subtitles` : '',
  ]
    .filter(Boolean)
    .join(' · ')
}
