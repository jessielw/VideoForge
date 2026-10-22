import { readFile } from 'node:fs/promises'
import { test, expect, type Page } from '@playwright/test'
import type { AudioBundle, AudioEncodeInfo, AudioPresetSettings, Presets, Profile, Template, TrackOverride } from '../../src/lib/types.ts'

const settings: AudioPresetSettings = { action: 'ddp', layout: '5.1', bitrate_kbps: 640, options: { dialnorm: '-27' }, title: 'Bob' }
const saved = { name: 'audio-id', label: 'Surround', group: ['Home cinema'], data: settings }

async function fixture(page: Page) {
  const errors: string[] = []
  const exports: AudioBundle[] = []
  const imports: AudioBundle[] = []
  page.on('pageerror', error => errors.push(error.message))
  const track: TrackOverride = { ...settings, title: 'Source commentary', language: null, exclude: null, flags: {} }
  const template: Template = {
    video: { source_filter: 'ffms2', crop: { left: 0, top: 0, right: 0, bottom: 0 }, resize: null, filters: [], custom: null },
    encoder: { encoder: 'x264', rate_control: 'crf', crf: 18, bitrate_kbps: 8000, target_mb: null,
      preset: 'slow', tune: '', depth: 8, options: {}, extra: '', source_color: true, hdr10plus: false, dolby_vision: false },
    mux: { container: 'mkv', extra: '', pgs_zlib: false }, qpf: true, crop_mode: 'keep', subs: null,
    audio: { mode: 'position', slots: [{ track, extra: [] }], rules: [], others: 'keep' },
  }
  const profile: Profile = { id: 'manual', name: 'Manual', default: true, container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }], external_subtitles: true,
    track_editor: true, track_properties: [], defaults: { video: template.video, encoder: template.encoder, template } }
  const enc: AudioEncodeInfo = { id: 'ddp', label: 'DDP (DEE)', codec: 'eac3', layouts: ['2.0', '5.1'],
    bitrates: { '2': 256, '6': 640 }, bitrate_choices: [], bitrate_range: null, per_channel_max: null,
    vbr_default: false, default_max: null, missing: [], options: [] }
  const presets: Presets = { video: [], encoder: [], audio: [structuredClone(saved)],
    template: [{ name: 'Current template', data: template }], template_defaults: { manual: 'Current template' }, encoder_starters: [] }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/presets/audio/export') {
      exports.push(request.postDataJSON())
      await route.fulfill({ json: exports.at(-1) })
    } else if (path === '/api/presets/audio/preview') {
      const bundle: AudioBundle = request.postDataJSON()
      await route.fulfill({ json: { bundle, names: bundle.audio.map(entry => `${entry.label} (2)`) } })
    } else if (path === '/api/presets/audio/import') {
      const bundle: AudioBundle = request.postDataJSON()
      imports.push(bundle)
      const names = bundle.audio.map(entry => `${entry.label} (2)`)
      presets.audio.push(...bundle.audio.map((entry, i) => ({ ...entry, name: `import-${i}`, label: names[i] })))
      await route.fulfill({ json: { presets, names } })
    } else if (path === '/api/presets/audio' && request.method() === 'POST') {
      const body = request.postDataJSON()
      presets.audio = presets.audio.map(entry => entry.name === body.name ? { ...body, name: entry.name } : entry)
      await route.fulfill({ json: presets })
    } else {
      const responses: Record<string, unknown> = { '/api/jobs': [], '/api/profiles': [profile], '/api/presets': presets,
        '/api/health': { ok: true, version: 'test' }, '/api/filter-presets': [], '/api/config/encoders': [enc],
        '/api/config/video-options/x264': { dashes: '--', options: [] } }
      if (!(path in responses)) throw new Error(`Unexpected audio fixture request: ${path}`)
      await route.fulfill({ json: responses[path] })
    }
  })
  await page.goto('/#/templates')
  const output = page.getByRole('group', { name: 'Audio track 1', exact: true })
  const openManager = async () => {
    await output.getByRole('button', { name: 'Audio presets', exact: true }).click()
    await page.getByRole('button', { name: 'Manage presets…', exact: true }).click()
    return page.getByRole('dialog', { name: 'Audio presets', exact: true })
  }
  return { output, openManager, errors, exports, imports }
}

