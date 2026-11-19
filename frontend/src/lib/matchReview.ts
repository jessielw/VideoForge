// Review matches: every file of a match preview (unmatched ones, encodes, chapters, subtitles) as one list, with
// its source, how it matched and what to offer, so a person can check and change any of them.

import type { MatchResult, MatchSuggestion, SubtitleMatch } from './types'

/** The matches a person should check: MATCH_NOTE's not-sure ones (a test keeps the two the same). */
export const UNSURE: ReadonlySet<SubtitleMatch> = new Set(['number', 'similar', 'only_source', 'other_episode'])

export type MatchKind = 'video' | 'subtitles' | 'chapters'

export interface MatchEntry {
  path: string
  kind: MatchKind
  source: string | null // null: no source
  reason: SubtitleMatch | null // null for an unmatched file the user didn't set to no source
  suggestions: MatchSuggestion[]
}

const SUBTITLE = /\.(srt|ass|ssa|sup|idx)$/i
const CHAPTERS = /\.(txt|xml)$/i

export function kindOf(path: string): MatchKind {
  return SUBTITLE.test(path) ? 'subtitles' : CHAPTERS.test(path) ? 'chapters' : 'video'
}

/** Unmatched files first, then each job's files in source order (video, chapters, subtitles). Chapters found in
 * StaxRip's temp folder are left out: they aren't inputs, so they can't move. */
export function matchEntries(result: MatchResult): MatchEntry[] {
  const held = new Set(result.held ?? [])
  const out: MatchEntry[] = result.unmatched.map((path) => ({
    path,
    kind: kindOf(path),
    source: null,
    reason: held.has(path) ? 'manual' : null,
    suggestions: result.suggestions?.[path] ?? [],
  }))
  for (const j of result.jobs) {
    const files: [string, MatchKind][] = [
      ...(j.encode ? [[j.encode, 'video'] as [string, MatchKind]] : []),
      ...(j.chapters ? [[j.chapters, 'chapters'] as [string, MatchKind]] : []),
      ...j.subtitles.map((p) => [p, 'subtitles'] as [string, MatchKind]),
    ]
    for (const [path, kind] of files) {
      const reason = j.matches?.[path] ?? null
      if (reason !== 'staxrip') out.push({ path, kind, source: j.source, reason, suggestions: [] })
    }
  }
  return out
}

/** Unmatched (and not set so on purpose), or matched in a way a person should check. */
export function needsLook(e: MatchEntry): boolean {
  return e.reason === null || UNSURE.has(e.reason)
}

/** The entries whose file or source name has every word of the query, case-insensitively. */
export function filterEntries(entries: readonly MatchEntry[], query: string): MatchEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return [...entries]
  const name = (p: string | null) => (p ? (p.split(/[\\/]/).pop() ?? p).toLowerCase() : '')
  return entries.filter((e) => {
    const text = `${name(e.path)} ${name(e.source)}`
    return words.every((w) => text.includes(w))
  })
}

/** The best suggestion for each unmatched file that has one, optionally only those learned from the user's
 * own matches ("pattern"). */
export function suggestedMatches(entries: readonly MatchEntry[], why?: MatchSuggestion['why']): Record<string, string> {
  return Object.fromEntries(
    entries
      .filter((e) => e.reason === null && e.suggestions.length && (!why || e.suggestions[0].why === why))
      .map((e) => [e.path, e.suggestions[0].source]),
  )
}
