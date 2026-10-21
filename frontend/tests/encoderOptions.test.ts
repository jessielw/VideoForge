import assert from 'node:assert/strict'
import { test } from 'node:test'
import { extraFlags, unknownHint } from '../src/lib/encoderOptions.ts'

const known = new Map([['level-idc', ''], ['no-high-tier', ''], ['psy-rd', ''], ['aq-mode', '']])

test('the extra arguments\' flags, without values or short flags', () => {
  assert.deepEqual(extraFlags('--no-sao --zones "0,100,--q=20" -p 5 --psy-rd=2 --no-sao', '--'), ['no-sao', 'zones', 'psy-rd'])
  assert.deepEqual(extraFlags('-g 240 -b:v 0 -tile-columns 2 -1', '-'), ['g', 'b', 'tile-columns'])
})

test('an unlisted name warns, with the nearest listed one', () => {
  assert.equal(unknownHint('level-idc', known, '--', 'x265'), '')
  assert.equal(unknownHint('levle-idc', known, '--', 'x265'), "x265's help doesn't list --levle-idc: did you mean --level-idc?")
  assert.equal(unknownHint('frobnicate', known, '--', 'x265'), "x265's help doesn't list --frobnicate")
  assert.equal(unknownHint('anything', null, '--', 'x265'), '') // no list: nothing to check
  assert.equal(unknownHint('anything', new Map(), '--', 'x265'), '')
})
