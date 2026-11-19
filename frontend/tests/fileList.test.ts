import assert from 'node:assert/strict'
import { test } from 'node:test'
import { filterEntries } from '../src/lib/fileList.ts'

const names = (xs: { name: string }[]) => xs.map((x) => x.name)
const entries = [{ name: 'Show.S01E01.mkv' }, { name: 'Show.S02E01.mkv' }, { name: 'Extras' }]

test('the filter keeps names with every word in them, ignoring case and spacing', () => {
  assert.deepEqual(names(filterEntries(entries, 's01')), ['Show.S01E01.mkv'])
  assert.deepEqual(names(filterEntries(entries, '  E01   MKV ')), ['Show.S01E01.mkv', 'Show.S02E01.mkv'])
  assert.deepEqual(names(filterEntries(entries, 's01 extras')), [])
  assert.equal(filterEntries(entries, '   '), entries)
})
