import assert from 'node:assert/strict'
import { test } from 'node:test'
import { filterEntries, sortEntries } from '../src/lib/fileList.ts'

const names = (xs: { name: string }[]) => xs.map((x) => x.name)
const entries = [{ name: 'Show.S01E01.mkv' }, { name: 'Show.S02E01.mkv' }, { name: 'Extras' }]

test('the filter keeps names with every word in them, ignoring case and spacing', () => {
  assert.deepEqual(names(filterEntries(entries, 's01')), ['Show.S01E01.mkv'])
  assert.deepEqual(names(filterEntries(entries, '  E01   MKV ')), ['Show.S01E01.mkv', 'Show.S02E01.mkv'])
  assert.deepEqual(names(filterEntries(entries, 's01 extras')), [])
  assert.equal(filterEntries(entries, '   '), entries)
})

test('sorting goes by number-aware name, date or size, with ties and folders by name', () => {
  const files = [
    { name: 'E10.mkv', size: 5, mtime: 3 },
    { name: 'e2.mkv', size: 9, mtime: 1 },
    { name: 'E1.mkv', size: 5, mtime: 2 },
  ]
  assert.deepEqual(names(sortEntries(files, { key: 'name', desc: false })), ['E1.mkv', 'e2.mkv', 'E10.mkv'])
  assert.deepEqual(names(sortEntries(files, { key: 'name', desc: true })), ['E10.mkv', 'e2.mkv', 'E1.mkv'])
  assert.deepEqual(names(sortEntries(files, { key: 'mtime', desc: true })), ['E10.mkv', 'E1.mkv', 'e2.mkv'])
  assert.deepEqual(names(sortEntries(files, { key: 'size', desc: false })), ['E1.mkv', 'E10.mkv', 'e2.mkv'])
  assert.deepEqual(names(sortEntries(files, { key: 'size', desc: true })), ['e2.mkv', 'E1.mkv', 'E10.mkv'])
  const folders = [{ name: 'B' }, { name: 'a' }]
  assert.deepEqual(names(sortEntries(folders, { key: 'size', desc: true })), ['a', 'B'])
  assert.equal(files[0].name, 'E10.mkv') // a copy: the listing keeps its order
})
