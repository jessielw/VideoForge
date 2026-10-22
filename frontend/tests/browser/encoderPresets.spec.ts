import { readFile } from 'node:fs/promises'
import { test, expect, type Page } from '@playwright/test'
import type { EncoderBundle, EncoderSettings, Presets, Profile, Template } from '../../src/lib/types.ts'

const defaults: EncoderSettings = { encoder: 'x264', rate_control: 'crf', crf: 18, bitrate_kbps: 8000, target_mb: null,
  preset: 'slow', tune: '', depth: 8, options: {}, extra: '', source_color: true, hdr10plus: false, dolby_vision: false }
const saved = { name: 'library-id', label: 'Selected film', group: ['1080p', 'SDR'],
  data: { ...defaults, crf: 23, preset: 'veryslow', tune: 'grain', options: { ref: '5' } } }

async function fixture(page: Page) {
  const errors: string[] = []
  const exports: EncoderBundle[] = []
  const imports: EncoderBundle[] = []
  page.on('pageerror', error => errors.push(error.message))
  const template: Template = {
    video: { source_filter: 'ffms2', crop: { left: 0, top: 0, right: 0, bottom: 0 }, resize: null, filters: [], custom: null },
    encoder: defaults, mux: { container: 'mkv', extra: '', pgs_zlib: false }, qpf: true, crop_mode: 'keep', audio: null, subs: null,
  }
  const profile: Profile = { id: 'manual', name: 'Manual', default: true, container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }], external_subtitles: true,
    track_editor: true, track_properties: [], defaults: { video: template.video, encoder: defaults, template } }
  const presets: Presets = { video: [], encoder: [structuredClone(saved)], audio: [],
    template: [{ name: 'Current template', data: template }], template_defaults: { manual: 'Current template' }, encoder_starters: [] }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/presets/encoders/export') {
      exports.push(request.postDataJSON())
      await route.fulfill({ json: exports.at(-1) })
    } else if (path === '/api/presets/encoders/preview') {
      const bundle: EncoderBundle = request.postDataJSON()
      await route.fulfill({ json: { bundle, names: bundle.encoders.map(entry => `${entry.label} (2)`) } })
    } else if (path === '/api/presets/encoders/import') {
      const bundle: EncoderBundle = request.postDataJSON()
      imports.push(bundle)
      const names = bundle.encoders.map(entry => `${entry.label} (2)`)
      presets.encoder.push(...bundle.encoders.map((entry, i) => ({ ...entry, name: `import-${i}`, label: names[i] })))
      await route.fulfill({ json: { presets, names } })
    } else {
      const responses: Record<string, unknown> = { '/api/jobs': [], '/api/profiles': [profile], '/api/presets': presets,
        '/api/health': { ok: true, version: 'test' }, '/api/filter-presets': [], '/api/config/encoders': [],
        '/api/config/video-options/x264': { dashes: '--', options: [] } }
      if (!(path in responses)) throw new Error(`Unexpected encoder fixture request: ${path}`)
      await route.fulfill({ json: responses[path] })
    }
  })
  await page.goto('/#/templates')
  await page.getByRole('button', { name: 'Encoder presets', exact: true }).click()
  await page.getByRole('button', { name: 'Manage presets…' }).click()
  const manager = page.getByRole('dialog', { name: 'Encoder presets', exact: true })
  await expect(manager).toBeVisible()
  return { manager, errors, exports, imports }
}

test('New from current settings copies the selected library preset and its draft edits', async ({ page }, testInfo) => {
  const { manager, errors, exports } = await fixture(page)
  await manager.getByRole('textbox', { name: 'Search encoder presets' }).fill('Selected film')
  await manager.getByRole('button', { name: /Selected film/ }).click()
  await expect(manager.getByRole('spinbutton', { name: 'CRF', exact: true })).toHaveValue('23')
  await manager.getByRole('spinbutton', { name: 'CRF', exact: true }).fill('24')
  await manager.getByRole('button', { name: 'New from current settings', exact: true }).click()
  await manager.getByRole('button', { name: 'Discard changes', exact: true }).click()
  await expect(manager.getByRole('textbox', { name: 'Encoder preset name', exact: true })).toHaveValue('')
  await expect(manager.getByRole('textbox', { name: 'Encoder preset folder', exact: true })).toHaveValue('1080p / SDR')
  await expect(manager.getByRole('spinbutton', { name: 'CRF', exact: true })).toHaveValue('24')
  await expect(manager.getByRole('combobox', { name: 'Speed preset', exact: true })).toHaveValue('veryslow')
  await page.screenshot({ path: testInfo.outputPath('encoder-preset-manager.png') })
  const download = page.waitForEvent('download')
  await manager.getByRole('button', { name: 'Export current settings', exact: true }).click()
  const file = await download
  const doc = JSON.parse(await readFile((await file.path())!, 'utf8'))
  expect(doc.encoders[0]).toEqual({ label: 'x264 settings', group: saved.group, data: { ...saved.data, crf: 24 } })
  expect(exports).toEqual([doc])
  await manager.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByRole('spinbutton', { name: 'CRF', exact: true })).toHaveValue('18')
  expect(errors).toEqual([])
})

test('saved export uses portable labels and folders, and clearing selection disables export', async ({ page }) => {
  const { manager, errors } = await fixture(page)
  await manager.getByRole('button', { name: 'Export…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Export encoder presets', exact: true })
  await dialog.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Export 0 selected', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Select all', exact: true }).click()
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Export 1 selected', exact: true }).click()
  const doc = JSON.parse(await readFile((await (await download).path())!, 'utf8'))
  expect(doc).toEqual({ format: 'videoforge.encoders', version: 1,
    encoders: [{ label: saved.label, group: saved.group, data: saved.data }] })
  await expect(manager).toBeVisible()
  expect(errors).toEqual([])
})

test('import previews conflicts, imports selected presets, and preserves the open draft', async ({ page }) => {
  const { manager, errors, imports } = await fixture(page)
  await manager.getByRole('spinbutton', { name: 'CRF', exact: true }).fill('21')
  await manager.getByRole('button', { name: 'Import', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import encoder presets', exact: true })
  await dialog.locator('input[type=file]').setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from('{bad') })
  await expect(dialog.getByRole('alert')).toContainText('not valid JSON')
  const entries = [{ label: 'Selected film', group: ['1080p', 'SDR'], data: saved.data },
    { label: 'Skip me', group: [], data: defaults }]
  await dialog.locator('input[type=file]').setInputFiles({ name: 'encoder-presets.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ format: 'videoforge.encoders', version: 1, encoders: entries })) })
  await expect(dialog).toContainText('Selected film (2)')
  await dialog.getByRole('checkbox').nth(1).uncheck()
  await dialog.getByRole('button', { name: 'Import 1', exact: true }).click()
  expect(imports).toEqual([{ format: 'videoforge.encoders', version: 1, encoders: [entries[0]] }])
  await expect(manager.getByRole('spinbutton', { name: 'CRF', exact: true })).toHaveValue('21')
  await manager.getByRole('textbox', { name: 'Search encoder presets' }).fill('Selected film (2)')
  await expect(manager.getByRole('button', { name: /Selected film \(2\)/ })).toBeVisible()
  expect(errors).toEqual([])
})
