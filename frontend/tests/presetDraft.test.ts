import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canonical, draftFromChoice, duplicatePresetDraft, folderParts, matchingPreset, newPresetDraft, presetKey, saveDestination, type PresetChoice } from '../src/lib/presetDraft.ts'

type Settings = { encoder: string; crf: number; options: Record<string, string> }
const data: Settings = { encoder: 'x265', crf: 18, options: { tune: 'grain', 'aq-mode': '3' } }
const choice: PresetChoice<Settings> = { name: 'stable-id', label: 'Grain', group: ['1080p', 'SDR'], data, builtin: false }
const parentOf = (value: Settings) => value.encoder

test('editing a saved preset uses a snapshot without changing the library or current settings', () => {
  const draft = draftFromChoice(choice)
  assert.equal(draft.name, 'stable-id')
  assert.equal(draft.folder, '1080p / SDR')
  draft.data.options.tune = 'animation'
  draft.data.crf = 20
  assert.equal(choice.data.options.tune, 'grain')
  assert.equal(choice.data.crf, 18)
})

test('built-ins save as independent copies instead of replacing a built-in identity', () => {
  const draft = draftFromChoice({ ...choice, builtin: true })
  assert.equal(draft.name, undefined)
  const payload = saveDestination(draft, [{ ...choice, builtin: true }], parentOf)
  assert.equal(payload.name, undefined)
  assert.equal(payload.label, 'Grain')
})

test('new from current settings starts with a blank name and an independent configuration', () => {
  const draft = newPresetDraft(data)
  assert.equal(draft.label, '')
  assert.equal(draft.folder, '')
  draft.data.options.tune = 'animation'
  assert.equal(data.options.tune, 'grain')
})

test('duplicating a library preset keeps its draft settings and folder with a unique name', () => {
  const draft = draftFromChoice(choice)
  draft.data.crf = 20
  const existing = { ...choice, name: 'copy-id', label: 'Grain copy' }
  const duplicate = duplicatePresetDraft(draft, [choice, existing], parentOf)
  assert.equal(duplicate.name, undefined)
  assert.equal(duplicate.label, 'Grain copy 2')
  assert.equal(duplicate.folder, draft.folder)
  assert.equal(duplicate.data.crf, 20)
  duplicate.data.options.tune = 'animation'
  assert.equal(draft.data.options.tune, 'grain')
  assert.equal(choice.data.crf, 18)
})

test('saving normalizes labels/folders and returns a payload independent of the editor draft', () => {
  const draft = draftFromChoice(choice)
  draft.label = ' Grain revised '
  draft.folder = ' 2160p / Dolby Vision '
  const payload = saveDestination(draft, [choice], parentOf)
  assert.deepEqual(payload.group, ['2160p', 'Dolby Vision'])
  assert.equal(payload.label, 'Grain revised')
  assert.equal(payload.name, choice.name)
  payload.data.options.tune = 'animation'
  assert.equal(draft.data.options.tune, 'grain')
  assert.deepEqual(folderParts(''), [])
})

test('Replace targets only the matching encoder, folder, and name', () => {
  const draft = newPresetDraft(data, '1080p / SDR')
  draft.label = 'Grain'
  assert.equal(saveDestination(draft, [choice], parentOf).name, choice.name)
  draft.folder = '2160p / SDR'
  assert.equal(saveDestination(draft, [choice], parentOf).name, undefined)
  draft.folder = '1080p / SDR'
  draft.data.encoder = 'x264'
  assert.equal(saveDestination(draft, [choice], parentOf).name, undefined)
})

test('renaming/moving one saved preset cannot accidentally overwrite another', () => {
  const other = { ...choice, name: 'another-id', label: 'Film' }
  const draft = draftFromChoice(choice)
  draft.label = 'Film'
  assert.throws(() => saveDestination(draft, [choice, other], parentOf), /already exists/)
})

test('matching preserves a selected folder when several presets have identical settings', () => {
  const other = { ...choice, name: 'another-id', group: ['2160p', 'HDR10'] }
  assert.equal(matchingPreset([choice, other], data, presetKey(other)), other)
  const edited = { ...data, crf: 24 }
  assert.equal(matchingPreset([choice, other], edited), undefined)
})

test('option ordering does not mark a draft changed, while settings and metadata edits do', () => {
  const draft = draftFromChoice(choice)
  const baseline = canonical(draft)
  draft.data.options = { 'aq-mode': '3', tune: 'grain' }
  assert.equal(canonical(draft), baseline)
  draft.folder = '2160p / SDR'
  assert.notEqual(canonical(draft), baseline)
  draft.folder = '1080p / SDR'
  draft.data.crf = 19
  assert.notEqual(canonical(draft), baseline)
})
