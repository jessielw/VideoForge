import assert from 'node:assert/strict'
import { test } from 'node:test'
import { matchingJobs, queuePage, queueRange, QUEUE_PAGE_SIZE } from '../src/lib/queueView.ts'
import type { JobSummary } from '../src/lib/types.ts'

const jobs = [
  { id: 'a', name: 'Episode 01', source: 'D:\\Show\\Season2\\01.mkv', status: 'ready' },
  { id: 'b', name: 'Episode 02', source: 'D:\\Show\\Season1\\02.mkv', status: 'done' },
  { id: 'c', name: 'Episode 03', source: 'D:\\Show\\Season2\\03.mkv', status: 'failed' },
] as JobSummary[]

test('queue search combines words, source paths, and status without changing run order', () => {
  assert.deepEqual(matchingJobs(jobs, '  SEASON2 episode ').map(j => j.id), ['a', 'c'])
  assert.deepEqual(matchingJobs(jobs, 'show', 'failed').map(j => j.id), ['c'])
  assert.deepEqual(matchingJobs(jobs, '', 'done').map(j => j.id), ['b'])
  assert.equal(matchingJobs(jobs, 'missing').length, 0)
  assert.deepEqual(matchingJobs(jobs, '  '), jobs)
})

test('selection ranges follow matching order and recover when a live status removes the anchor', () => {
  assert.deepEqual(queueRange(['a', 'c'], 'c', 'a'), ['a', 'c'])
  assert.deepEqual(queueRange(['a', 'c'], 'b', 'c'), ['c'])
  assert.deepEqual(queueRange(['a', 'c'], 'a', 'gone'), [])
})

test('queue pages clamp after removal and handle empty and exact page boundaries', () => {
  assert.equal(queuePage(0, 9), 0)
  assert.equal(queuePage(QUEUE_PAGE_SIZE, 1), 0)
  assert.equal(queuePage(QUEUE_PAGE_SIZE + 1, 9), 1)
  assert.equal(queuePage(10_000, 99), 99)
})
