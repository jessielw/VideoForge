import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nextMark, prevMark, sampleMarks, scriptFrame, toggleMark } from '../src/lib/marks.ts'

test('a mark goes in sorted, and a second toggle takes it out', () => {
  assert.deepEqual(toggleMark([10, 500], 42), [10, 42, 500])
  assert.deepEqual(toggleMark([10, 42, 500], 42), [10, 500])
  assert.deepEqual(toggleMark([], 0), [0])
})

test('the next and previous marks skip the frame itself, and stop at either end', () => {
  const marks = [10, 42, 500]
  assert.equal(nextMark(marks, 42), 500)
  assert.equal(nextMark(marks, 0), 10)
  assert.equal(nextMark(marks, 500), null)
  assert.equal(prevMark(marks, 42), 10)
  assert.equal(prevMark(marks, 501), 500)
  assert.equal(prevMark(marks, 10), null)
})

// 48-frame blocks, one every 960 frames of the script: sample frame 50 is the script's 962.
const BLOCKS = { length: 48, cycle: 960 }

test("a test encode's frame is the script's: its block's start plus how far in", () => {
  assert.equal(scriptFrame(0, BLOCKS), 0)
  assert.equal(scriptFrame(47, BLOCKS), 47)
  assert.equal(scriptFrame(50, BLOCKS), 962)
})

test("the script's marks inside the test encode's blocks, in its frames", () => {
  // 30 is in the first block, 500 between blocks, 962 in the second, 2000 past the sample's end.
  assert.deepEqual(sampleMarks([30, 500, 962, 2000], BLOCKS, 96), [30, 50])
  for (const n of sampleMarks([30, 962], BLOCKS, 96)) assert.ok([30, 962].includes(scriptFrame(n, BLOCKS)))
})
