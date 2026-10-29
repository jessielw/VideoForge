import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  applyAudioPreset,
  audioPresetDefaults,
  audioPresetProblem,
  audioPresetSettings,
} from '../src/lib/audioPresets.ts'
import type { AudioEncodeInfo, AudioPresetSettings, AudioTrack, TrackOverride } from '../src/lib/types.ts'

const ddp: AudioEncodeInfo = {
  id: 'ddp',
  label: 'DDP (DEE)',
  codec: 'eac3',
  layouts: ['1.0', '2.0', '5.1', '7.1'],
  bitrates: { '1': 192, '2': 256, '6': 640, '8': 1024 },
  bitrate_choices: [],
  bitrate_range: null,
  per_channel_max: null,
  vbr_default: false,
  default_max: null,
  missing: [],
  options: [],
}
const opus: AudioEncodeInfo = { ...ddp, id: 'opus', label: 'Opus', bitrate_range: [6, 2048], per_channel_max: 256 }
const ac3: AudioEncodeInfo = {
  ...ddp,
  id: 'ac3',
  label: 'AC-3',
  layouts: ['1.0', '2.0', '5.0', '5.1'],
  bitrate_choices: [192, 224, 448, 640],
}
const atmos: AudioEncodeInfo = { ...ddp, id: 'atmos', label: 'Atmos', layouts: ['5.1'] }
const encodes = [ddp, opus, ac3, atmos]
const source = (layout: string, codec = 'flac', atmos = false) => ({ layout, codec, atmos }) as AudioTrack
const preset: AudioPresetSettings = { action: 'ddp', layout: '5.1', bitrate_kbps: 640, options: { dialnorm: '-27' } }

test('saving audio settings includes custom titles, excludes other metadata and takes an independent options copy', () => {
  const settings = audioPresetSettings({
    ...preset,
    title: 'Original',
    language: 'ja',
    flags: { default: true },
    exclude: true,
  })
  assert.deepEqual(Object.keys(settings).sort(), ['action', 'bitrate_kbps', 'layout', 'options', 'title'])
  assert.equal(settings.title, 'Original')
  settings.options.dialnorm = '-25'
  assert.equal(preset.options.dialnorm, '-27')
})

test('applying a preset preserves track metadata and replaces only encoding fields', () => {
  const track: TrackOverride = {
    ...preset,
    title: 'Commentary',
    language: 'en',
    flags: { commentary: true },
    exclude: false,
  }
  const next = applyAudioPreset(track, { ...preset, action: 'ac3', options: { extra: '-cutoff 18000' } })
  assert.deepEqual(next, { ...track, action: 'ac3', options: { extra: '-cutoff 18000' } })
  next.options.extra = '-cutoff 16000'
  assert.deepEqual(track.options, { dialnorm: '-27' })
  assert.deepEqual(preset.options, { dialnorm: '-27' })
  const copied = applyAudioPreset(track, { ...preset, action: 'copy' })
  assert.deepEqual(copied, { ...track, action: 'copy', layout: null, bitrate_kbps: null, options: {} })
})

test('a surround preset cannot upmix stereo; DDP retains its existing 5.0 exception', () => {
  assert.match(audioPresetProblem(preset, encodes, source('2.0')), /more channels/)
  assert.equal(audioPresetProblem(preset, encodes, source('5.0')), '')
  assert.match(audioPresetProblem({ ...preset, action: 'ac3' }, encodes, source('5.0')), /more channels/)
  assert.equal(audioPresetProblem(preset, encodes, source('7.1')), '')
})

test('Atmos requires TrueHD Atmos when applying directly to a source', () => {
  const setting = { ...preset, action: 'atmos' } as AudioPresetSettings
  assert.match(audioPresetProblem(setting, encodes, source('7.1', 'truehd')), /TrueHD Atmos/)
  assert.match(audioPresetProblem(setting, encodes, source('7.1', 'eac3', true)), /TrueHD Atmos/)
  assert.equal(audioPresetProblem(setting, encodes, source('7.1', 'truehd', true)), '')
  assert.equal(audioPresetProblem(setting, encodes), '') // templates fit it to each source later
})

test('DDP Blu-ray requires 7.1 even for auto channels and the 5.0 upmix exception', () => {
  const setting: AudioPresetSettings = { ...preset, layout: null, bitrate_kbps: 1536, options: { ddp_mode: 'bluray' } }
  assert.equal(audioPresetProblem(setting, encodes, source('7.1')), '')
  assert.equal(audioPresetProblem(setting, encodes), '')
  for (const layout of ['2.0', '5.0', '5.1']) {
    assert.match(audioPresetProblem(setting, encodes, source(layout)), /more channels/)
    assert.match(audioPresetProblem({ ...setting, layout }, encodes), /does not support/)
  }
  const applied = applyAudioPreset({ ...preset, flags: {} }, setting)
  assert.equal(audioPresetSettings(applied).options.ddp_mode, 'bluray')
})

test('automatic output layouts still enforce bitrate limits for the actual source', () => {
  const setting = { ...preset, action: 'opus', layout: null, bitrate_kbps: 384 } as AudioPresetSettings
  assert.match(audioPresetProblem(setting, encodes, source('1.0')), /exceeds the limit/)
  assert.equal(audioPresetProblem(setting, encodes, source('2.0')), '')
  assert.match(audioPresetProblem({ ...setting, bitrate_kbps: 3000 }, encodes, source('7.1')), /takes 6 to 2048/)
  assert.match(
    audioPresetProblem({ ...preset, action: 'ac3', bitrate_kbps: 641 }, encodes, source('5.1')),
    /not supported/,
  )
})

test('missing tools disable direct application without preventing template configuration', () => {
  const unavailable = [{ ...ddp, missing: ['dee'] }]
  assert.match(audioPresetProblem(preset, unavailable, source('5.1')), /Needs dee/)
  assert.equal(audioPresetProblem(preset, unavailable), '')
  assert.match(audioPresetProblem(preset, [], source('5.1')), /unavailable/)
  assert.equal(audioPresetProblem({ ...preset, action: 'copy' }, [], source('2.0')), '')
})

test('built-ins provide 5.1 640 kb/s and source-independent encoder defaults', () => {
  const choices = audioPresetDefaults(encodes)
  const surround = choices.find((c) => c.data.action === 'ddp' && c.data.layout === '5.1')!
  assert.equal(surround.label, '5.1 640 kb/s')
  assert.equal(surround.data.bitrate_kbps, 640)
  assert.equal(choices.find((c) => c.data.action === 'ddp' && c.label === 'Encoder defaults')!.data.layout, null)
  assert.equal(new Set(choices.map((c) => c.name)).size, choices.length)
})

test('custom preset titles override output titles for encode and copy; untitled presets preserve edits', () => {
  const track = { ...preset, title: 'Source title', language: 'en', flags: {} } as TrackOverride
  assert.equal(applyAudioPreset(track, { ...preset, title: 'Bob' }).title, 'Bob')
  assert.equal(applyAudioPreset(track, { ...preset, action: 'copy', title: 'Bob' }).title, 'Bob')
  assert.equal(applyAudioPreset(track, { ...preset, title: null }).title, 'Source title')
  assert.equal(audioPresetSettings({ ...track, action: 'copy', title: 'Bob' }).title, 'Bob')
  assert.equal(audioPresetSettings().title, null)
})
