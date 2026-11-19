// Checks on Matched files before Add: which jobs have a different number of subtitles than most do, so a
// missing synced file or an extra extracted one shows at a glance.

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
