import assert from 'node:assert/strict'
import { test } from 'node:test'
import { LatestRequest } from '../src/lib/latestRequest.ts'

test('reverse-order responses and stale failures cannot replace the latest preview', async () => {
  const latest = new LatestRequest()
  let resolve!: (value: string) => void
  let reject!: (error: Error) => void
  const a = latest.run(() => new Promise<string>(r => { resolve = r }))
  const failed = latest.run(() => new Promise<string>((_, r) => { reject = r }))
  assert.deepEqual(await latest.run(async () => 'B'), { value: 'B' })
  resolve('A'); reject(new Error('old failure'))
  assert.equal(await a, null)
  assert.equal(await failed, null)
  const unmounted = latest.run(async () => 'old page')
  latest.invalidate()
  assert.equal(await unmounted, null)
})
