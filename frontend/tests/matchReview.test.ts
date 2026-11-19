import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MATCH_NOTE } from '../src/lib/matchCheck.ts'
import { filterEntries, kindOf, matchEntries, needsLook, suggestedMatches, UNSURE } from '../src/lib/matchReview.ts'
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
