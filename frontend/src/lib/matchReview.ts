// Review matches: every file of a match preview (unmatched ones, encodes, chapters, subtitles) as one list, with
// its source, how it matched, what that went on, what clashes with it and what to offer, so a person can check
// and change any of them.

import type { MatchResult, MatchSuggestion, SubtitleLabel, SubtitleMatch } from './types'

/** The matches a person should check: MATCH_NOTE's not-sure ones (a test keeps the two the same). */
export const UNSURE: ReadonlySet<SubtitleMatch> = new Set(['number', 'similar', 'only_source', 'other_episode'])

export type MatchKind = 'video' | 'subtitles' | 'chapters'

export interface MatchEntry {
  path: string
  kind: MatchKind
  source: string | null // null: no source
  reason: SubtitleMatch | null // null for an unmatched file the user didn't set to no source
  detail: string // for a guess, what it went on
  conflict: string // what clashes with it: its source already has one of its kind, or a subtitle like it
  pattern: string | null // the remembered pattern it matched by (its shape), to forget
  suggestions: MatchSuggestion[]
}

const SUBTITLE = /\.(srt|ass|ssa|sup|idx)$/i
const CHAPTERS = /\.(txt|xml)$/i
const nameOf = (p: string) => p.split(/[\\/]/).pop() ?? p

export function kindOf(path: string): MatchKind {
  return SUBTITLE.test(path) ? 'subtitles' : CHAPTERS.test(path) ? 'chapters' : 'video'
}

/** A job's subtitles that look like the same track twice: same language, format and forced/SDH/dub tags
 * ("synced" doesn't count), leaving out the unticked ones. Each group has two files or more. */
export function duplicateSubtitles(info: readonly SubtitleLabel[], excluded: readonly string[] = []): string[][] {
  const off = new Set(excluded)
  const groups = new Map<string, string[]>()
  for (const s of info) {
    if (off.has(s.path)) continue
    const key = [s.language, s.format, ...s.tags.filter((t) => t !== 'synced').sort()].join('|')
    groups.set(key, [...(groups.get(key) ?? []), s.path])
  }
  return [...groups.values()].filter((g) => g.length > 1)
}

/** Unmatched files first, then each job's files in source order (video, chapters, subtitles). Chapters found in
 * StaxRip's temp folder are left out: they aren't inputs, so they can't move. */
export function matchEntries(result: MatchResult): MatchEntry[] {
  const held = new Set(result.held ?? [])
  const bySource = new Map(result.jobs.map((j) => [j.source, j]))
  const out: MatchEntry[] = result.unmatched.map((path) => {
    const kind = kindOf(path)
    const lostTo = result.spare?.[path]
    const has = lostTo ? (kind === 'video' ? bySource.get(lostTo)?.encode : bySource.get(lostTo)?.chapters) : null
    return {
      path,
      kind,
      source: null,
      reason: held.has(path) ? 'manual' : null,
      detail: '',
      conflict: lostTo
        ? `Left over: ${nameOf(lostTo)} already has ${kind === 'video' ? 'an encode' : 'chapters'}${has ? `, ${nameOf(has)}` : ''}`
        : '',
      pattern: null,
      suggestions: result.suggestions?.[path] ?? [],
    }
  })
  for (const j of result.jobs) {
    const twins = new Map<string, string[]>()
    for (const group of duplicateSubtitles(j.subtitle_info ?? [])) for (const p of group) twins.set(p, group)
    const files: [string, MatchKind][] = [
      ...(j.encode ? [[j.encode, 'video'] as [string, MatchKind]] : []),
      ...(j.chapters ? [[j.chapters, 'chapters'] as [string, MatchKind]] : []),
      ...j.subtitles.map((p) => [p, 'subtitles'] as [string, MatchKind]),
    ]
    for (const [path, kind] of files) {
      const reason = j.matches?.[path] ?? null
      if (reason === 'staxrip') continue
      const others = (twins.get(path) ?? []).filter((p) => p !== path).map(nameOf)
      out.push({
        path,
        kind,
        source: j.source,
        reason,
        detail: j.details?.[path] ?? '',
        conflict: others.length ? `Same language and type as ${others.join(', ')}` : '',
        pattern: j.patterns?.[path] ?? null,
        suggestions: [],
      })
    }
  }
  return out
}

/** Unmatched (and not set so on purpose), matched in a way a person should check, or clashing with another. */
export function needsLook(e: MatchEntry): boolean {
  return e.reason === null || UNSURE.has(e.reason) || !!e.conflict
}

/** The entries whose file or source name has every word of the query, case-insensitively. */
export function filterEntries(entries: readonly MatchEntry[], query: string): MatchEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return [...entries]
  return entries.filter((e) => {
    const text = `${nameOf(e.path)} ${e.source ? nameOf(e.source) : ''}`.toLowerCase()
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

/** Paths from `from` to `to` in the order shown (either way round), for a Shift+click range. */
export function rangeOf(order: readonly string[], from: string, to: string): string[] {
  const a = order.indexOf(from)
  const b = order.indexOf(to)
  if (a < 0 || b < 0) return [to]
  return order.slice(Math.min(a, b), Math.max(a, b) + 1)
}
