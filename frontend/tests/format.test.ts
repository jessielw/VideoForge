import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sizeLabel } from '../src/lib/format.ts'

test('a plain size reads with a times sign; a size class stays as it is', () => {
  assert.equal(sizeLabel('1920x1040'), '1920×1040')
  assert.equal(sizeLabel('3840x2076'), '3840×2076')
  assert.equal(sizeLabel('1080p'), '1080p')
  assert.equal(sizeLabel(''), '')
})
