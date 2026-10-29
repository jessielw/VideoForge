import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createDraftStore } from '../src/lib/drafts.ts'

test('import selections and overrides survive a new page instance without sharing mutable objects', () => {
  const values = new Map<string, string>()
  const storage = {
    getItem: (k: string) => values.get(k) ?? null,
    setItem: (k: string, v: string) => {
      values.set(k, v)
    },
  }
  const store = createDraftStore(storage)
  const draft = { sources: ['movie.mkv'], encoder: { crf: 17 }, templateName: 'My template' }
  store.write('new-jobs', draft)
  draft.encoder.crf = 25
  assert.deepEqual(createDraftStore(storage).read('new-jobs'), {
    sources: ['movie.mkv'],
    encoder: { crf: 17 },
    templateName: 'My template',
  })
  store.write('new-jobs', { sources: [] })
  assert.deepEqual(createDraftStore(storage).read('new-jobs'), { sources: [] })
})

test('blocked or malformed storage does not prevent in-session draft recovery', () => {
  const blocked = createDraftStore({
    getItem() {
      throw Error('blocked')
    },
    setItem() {
      throw Error('blocked')
    },
  })
  assert.equal(blocked.read('templates'), null)
  blocked.write('templates', { name: 'unsaved' })
  assert.deepEqual(blocked.read('templates'), { name: 'unsaved' })
  assert.equal(createDraftStore({ getItem: () => 'broken', setItem() {} }).read('new-jobs'), null)
  assert.equal(createDraftStore({ getItem: () => '{"version":2,"value":{}}', setItem() {} }).read('new-jobs'), null)
})
