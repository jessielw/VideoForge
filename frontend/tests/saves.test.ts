import { test } from 'node:test'
import assert from 'node:assert/strict'
import { SaveQueue } from '../src/lib/saves.ts'

test('a save scheduled by a prior reply starts without a flush', async () => {
  const queue = new SaveQueue()
  const first = queue.add(async () => 1)
  assert.equal(await first.then(() => queue.add(async () => 2)), 2)
})

test('flush captures a debounce and waits for its write before start', async () => {
  const queue = new SaveQueue()
  const events: string[] = []
  let release!: () => void
  let pending = true
  queue.register(() => {
    if (!pending) return
    pending = false
    void queue.add(async () => {
      await new Promise<void>(resolve => { release = resolve })
      events.push('saved')
    })
  })
  const start = queue.flush().then(() => events.push('started'))
  assert.deepEqual(events, [])
  release()
  await start
  assert.deepEqual(events, ['saved', 'started'])
})

test('failure blocks start and subsequent edits; retry preserves write order', async () => {
  const queue = new SaveQueue()
  const writes: number[] = []
  let fail = true
  const first = queue.add(async () => { if (fail) throw new Error('offline'); writes.push(1) })
  const second = queue.add(async () => { writes.push(2) })
  await assert.rejects(queue.flush(), /offline/)
  assert.deepEqual(writes, [])
  fail = false
  await queue.retry()
  await Promise.all([first, second])
  assert.deepEqual(writes, [1, 2])
})

test('unregister flushes edits and discard releases failed writes', async () => {
  const queue = new SaveQueue()
  let result!: Promise<unknown>
  const unregister = queue.register(() => { result = queue.add(async () => { throw new Error('deleted job') }) })
  unregister()
  const rejected = assert.rejects(result, /discarded/)
  await assert.rejects(queue.flush(), /deleted job/)
  queue.discard()
  await rejected
  await queue.flush()
})
