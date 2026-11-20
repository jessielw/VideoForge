import assert from 'node:assert/strict'
import { test } from 'node:test'
import { issueCounts, sizeLabel } from '../src/lib/format.ts'

test('a plain size reads with a times sign; a size class stays as it is', () => {
  assert.equal(sizeLabel('1920x1040'), '1920×1040')
  assert.equal(sizeLabel('3840x2076'), '3840×2076')
  assert.equal(sizeLabel('1080p'), '1080p')
  assert.equal(sizeLabel(''), '')
})

test("a job's issues read as counts of errors and warnings, leaving out a kind with none", () => {
  assert.deepEqual(issueCounts({ block: 1, warn: 2 }), ['1 error', '2 warnings'])
  assert.deepEqual(issueCounts({ block: 3, warn: 1 }), ['3 errors', '1 warning'])
  assert.deepEqual(issueCounts({ block: 0, warn: 4 }), ['4 warnings'])
  assert.deepEqual(issueCounts({ block: 0, warn: 0 }), [])
})
