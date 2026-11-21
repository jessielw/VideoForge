import assert from 'node:assert/strict'
import { test } from 'node:test'
import { forget, savesInTurn, togglePin } from '../src/lib/outputFolders.ts'

const a = { path: 'D:/Out/a', pinned: true }
const b = { path: 'D:/Out/b', pinned: false }

test('pinning a folder keeps the default', () => {
  assert.deepEqual(togglePin([a, b], b, a.path), {
    folders: [a, { ...b, pinned: true }],
    fallback: a.path,
  })
})

test('unpinning the default clears it', () => {
  assert.deepEqual(togglePin([a, b], a, a.path), { folders: [{ ...a, pinned: false }, b], fallback: '' })
})

test('unpinning another folder keeps the default', () => {
  const c = { path: 'D:/Out/c', pinned: true }
  assert.deepEqual(togglePin([a, c], c, a.path), { folders: [a, { ...c, pinned: false }], fallback: a.path })
})

test('forgetting the default clears it', () => {
  assert.deepEqual(forget([a, b], a, a.path), { folders: [b], fallback: '' })
})

test('forgetting another folder keeps the default', () => {
  assert.deepEqual(forget([a, b], b, a.path), { folders: [a], fallback: a.path })
})

const tick = () => new Promise((resolve) => setTimeout(resolve))

test('saves go one at a time, and only the last one hands back the reply', async () => {
  const sent: string[] = []
  const replies: (() => void)[] = []
  const save = savesInTurn(async (s) => {
    sent.push(s.fallback)
    await new Promise<void>((resolve) => replies.push(resolve))
    return s
  })
  const first = save({ folders: [a], fallback: 'one' })
  const second = save({ folders: [a, b], fallback: 'two' })
  await tick()
  assert.deepEqual(sent, ['one']) // the second waits for the first's reply
  replies[0]()
  assert.equal(await first, null) // a newer save is waiting: its reply is the one to show
  await tick()
  assert.deepEqual(sent, ['one', 'two'])
  replies[1]()
  assert.deepEqual(await second, { folders: [a, b], fallback: 'two' })
})

test('a failed save rejects, and the next save still goes', async () => {
  let fail = true
  const save = savesInTurn(async (s) => {
    if (fail) throw new Error('offline')
    return s
  })
  await assert.rejects(save({ folders: [a], fallback: '' }), /offline/)
  fail = false
  assert.deepEqual(await save({ folders: [b], fallback: '' }), { folders: [b], fallback: '' })
})