test('saved titles apply, remain editable, and survive saving and selecting again', async ({ page }) => {
  const { output, openManager, errors } = await fixture(page)
  await expect(output.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue('Source commentary')
  const manager = await openManager()
  await manager.getByRole('textbox', { name: 'Search audio presets' }).fill('Surround')
  await manager.getByRole('button', { name: /Surround/ }).click()
  await expect(manager.getByRole('textbox', { name: 'Track title', exact: true })).toHaveValue('Bob')
  await manager.getByRole('textbox', { name: 'Track title', exact: true }).fill('Bob edited')
  await manager.getByRole('textbox', { name: 'Track title', exact: true }).blur()
  await manager.getByRole('button', { name: 'Save preset', exact: true }).click()
  await expect(output.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue('Source commentary')
  await manager.getByRole('button', { name: 'Apply to this output', exact: true }).click()
  await expect(output.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue('Bob edited')
  await output.getByRole('textbox', { name: 'Title', exact: true }).fill('Manual edit')
  await output.getByRole('textbox', { name: 'Title', exact: true }).blur()
  await output.getByRole('button', { name: 'Audio presets', exact: true }).click()
  await page.getByRole('textbox', { name: 'Search audio presets' }).fill('Surround')
  await page.getByRole('button', { name: /Surround/ }).click()
  await expect(output.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue('Bob edited')
  expect(errors).toEqual([])
})

test('audio export includes the open draft; import preserves edits and selects entries', async ({ page }, testInfo) => {
  const { openManager, errors, exports, imports } = await fixture(page)
  const manager = await openManager()
  await manager.getByRole('textbox', { name: 'Track title', exact: true }).fill('Unsaved title')
  const download = page.waitForEvent('download')
  await manager.getByRole('button', { name: 'Export current settings', exact: true }).click()
  const doc = JSON.parse(await readFile((await (await download).path())!, 'utf8'))
  expect(doc.audio[0].data.title).toBe('Unsaved title')
  expect(exports).toEqual([doc])
  await manager.getByRole('button', { name: 'Import', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import audio presets', exact: true })
  await dialog.locator('input[type=file]').setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from('{bad') })
  await expect(dialog.getByRole('alert')).toContainText('not valid JSON')
  const entries = [{ label: saved.label, group: saved.group, data: settings }, { label: 'Skip', group: [], data: settings }]
  await dialog.locator('input[type=file]').setInputFiles({ name: 'audio-presets.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ format: 'videoforge.audio', version: 1, audio: entries })) })
  await expect(dialog).toContainText('Surround (2)')
  await dialog.getByRole('checkbox').nth(1).uncheck()
  await dialog.getByRole('button', { name: 'Import 1', exact: true }).click()
  expect(imports).toEqual([{ format: 'videoforge.audio', version: 1, audio: [entries[0]] }])
  await expect(manager.getByRole('textbox', { name: 'Track title', exact: true })).toHaveValue('Unsaved title')
  await page.screenshot({ path: testInfo.outputPath('audio-preset-manager.png') })
  await manager.getByRole('button', { name: 'Close preset manager', exact: true }).click()
  await expect(manager.getByRole('alert')).toContainText('Save your preset changes')
  await manager.getByRole('button', { name: 'Discard changes', exact: true }).click()
  expect(errors).toEqual([])
})

test('saved audio exports preserve titles and folders and require a selection', async ({ page }) => {
  const { openManager, errors } = await fixture(page)
  const manager = await openManager()
  await manager.getByRole('button', { name: 'Export…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Export audio presets', exact: true })
  await dialog.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Export 0 selected', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Select all', exact: true }).click()
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Export 1 selected', exact: true }).click()
  const doc = JSON.parse(await readFile((await (await download).path())!, 'utf8'))
  expect(doc).toEqual({ format: 'videoforge.audio', version: 1,
    audio: [{ label: saved.label, group: saved.group, data: settings }] })
  await expect(manager).toBeVisible()
  expect(errors).toEqual([])
})
