import { readFile } from 'node:fs/promises'
import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, ConfigurationBundle, PresetKind, PresetPack, Presets, Profile, Template } from '../../src/lib/types.ts'
import { presetPack } from '../../src/lib/presetPack.ts'

async function fixture(page: Page) {
  const errors: string[] = []
  const imported: ConfigurationBundle[] = []
  const exportedPacks: PresetPack[] = []
  const importedPacks: PresetPack[] = []
  page.on('pageerror', error => errors.push(error.message))
  const template: Template = {
    video: { source_filter: 'ffms2', crop: { left: 0, top: 0, right: 0, bottom: 0 }, resize: null, filters: [], custom: 'clip = src' },
    encoder: { encoder: 'x264', rate_control: 'crf', crf: 18, bitrate_kbps: 8000, target_mb: null, preset: 'slow', tune: '', depth: 8, options: {}, extra: '', source_color: true, hdr10plus: false, dolby_vision: false },
    mux: { container: 'mkv', extra: '', pgs_zlib: false }, qpf: true, crop_mode: 'keep', audio: null, subs: null,
  }
  const profile: Profile = { id: 'manual', name: 'Manual', default: true, container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }], external_subtitles: true,
    track_editor: true, track_properties: [], defaults: { video: template.video, encoder: template.encoder, template } }
  const config: ConfigState = {
    tools: [{ name: 'ffmpeg', label: 'ffmpeg', purpose: 'Audio and video', folder: false, path: 'ffmpeg', default: 'ffmpeg', custom: null }],
    roots: ['D:\\Media'], roots_custom: false, default_roots: ['D:\\Media'], profile: 'manual', profile_default: 'manual', profiles: [profile], restart: [],
    index_waits_for_disk: true, parallel_audio: 2, parallel_audio_default: 2, delete_work_dir: false, delete_work_dir_default: false,
    encoder_priority: 'normal', encoder_priority_default: 'normal', tool_priority: 'normal', tool_priority_default: 'normal', priorities: ['normal'],
    records_dir: 'D:\\VideoForge\\records', notifications: [], notification_events: [], actions: [],
    action_kinds: [{ id: 'move', label: 'Move output' }, { id: 'command', label: 'Run command' }],
    action_tokens: { job: {}, queue: {} }, allow_commands: false, plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  const bundle: ConfigurationBundle = { format: 'videoforge.configuration', version: 1,
    application: { allow_commands: false }, settings: { notifications: [], actions: [], disabled_plugins: [], parallel_audio: 4 },
    folders: { output_dir: 'D:\\Output', last_dir: 'D:\\Media' },
    presets: { template: [{ name: 'Film', data: template }], video: [],
      encoder: [{ name: 'encoder-id', label: 'Grain', group: ['1080p', 'SDR'], data: template.encoder }],
      audio: [{ name: 'audio-id', label: 'Stereo', group: ['AAC'], data: { action: 'aac_ffmpeg', layout: null, bitrate_kbps: 128, options: {} } }] },
    template_defaults: { manual: 'Film' },
  }
  const presets: Presets = { ...bundle.presets, template_defaults: bundle.template_defaults, encoder_starters: [] }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/preset-packs/export') {
      exportedPacks.push(request.postDataJSON())
      await route.fulfill({ json: exportedPacks.at(-1) })
    } else if (path === '/api/preset-packs/preview' || path === '/api/preset-packs/import') {
      const pack: PresetPack = request.postDataJSON()
      if (pack.format !== 'videoforge.presets') {
        await route.fulfill({ status: 422, json: { detail: 'Choose a VideoForge preset pack' } })
        return
      }
      const names = Object.fromEntries(Object.entries(pack.presets).map(([kind, entries]) => [kind,
        entries.map(entry => `${'label' in entry ? entry.label : entry.name} (2)`)])) as Record<PresetKind, string[]>
      if (path.endsWith('/preview')) await route.fulfill({ json: { bundle: pack, names } })
      else {
        importedPacks.push(pack)
        presets.audio.push(...pack.presets.audio.map((entry, i) => ({ ...entry, name: `import-${i}`, label: names.audio[i] })))
        await route.fulfill({ json: { presets, names } })
      }
    } else if (path === '/api/configuration/export') await route.fulfill({ json: bundle })
    else if (path === '/api/configuration/preview') {
      const data: ConfigurationBundle = request.postDataJSON()
      if (data.version !== 1) {
        await route.fulfill({ status: 422, json: { detail: 'Unsupported configuration version' } })
        return
      }
      await route.fulfill({ json: { bundle: data, counts: { template: 1, encoder: 1, audio: 1, video: 0 },
        current_counts: { template: 2, encoder: 3, audio: 4, video: 1 }, warnings: ['Check tool paths on this computer.'] } })
    } else if (path === '/api/configuration/import') {
      imported.push(request.postDataJSON())
      config.parallel_audio = 4
      await route.fulfill({ json: { config, presets, warnings: [] } })
    } else {
      const responses: Record<string, unknown> = { '/api/jobs': [], '/api/profiles': [profile], '/api/presets': presets,
        '/api/health': { ok: true, version: 'test' }, '/api/filter-presets': [], '/api/config/encoders': [],
        '/api/config': config, '/api/config/tools': [], '/api/config/video-options/x264': { dashes: '--', options: [] } }
      if (!(path in responses)) throw new Error(`Unexpected configuration fixture request: ${path}`)
      await route.fulfill({ json: responses[path] })
    }
  })
  await page.goto('/#/settings')
  await expect(page.getByRole('heading', { name: 'Configuration backup', exact: true })).toBeVisible()
  return { bundle, imported, errors, exportedPacks, importedPacks }
}

