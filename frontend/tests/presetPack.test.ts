import assert from 'node:assert/strict'
import { test } from 'node:test'
import { presetPack } from '../src/lib/presetPack.ts'
import type { ConfigurationBundle, EncoderSettings } from '../src/lib/types.ts'

const encoder: EncoderSettings = {
  encoder: 'x264',
  rate_control: 'crf',
  crf: 18,
  bitrate_kbps: 8000,
  target_mb: null,
  preset: 'slow',
  tune: 'grain',
  depth: 10,
  options: { ref: '4' },
  extra: '',
  source_color: true,
  hdr10plus: false,
  dolby_vision: false,
}

test('sharing allowlists portable fields and removes local identities and accidental metadata', () => {
  const data = {
    template: [],
    video: [],
    encoder: [
      { name: 'local-id', label: 'Film', group: ['1080p', 'SDR'], data: encoder, privateToken: 'DO_NOT_SHARE' },
    ],
    audio: [{ name: 'legacy-audio', data: { action: 'copy' as const, layout: null, bitrate_kbps: null, options: {} } }],
    settings: { notifications: [{ url: 'TOKEN' }] },
    application: { plugins: { secret: 'TOKEN' } },
  }
  const pack = presetPack(data)
  assert.deepEqual(Object.keys(pack).sort(), ['format', 'presets', 'version'])
  assert.deepEqual(pack.presets.encoder[0], { label: 'Film', group: ['1080p', 'SDR'], data: encoder })
  assert.deepEqual(pack.presets.audio[0], { label: 'legacy-audio', group: [], data: data.audio[0].data })
  assert.equal(JSON.stringify(pack).includes('TOKEN'), false)
  pack.presets.encoder[0].data.options.ref = '8'
  pack.presets.encoder[0].group.push('More')
  assert.equal(encoder.options.ref, '4')
  assert.deepEqual(data.encoder[0].group, ['1080p', 'SDR'])
})

test('a selected library subset does not pull in other configuration', () => {
  const libraries: ConfigurationBundle['presets'] = { template: [], video: [], encoder: [], audio: [] }
  const pack = presetPack(libraries)
  assert.deepEqual(pack.presets, libraries)
})
