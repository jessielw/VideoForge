import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseSeek, timecode } from '../src/lib/format.ts'

const FILM = 24000 / 1001

test('a number is a frame', () => {
  assert.equal(parseSeek('1234', FILM), 1234)
  assert.equal(parseSeek(' 0 ', FILM), 0)
})

test('a time goes to the frame it rounds to', () => {
  assert.equal(parseSeek('1:00', 24), 1440)
  assert.equal(parseSeek('1:02:03', 25), (3600 + 120 + 3) * 25)
  assert.equal(parseSeek('0:01.5', 24), 36)
  assert.equal(parseSeek('83.5s', 24), 2004)
  assert.equal(parseSeek('2 S', 25), 50)
  assert.equal(parseSeek('0:01,5', 24), 36) // a decimal comma
})

test('the time shown for a frame comes back as that frame', () => {
  for (const n of [0, 1, 2, 3, 1000, 123_456, 171_000]) {
    assert.equal(parseSeek(timecode(n / FILM), FILM), n)
  }
})

test('anything else is no position', () => {
  for (const t of ['', 'abc', '1:2:3:4', '1:75', '-5', '1.5', 's', '1::2']) assert.equal(parseSeek(t, 24), null, t)
})

test('a time is shown as h:mm:ss.mmm', () => {
  assert.equal(timecode(0), '0:00:00.000')
  assert.equal(timecode(83.5), '0:01:23.500')
  assert.equal(timecode(3723.25), '1:02:03.250')
  assert.equal(timecode(1 / FILM), '0:00:00.042')
})
