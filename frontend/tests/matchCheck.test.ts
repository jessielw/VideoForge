import assert from 'node:assert/strict'
import { test } from 'node:test'
import { oddSubtitleRows, oddSummary } from '../src/lib/matchCheck.ts'

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
