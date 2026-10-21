import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mergeSteps } from '../src/lib/logSnapshot.ts'
import type { StepRun } from '../src/lib/types.ts'

test('a snapshot hydrates missing steps while preserving events received after its boundary', () => {
  const old = [{ id: 'video', status: 'running' }, { id: 'audio', status: 'done' }] as StepRun[]
  const live = [{ id: 'video', status: 'done' }] as StepRun[]
  assert.deepEqual(mergeSteps(old, live, { video: 12 }, 10).map(s => s.status), ['done', 'done'])
  assert.deepEqual(mergeSteps(old, live, { video: 9 }, 10), old)
})
