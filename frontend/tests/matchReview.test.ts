import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MATCH_NOTE } from '../src/lib/matchCheck.ts'
import {
  duplicateSubtitles,
  filterEntries,
  kindOf,
  matchEntries,
  needsLook,
  rangeOf,
  suggestedMatches,
  timingKey,
  timingNote,
  timingPairs,
  UNSURE,
} from '../src/lib/matchReview.ts'
import type { MatchResult, MatchedJob } from '../src/lib/types.ts'

const job = (source: string, files: Partial<MatchedJob> & { matches: MatchedJob['matches'] }): MatchedJob => ({
  existing_id: null,
  existing_status: null,
  source,
  encode: null,
  subtitles: [],
  subtitle_info: [],
  chapters: null,
  encode_state: 'unknown',
  ...files,
})

const result: MatchResult = {
  jobs: [
    job('D:/m/Show.S01E01.mkv', {
      encode: 'D:/m/Show.S01E01_job.h264',
      chapters: 'D:/m/Show.S01E01.mkv_temp/a_qpf/qpf_chapters.txt',
      subtitles: ['D:/m/Show.S01E01.en.srt', 'D:/m/Show - 01.ass'],
      matches: {
        'D:/m/Show.S01E01_job.h264': 'name',
        'D:/m/Show.S01E01.mkv_temp/a_qpf/qpf_chapters.txt': 'staxrip',
        'D:/m/Show.S01E01.en.srt': 'name',
        'D:/m/Show - 01.ass': 'similar',
      },
    }),
    job('D:/m/Show.S01E02.mkv', { subtitles: ['D:/m/English.srt'], matches: { 'D:/m/English.srt': 'manual' } }),
  ],
  unmatched: ['D:/m/t2_c3.srt', 'D:/m/stray.xml', 'D:/m/Old.srt'],
  held: ['D:/m/Old.srt'],
  suggestions: {
    'D:/m/t2_c3.srt': [{ source: 'D:/m/Show.S01E02.mkv', why: 'pattern' }],
    'D:/m/stray.xml': [{ source: 'D:/m/Show.S01E01.mkv', why: 'similar' }],
    'D:/m/Old.srt': [{ source: 'D:/m/Show.S01E01.mkv', why: 'similar' }],
  },
}

test('lists unmatched files first, then each job’s files, without StaxRip temp chapters', () => {
  const entries = matchEntries(result)
  assert.deepEqual(
    entries.map((e) => [e.path.slice(5), e.kind, e.source?.slice(5) ?? null, e.reason]),
    [
      ['t2_c3.srt', 'subtitles', null, null],
      ['stray.xml', 'chapters', null, null],
      ['Old.srt', 'subtitles', null, 'manual'],
      ['Show.S01E01_job.h264', 'video', 'Show.S01E01.mkv', 'name'],
      ['Show.S01E01.en.srt', 'subtitles', 'Show.S01E01.mkv', 'name'],
      ['Show - 01.ass', 'subtitles', 'Show.S01E01.mkv', 'similar'],
      ['English.srt', 'subtitles', 'Show.S01E02.mkv', 'manual'],
    ],
  )
})

test('needs a look: unmatched files and guesses, not sure matches or ones set to no source', () => {
  const look = matchEntries(result).filter(needsLook)
  assert.deepEqual(
    look.map((e) => e.path.slice(5)),
    ['t2_c3.srt', 'stray.xml', 'Show - 01.ass'],
  )
})

test('filters by every word, in the file’s or its source’s name', () => {
  const entries = matchEntries(result)
  assert.deepEqual(
    filterEntries(entries, 'e02 SRT').map((e) => e.path.slice(5)),
    ['English.srt'],
  )
  assert.equal(filterEntries(entries, '  ').length, entries.length)
})

test('offers the best suggestion per unmatched file, or only those learned from the user’s matches', () => {
  const entries = matchEntries(result)
  assert.deepEqual(suggestedMatches(entries), {
    'D:/m/t2_c3.srt': 'D:/m/Show.S01E02.mkv',
    'D:/m/stray.xml': 'D:/m/Show.S01E01.mkv',
  })
  assert.deepEqual(suggestedMatches(entries, 'pattern'), { 'D:/m/t2_c3.srt': 'D:/m/Show.S01E02.mkv' })
})

test('the matches to check are the ones Matched files marks as not sure', () => {
  const unsure = Object.entries(MATCH_NOTE)
    .filter(([, n]) => !n.sure)
    .map(([k]) => k)
  assert.deepEqual([...UNSURE].sort(), unsure.sort())
})

test('reads a file’s kind from its extension', () => {
  assert.deepEqual(['a.SUP', 'b.idx', 'c.txt', 'd.mkv', 'e.hevc'].map(kindOf), [
    'subtitles',
    'subtitles',
    'chapters',
    'video',
    'video',
  ])
})