test('exports the whole configuration from Settings with an empty queue', async ({ page }) => {
  const { bundle, errors } = await fixture(page)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export configuration', exact: true }).click()
  const file = await download
  expect(file.suggestedFilename()).toMatch(/^videoforge-configuration-\d{4}-\d{2}-\d{2}\.json$/)
  expect(JSON.parse(await readFile((await file.path())!, 'utf8'))).toEqual(bundle)
  expect(errors).toEqual([])
})

test('audio and video encoder libraries open from Settings with an empty queue', async ({ page }, testInfo) => {
  const { errors } = await fixture(page)
  for (const [button, title] of [['Manage audio presets', 'Audio presets'], ['Manage video encoder presets', 'Encoder presets']]) {
    await page.getByRole('button', { name: button, exact: true }).click()
    const manager = page.getByRole('dialog', { name: title, exact: true })
    await expect(manager).toBeVisible()
    await expect(manager.getByRole('button', { name: 'New preset', exact: true })).toBeVisible()
    await expect(manager.getByRole('button', { name: /Apply/ })).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath(`${title.replaceAll(' ', '-')}.png`) })
    await manager.getByRole('button', { name: 'Close', exact: true }).click()
    await expect(manager).not.toBeVisible()
    await expect(page.getByRole('button', { name: button, exact: true })).toBeFocused()
  }
  expect(errors).toEqual([])
})

test('previews all libraries and requires replacement confirmation before importing', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('videoforge.draft.templates', JSON.stringify({ version: 1, value: { draftName: 'Outdated' } }))
    sessionStorage.setItem('videoforge.draft.new-jobs', JSON.stringify({ version: 1, value: {
      sources: ['movie.mkv'], profile: 'old-profile', templateName: 'Old template', encoder: { crf: 25 }, container: 'mp4', output: ['old-output'],
    } }))
  })
  const { bundle, imported, errors } = await fixture(page)
  await page.getByRole('button', { name: 'Import configuration…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import configuration', exact: true })
  const button = dialog.getByRole('button', { name: 'Import configuration', exact: true })
  await expect(button).toBeDisabled()
  await dialog.locator('input[type=file]').setInputFiles({ name: 'backup.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bundle)) })
  await expect(dialog.getByRole('row')).toHaveCount(5)
  await expect(dialog).toContainText('Video encoder presets')
  await expect(dialog).toContainText('Audio encoder presets')
  await expect(dialog).toContainText('Check tool paths on this computer.')
  await dialog.getByText('Review included scripts and actions', { exact: true }).click()
  await expect(dialog.locator('pre')).toHaveText('clip = src')
  await expect(button).toBeDisabled()
  expect(imported).toEqual([])
  await dialog.getByRole('checkbox').check()
  await page.screenshot({ path: testInfo.outputPath('configuration-import.png') })
  await button.click()
  await expect(dialog).not.toBeVisible()
  expect(imported).toEqual([bundle])
  await expect(page.getByRole('spinbutton')).toHaveValue('4')
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('videoforge.draft.templates')!))).toEqual({ version: 1, value: null })
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('videoforge.draft.new-jobs')!).value)).toEqual({
    sources: ['movie.mkv'], profile: '', templateName: null, encoder: null, container: '', output: [],
  })
  await page.getByRole('button', { name: 'Templates', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Template name', exact: true })).toHaveValue('Film')
  expect(errors).toEqual([])
})

