import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nameParts, oddSubtitleRows, oddSummary, wrongEpisodeCount } from '../src/lib/matchCheck.ts'

const job = (source: string, ...subtitles: string[]) => ({ source, subtitles })

test('flags the jobs whose subtitle count differs from most', () => {
  const jobs = [job('e1', 'a'), job('e2', 'b'), job('e3'), job('e4', 'c', 'd')]
  const odd = oddSubtitleRows(jobs, [])
  assert.deepEqual(
    [...odd],
    [
      ['e3', { count: 0, usual: 1 }],
      ['e4', { count: 2, usual: 1 }],
    ],
  )
  assert.equal(oddSummary(odd), '1 without subtitles · 1 with a different number of subtitles')
})

test('unticked subtitles count as gone', () => {
  const odd = oddSubtitleRows([job('e1', 'a', 'x'), job('e2', 'b', 'y'), job('e3', 'c')], ['x', 'y'])
  assert.equal(odd.size, 0)
})

test('nothing to flag for one job, or a batch with no subtitles', () => {
  assert.equal(oddSubtitleRows([job('e1')], []).size, 0)
  assert.equal(oddSubtitleRows([job('e1'), job('e2')], []).size, 0)
  assert.equal(oddSummary(new Map()), '')
})

test('a tie picks the larger count as usual', () => {
  const odd = oddSubtitleRows([job('e1', 'a'), job('e2')], [])
  assert.deepEqual([...odd.keys()], ['e2'])
})

test('splits a subtitle name where it stops sharing its source name, at a separator', () => {
  assert.deepEqual(nameParts('Show.S01E01.1080p.REMUX.en.forced.srt', 'Show.S01E01.1080p.REMUX.mkv'), {
    shared: 'Show.S01E01.1080p.REMUX.',
    rest: 'en.forced.srt',
  })
  // Shares "Show.S01E01.1" with the source, but the cut goes back to the last dot.
  assert.deepEqual(nameParts('Show.S01E01.1080p.NF.en.srt', 'Show.S01E01.1080i.mkv'), {
    shared: 'Show.S01E01.',
    rest: '1080p.NF.en.srt',
  })
  assert.deepEqual(nameParts('English.srt', 'Movie.mkv'), { shared: '', rest: 'English.srt' })
  assert.deepEqual(nameParts('show.s01e01.EN.srt', 'Show.S01E01.mkv'), { shared: 'show.s01e01.', rest: 'EN.srt' })
})

test('counts ticked subtitles named for another episode', () => {
  const sub = (path: string, match: 'name' | 'other_episode') => ({ path, match })
  const jobs = [{ subtitle_info: [sub('a', 'name'), sub('b', 'other_episode'), sub('c', 'other_episode')] }]
  assert.equal(wrongEpisodeCount(jobs, []), 2)
  assert.equal(wrongEpisodeCount(jobs, ['b']), 1)
})
