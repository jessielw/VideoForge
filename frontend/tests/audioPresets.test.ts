import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  applyAudioPreset,
  audioPresetDefaults,
  audioPresetProblem,
  audioPresetSettings,
  fitLayoutAndBitrate,
} from '../src/lib/audioPresets.ts'
import type { AudioEncodeInfo, AudioPresetSettings, AudioTrack, TrackOverride } from '../src/lib/types.ts'

const limits = { bitrate_choices: [], bitrate_range: null, per_channel_max: null, layout_rates: {} }
const choice = (key: string, label: string, ...values: [string, string][]) => ({
  key,
  label,
  default: values[0][0],
  help: '',
  choices: values.map(([value, label]) => ({ value, label })),
  range: null,
  step: 1,
  when: null,
})
// as the server describes them (GET /api/config/encoders), trimmed
const ddp: AudioEncodeInfo = {
  id: 'ddp',
  label: 'DDP (DEE)',
  codec: 'eac3',
  layouts: ['1.0', '2.0', '5.0', '5.1', '7.1'],
  bitrates: { '1': 192, '2': 256, '6': 640, '8': 1024 },
  ...limits,
  layout_rates: { '5.1': [192, 448, 576, 640, 704, 1024], '7.1': [384, 1024, 1280, 1536, 1792] },
  vbr_default: false,
  default_max: null,
  adds_no_speakers: true,
  modes: [
    {
      key: 'ddp_mode',
      value: 'bluray',
      layouts: ['7.1'],
      bitrates: { '8': 1280 },
      ...limits,
      layout_rates: { '7.1': [768, 1024, 1280, 1536, 1664] },
    },
  ],
  missing: [],
  options: [choice('ddp_mode', 'DDP mode', ['standard', 'Standard'], ['bluray', 'Blu-ray'])],
}
const plain = { ...limits, adds_no_speakers: false, modes: [], options: [] }
const opus: AudioEncodeInfo = {
  ...ddp,
  ...plain,
  id: 'opus',
  label: 'Opus',
  bitrate_range: [6, 2048],
  per_channel_max: 256,
}
const ac3: AudioEncodeInfo = {
  ...ddp,
  ...plain,
  id: 'ac3',
  label: 'AC-3',
  layouts: ['1.0', '2.0', '5.0', '5.1'],
  bitrate_choices: [192, 224, 448, 640],
}
const atmos: AudioEncodeInfo = {
  ...ddp,
  ...plain,
  id: 'atmos',
  label: 'Atmos',
  layouts: ['5.1'],
  bitrates: { '6': 768 },
  layout_rates: { '5.1': [384, 448, 576, 640, 768, 1024] },
  modes: [
    {
      key: 'atmos_mode',
      value: 'standard',
      layouts: ['7.1'],
      bitrates: { '8': 1152 },
      ...limits,
      bitrate_range: [448, 2048],
    },
    {
      key: 'atmos_mode',
      value: 'bluray',
      layouts: ['7.1'],
      bitrates: { '8': 1280 },
      ...limits,
      layout_rates: { '7.1': [1152, 1280, 1408, 1512, 1536, 1664] },
    },
  ],
  options: [
    choice(
      'atmos_mode',
      'Atmos mode',
      ['streaming', 'Streaming (5.1)'],
      ['standard', 'Standard (7.1)'],
      ['bluray', 'Blu-ray (7.1, AC-3 core)'],
    ),
  ],
}
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
  const setting = { ...preset, action: 'atmos', bitrate_kbps: 768 } as AudioPresetSettings
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

test('DDP takes DEE rates per layout and adds no speaker the source lacks', () => {
  assert.match(
    audioPresetProblem({ ...preset, bitrate_kbps: 650 }, encodes, source('5.1')),
    /DDP \(DEE\) at 5.1 takes 640 or 704 kb\/s, not 650/,
  )
  assert.equal(audioPresetProblem({ ...preset, layout: '7.1', bitrate_kbps: 1792 }, encodes, source('7.1')), '')
  // 5.1 from 5.0, 6.0 or 7.0 is DDP's upmix (6.0 and 7.0 by a 5.0 downmix); 4.1 has no center for 5.0
  for (const layout of ['5.0', '6.0', '7.0']) assert.equal(audioPresetProblem(preset, encodes, source(layout)), '')
  const quad = { ...preset, layout: '5.0', bitrate_kbps: null }
  assert.match(audioPresetProblem(quad, encodes, source('4.1')), /adds a speaker this 4.1 source doesn't have/)
  const auto = { ...preset, layout: null, bitrate_kbps: null }
  assert.equal(audioPresetProblem(auto, encodes, source('7.0')), '') // 7.0 defaults to 5.0
  assert.equal(audioPresetProblem({ ...preset, layout: '5.0', bitrate_kbps: null }, encodes, source('5.1')), '')
})

test('Atmos modes bring their own 7.1 bed and rates, whatever the TrueHD core', () => {
  const thd = source('5.1', 'truehd', true)
  const standard: AudioPresetSettings = {
    action: 'atmos',
    layout: null,
    bitrate_kbps: 1152,
    options: { atmos_mode: 'standard' },
  }
  assert.equal(audioPresetProblem(standard, encodes, thd), '')
  assert.equal(audioPresetProblem({ ...standard, layout: '7.1' }, encodes, thd), '')
  assert.match(audioPresetProblem({ ...standard, layout: '5.1' }, encodes, thd), /does not support 5.1/)
  const bluray = { ...standard, options: { atmos_mode: 'bluray' }, bitrate_kbps: 1024 }
  assert.match(audioPresetProblem(bluray, encodes), /Atmos at 7.1 takes 1152 kb\/s, not 1024/)
  assert.match(audioPresetProblem({ ...standard, options: {}, bitrate_kbps: 512 }, encodes), /takes 448 or 576/)
})

test('a layout and bitrate a new mode or layout does not take go back to auto', () => {
  const fit = fitLayoutAndBitrate
  assert.deepEqual(fit(ddp, { ddp_mode: 'bluray' }, '5.1', 640), { layout: null, bitrate_kbps: null })
  assert.deepEqual(fit(ddp, { ddp_mode: 'bluray' }, '7.1', 1280), { layout: '7.1', bitrate_kbps: 1280 })
  assert.deepEqual(fit(ddp, {}, '5.1', 1280), { layout: '5.1', bitrate_kbps: null })
  assert.deepEqual(fit(atmos, { atmos_mode: 'standard' }, null, 1024), { layout: null, bitrate_kbps: 1024 })
  assert.deepEqual(fit(atmos, { atmos_mode: 'bluray' }, null, 1024), { layout: null, bitrate_kbps: null })
})

test('built-ins include each mode, named after it', () => {
  const byName = new Map(audioPresetDefaults(encodes).map((c) => [c.name, c]))
  assert.equal(byName.get('ddp:ddp_mode=bluray:7.1')!.label, '7.1 1280 kb/s · Blu-ray')
  assert.deepEqual(byName.get('ddp:ddp_mode=bluray:7.1')!.data.options, { ddp_mode: 'bluray' })
  assert.equal(byName.get('atmos:atmos_mode=standard:7.1')!.label, '7.1 1152 kb/s · Standard')
  assert.equal(byName.get('atmos:5.1')!.label, '5.1 768 kb/s')
  assert.equal(byName.get('ddp:5.0')!.label, '5.0 640 kb/s')
})
