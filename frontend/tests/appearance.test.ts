import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  DEFAULT_PALETTE,
  DEFAULT_RADIUS,
  PALETTES,
  normalizePalette,
  normalizeRadius,
  radiusRem,
} from '../src/lib/appearance.ts'

test('a stored palette or radius that is unknown falls back to the default', () => {
  assert.equal(normalizePalette('ocean'), 'ocean')
  assert.equal(normalizePalette('nope'), DEFAULT_PALETTE)
  assert.equal(normalizePalette(null), DEFAULT_PALETTE)
  assert.equal(normalizeRadius('round'), 'round')
  assert.equal(normalizeRadius(42), DEFAULT_RADIUS)
})

test('the default radius is the stylesheet default, and the default palette is listed first', () => {
  assert.equal(radiusRem(DEFAULT_RADIUS), 0.5)
  assert.equal(PALETTES[0].id, DEFAULT_PALETTE)
})

test('palette ids are unique', () => {
  assert.equal(new Set(PALETTES.map((p) => p.id)).size, PALETTES.length)
})

test('accent must be a #rrggbb colour; the text on it flips with brightness', async () => {
  const { normalizeAccent, accentForeground, normalizeDensity, densityScale } = await import('../src/lib/appearance.ts')
  assert.equal(normalizeAccent('#AABBCC'), '#aabbcc')
  assert.equal(normalizeAccent('red'), null)
  assert.equal(normalizeAccent('#abc'), null)
  assert.equal(accentForeground('#ffff00'), '#1c1917')
  assert.equal(accentForeground('#1e3a8a'), '#ffffff')
  assert.equal(normalizeDensity('weird'), 'default')
  assert.equal(densityScale('compact'), 0.9)
})