const label = (path: string, language: string, format: string, tags: string[] = []) => ({
  path,
  language,
  language_name: language,
  format,
  tags,
  track: null,
  match: 'name' as const,
})

test('subtitles alike: same language, format and tags, synced or not, ticked ones only', () => {
  const info = [
    label('a.en.srt', 'en', 'srt'),
    label('a.en.synced.srt', 'en', 'srt', ['synced']),
    label('a.en.sup', 'en', 'sup'),
    label('a.en.forced.srt', 'en', 'srt', ['forced']),
  ]
  assert.deepEqual(duplicateSubtitles(info), [['a.en.srt', 'a.en.synced.srt']])
  assert.deepEqual(duplicateSubtitles(info, ['a.en.srt']), [])
})

test('a left-over file and subtitles alike need a look, and say why', () => {
  const r: MatchResult = {
    jobs: [
      job('D:/m/E01.mkv', {
        chapters: 'D:/m/E01.chapters.txt',
        subtitles: ['D:/m/E01.en.srt', 'D:/m/E01.en.synced.srt'],
        subtitle_info: [
          label('D:/m/E01.en.srt', 'en', 'srt'),
          label('D:/m/E01.en.synced.srt', 'en', 'srt', ['synced']),
        ],
        matches: { 'D:/m/E01.chapters.txt': 'name', 'D:/m/E01.en.srt': 'name', 'D:/m/E01.en.synced.srt': 'name' },
        details: {},
      }),
    ],
    unmatched: ['D:/m/chapters_E01.xml'],
    held: [],
    spare: { 'D:/m/chapters_E01.xml': 'D:/m/E01.mkv' },
    suggestions: {},
  }
  const entries = matchEntries(r)
  assert.deepEqual(
    entries.filter(needsLook).map((e) => [e.path.slice(5), e.conflict]),
    [
      ['chapters_E01.xml', 'Left over: E01.mkv already has chapters, E01.chapters.txt'],
      ['E01.en.srt', 'Same language and type as E01.en.synced.srt'],
      ['E01.en.synced.srt', 'Same language and type as E01.en.srt'],
    ],
  )
})

test('a Shift+click range runs either way between two shown paths', () => {
  assert.deepEqual(rangeOf(['a', 'b', 'c', 'd'], 'c', 'a'), ['a', 'b', 'c'])
  assert.deepEqual(rangeOf(['a', 'b'], 'gone', 'b'), ['b'])
})

test('timing: text subtitles only, not synced or matched by hand, and a flag only for one that does not fit', () => {
  const r: MatchResult = {
    jobs: [
      job('D:/m/E01.mkv', {
        subtitles: ['D:/m/E01.en.srt', 'D:/m/E01.en.synced.srt', 'D:/m/E01.en.sup', 'D:/m/E01.ja.ass', 'D:/m/x.srt'],
        subtitle_info: [
          label('D:/m/E01.en.srt', 'en', 'srt'),
          label('D:/m/E01.en.synced.srt', 'en', 'srt', ['synced']),
          label('D:/m/E01.en.sup', 'en', 'sup'),
          label('D:/m/E01.ja.ass', 'ja', 'ass'),
          label('D:/m/x.srt', 'und', 'srt'),
        ],
        matches: {
          'D:/m/E01.en.srt': 'name',
          'D:/m/E01.en.synced.srt': 'name',
          'D:/m/E01.en.sup': 'name',
          'D:/m/E01.ja.ass': 'name',
          'D:/m/x.srt': 'manual',
        },
      }),
    ],
    unmatched: [],
    held: [],
    suggestions: {},
  }
  assert.deepEqual(timingPairs(r), { 'D:/m/E01.en.srt': 'D:/m/E01.mkv', 'D:/m/E01.ja.ass': 'D:/m/E01.mkv' })

  const late = { verdict: 'late' as const, last_ms: 2_640_000, source_ms: 1_440_000 }
  const timing = {
    [timingKey('D:/m/E01.en.srt', 'D:/m/E01.mkv')]: late,
    [timingKey('D:/m/E01.ja.ass', 'D:/m/E01.mkv')]: { verdict: null, last_ms: 1_400_000, source_ms: 1_440_000 },
    [timingKey('D:/m/x.srt', 'D:/m/E01.mkv')]: late, // matched by hand: never flagged
  }
  const flagged = matchEntries(r, timing).filter((e) => e.timing)
  assert.ok(flagged.every(needsLook))
  assert.deepEqual(
    flagged.map((e) => [e.path.slice(5), e.timing]),
    [['E01.en.srt', 'Its last line is at 44:00, 20:00 after the source ends (24:00): another episode or cut?']],
  )
  assert.equal(
    timingNote({ verdict: 'early', last_ms: 300_000, source_ms: 7_260_000 }),
    'Its last line is at 5:00, 1:56:00 before the source ends (2:01:00): another episode or cut?',
  )
  assert.equal(matchEntries(r).find((e) => e.path === 'D:/m/E01.en.srt')?.timing, '') // not checked yet
})
