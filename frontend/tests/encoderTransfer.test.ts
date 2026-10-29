import assert from 'node:assert/strict'
import { test } from 'node:test'
import { encoderBundle } from '../src/lib/encoderTransfer.ts'
import type { EncoderSettings } from '../src/lib/types.ts'

const data: EncoderSettings = {
  encoder: 'x264',
  rate_control: 'crf',
  crf: 18,
  bitrate_kbps: 8000,
  target_mb: null,
  preset: 'slow',
  tune: 'grain',
  depth: 10,
  options: { ref: '4' },
  extra: '--no-dct-decimate',
  source_color: true,
  hdr10plus: false,
  dolby_vision: false,
}

test('encoder exports keep labels, nested folders, and all settings without local identities', () => {
  const bundle = encoderBundle([{ name: 'local-id', label: 'Film', group: ['1080p', 'SDR'], data }])
  assert.deepEqual(bundle, {
    format: 'videoforge.encoders',
    version: 1,
    encoders: [{ label: 'Film', group: ['1080p', 'SDR'], data }],
  })
  bundle.encoders[0].data.options.ref = '8'
  bundle.encoders[0].group.push('Grain')
  assert.equal(data.options.ref, '4')
})

test('legacy presets use their display name at the encoder root', () => {
  assert.deepEqual(encoderBundle([{ name: 'Legacy', data }]).encoders[0], { label: 'Legacy', group: [], data })
})