test('invalid files and cancelled imports leave settings untouched', async ({ page }) => {
  const { bundle, imported, errors } = await fixture(page)
  await page.getByRole('button', { name: 'Import configuration…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import configuration', exact: true })
  const file = dialog.locator('input[type=file]')
  await file.setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from('{bad') })
  await expect(dialog.getByRole('alert')).toContainText('not valid JSON')
  await file.setInputFiles({ name: 'future.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ ...bundle, version: 2 })) })
  await expect(dialog.getByRole('alert')).toContainText('Unsupported configuration version')
  await expect(dialog.getByRole('button', { name: 'Import configuration', exact: true })).toBeDisabled()
  await file.setInputFiles({ name: 'backup.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bundle)) })
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  expect(imported).toEqual([])
  await expect(page.getByRole('spinbutton')).toHaveValue('2')
  expect(errors).toEqual([])
})

test('exports selected templates and encoder presets without application configuration', async ({ page }, testInfo) => {
  const { bundle, exportedPacks, errors } = await fixture(page)
  await page.getByRole('button', { name: 'Export presets…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Export preset pack', exact: true })
  await dialog.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Export 0 selected', exact: true })).toBeDisabled()
  await dialog.getByRole('checkbox', { name: 'Film', exact: true }).check()
  await dialog.getByRole('checkbox', { name: /Grain/ }).check()
  await page.screenshot({ path: testInfo.outputPath('preset-sharing-export.png') })
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Export 2 selected', exact: true }).click()
  const file = await download
  const doc = JSON.parse(await readFile((await file.path())!, 'utf8'))
  const expected = presetPack({ ...bundle.presets, audio: [], video: [] })
  expect(doc).toEqual(expected)
  expect(exportedPacks).toEqual([expected])
  expect(doc.presets.encoder[0]).not.toHaveProperty('name')
  expect(doc).not.toHaveProperty('settings')
  expect(doc).not.toHaveProperty('application')
  expect(errors).toEqual([])
})

test('imports selected presets additively and preserves local app settings', async ({ page }) => {
  const { bundle, importedPacks, errors } = await fixture(page)
  const pack = presetPack(bundle.presets)
  await page.getByRole('button', { name: 'Import presets…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import preset pack', exact: true })
  await dialog.locator('input[type=file]').setInputFiles({ name: 'group.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(pack)) })
  await expect(dialog).toContainText('Stereo → Stereo (2)')
  await dialog.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await dialog.getByRole('checkbox', { name: /Stereo/ }).check()
  await dialog.getByRole('button', { name: 'Import 1 selected', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(importedPacks).toEqual([{ ...pack, presets: { template: [], video: [], encoder: [], audio: pack.presets.audio } }])
  await expect(page.getByRole('spinbutton')).toHaveValue('2')
  await page.getByRole('button', { name: 'Export presets…', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Export preset pack', exact: true }).getByRole('checkbox', { name: /Stereo \(2\)/ })).toBeVisible()
  expect(errors).toEqual([])
})

test('preset sharing refuses a full configuration file', async ({ page }) => {
  const { bundle, importedPacks, errors } = await fixture(page)
  await page.getByRole('button', { name: 'Import presets…', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import preset pack', exact: true })
  await dialog.locator('input[type=file]').setInputFiles({ name: 'private-backup.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bundle)) })
  await expect(dialog.getByRole('alert')).toContainText('Choose a VideoForge preset pack')
  await expect(dialog.getByRole('button', { name: 'Import 0 selected', exact: true })).toBeDisabled()
  expect(importedPacks).toEqual([])
  expect(errors).toEqual([])
})
