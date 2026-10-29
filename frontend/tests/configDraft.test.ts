import { test } from 'node:test'
import assert from 'node:assert/strict'
import { configDraft } from '../src/lib/configDraft.ts'
import { SaveQueue } from '../src/lib/saves.ts'
import type { ConfigState } from '../src/lib/types.ts'

test('rapid whole-list edits build on the optimistic list and save in order', async () => {
  let config = { notifications: [{ name: 'A', enabled: true, events: ['job_done'], url: 'test://' }] } as ConfigState
  const queue = new SaveQueue()
  const sent: unknown[] = []
  let release!: () => void
  const changes = { notifications: config.notifications.map((n) => ({ ...n, name: 'B' })) }
  config = configDraft(config, changes)
  const first = queue.add(async () => {
    await new Promise<void>((r) => {
      release = r
    })
    sent.push(changes)
  })
  const secondChanges = { notifications: config.notifications.map((n) => ({ ...n, enabled: false })) }
  config = configDraft(config, secondChanges)
  const second = queue.add(async () => {
    sent.push(secondChanges)
  })
  assert.equal(config.notifications[0].name, 'B')
  release()
  await Promise.all([first, second])
  assert.deepEqual(sent[1], { notifications: [{ name: 'B', enabled: false, events: ['job_done'], url: 'test://' }] })
})
