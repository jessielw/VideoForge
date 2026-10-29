import assert from 'node:assert/strict'
import { test } from 'node:test'
import { extraFlags, parseOptions, unknownHint } from '../src/lib/encoderOptions.ts'

const known = new Map([
  ['level-idc', ''],
  ['no-high-tier', ''],
  ['psy-rd', ''],
  ['aq-mode', ''],
])

test("the extra arguments' flags, without values or short flags", () => {
  assert.deepEqual(extraFlags('--no-sao --zones "0,100,--q=20" -p 5 --psy-rd=2 --no-sao', '--'), [
    'no-sao',
    'zones',
    'psy-rd',
  ])
  assert.deepEqual(extraFlags('-g 240 -b:v 0 -tile-columns 2 -1', '-'), ['g', 'b', 'tile-columns'])
})

test('an unlisted name warns, with the nearest listed one', () => {
  assert.equal(unknownHint('level-idc', known, '--', 'x265'), '')
  assert.equal(
    unknownHint('levle-idc', known, '--', 'x265'),
    "x265's help doesn't list --levle-idc: did you mean --level-idc?",
  )
  assert.equal(unknownHint('frobnicate', known, '--', 'x265'), "x265's help doesn't list --frobnicate")
  assert.equal(unknownHint('anything', null, '--', 'x265'), '') // no list: nothing to check
  assert.equal(unknownHint('anything', new Map(), '--', 'x265'), '')
})

test('a pasted command line becomes one row per option', () => {
  assert.deepEqual(parseOptions('--ref 4 --bframes 8 --no-sao --psy-rd=2 --zones "0,100,q=20"', '--'), {
    pairs: [
      ['ref', '4'],
      ['bframes', '8'],
      ['no-sao', ''],
      ['psy-rd', '2'],
      ['zones', '0,100,q=20'],
    ],
    skipped: [],
  })
  assert.deepEqual(parseOptions('level-idc 5.1', '--'), { pairs: [['level-idc', '5.1']], skipped: [] }) // typed name, no dashes
  assert.deepEqual(parseOptions('5 --aq-mode 3 -p 5 -D 10', '--'), {
    pairs: [['aq-mode', '3']],
    skipped: ['5', '-p 5', '-D 10'],
  })
  assert.deepEqual(parseOptions('-g 240 -arnr-strength -1 -row-mt 1 -b:v 0', '-'), {
    pairs: [
      ['g', '240'],
      ['arnr-strength', '-1'],
      ['row-mt', '1'],
      ['b:v', '0'],
    ],
    skipped: [],
  })
})
