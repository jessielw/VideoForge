import assert from 'node:assert/strict'
import { test } from 'node:test'
import { frameFilename } from '../src/lib/format.ts'

test('a saved frame is named after the source, its number padded to the clip length', () => {
  assert.equal(frameFilename('D:\\remux\\Show S01E01.mkv', 42, 34000, 'output'), 'Show S01E01 - 00042.png')
  assert.equal(frameFilename('/media/movie.m2ts', 7, 10, 'output'), 'movie - 7.png')
  assert.equal(frameFilename('/media/movie.m2ts', 7, 11, 'output'), 'movie - 07.png')
})

test('the crop view is marked, as its frame has the margins on', () => {
  assert.equal(frameFilename('movie.mkv', 0, 1, 'crop'), 'movie - 0 (crop view).png')
})

test('characters a file name cannot hold are replaced; an empty name falls back', () => {
  assert.equal(frameFilename('/x/a:b?.mkv', 1, 2, 'output'), 'a_b_ - 1.png')
  assert.equal(frameFilename('', 3, 100, 'output'), 'frame - 03.png')
})
