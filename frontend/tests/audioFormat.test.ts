import assert from 'node:assert/strict'
import { test } from 'node:test'
import { audioFormat, withImmersive } from '../src/lib/format.ts'

const label = (t: { commercial_name?: string; format_name: string; codec: string; atmos?: boolean; dtsx?: boolean }) =>
  withImmersive(audioFormat(t), t)

test('Atmos is not repeated when the commercial name already says it', () => {
  const t = { commercial_name: 'Dolby TrueHD with Dolby Atmos', format_name: 'MLP FBA', codec: 'truehd', atmos: true }
  assert.equal(label(t), 'Dolby TrueHD with Dolby Atmos')
})

test('Atmos is added when the name does not carry it', () => {
  assert.equal(label({ format_name: 'MLP FBA', codec: 'truehd', atmos: true }), 'MLP FBA Atmos')
})

test('DTS:X is not repeated, and is added when missing', () => {
  const base = { format_name: 'DTS', codec: 'dts', dtsx: true }
  assert.equal(label({ ...base, commercial_name: 'DTS-HD Master Audio + DTS:X' }), 'DTS-HD Master Audio + DTS:X')
  assert.equal(label({ ...base, commercial_name: 'DTS-HD Master Audio' }), 'DTS-HD MA DTS:X')
})

test('plain tracks are left alone', () => {
  assert.equal(label({ commercial_name: 'Dolby Digital', format_name: 'AC-3', codec: 'ac3' }), 'DD')
})
