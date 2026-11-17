import assert from 'node:assert/strict'
import { test } from 'node:test'
import { forget, togglePin } from '../src/lib/outputFolders.ts'

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
