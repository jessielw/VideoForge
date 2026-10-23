import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { AudioEncodeInfo, AudioPresetSettings, AudioTrack, ConfigState, EncoderSettings, JobDetail, Presets, Profile, Template } from '../../src/lib/types.ts'

const video: EncoderSettings = { encoder: 'x264', rate_control: 'crf', crf: 18, bitrate_kbps: 8000, target_mb: null,
  preset: 'slow', tune: '', depth: 8, options: {}, extra: '', source_color: true, hdr10plus: false, dolby_vision: false }
const audio: AudioPresetSettings = { action: 'ddp', layout: '5.1', bitrate_kbps: 640, options: {}, title: 'Surround' }
const copy: AudioPresetSettings = { action: 'copy', layout: null, bitrate_kbps: null, options: {}, title: null }
const variants = [
  { title: 'Audio', target: 'ddp', other: 'copy', label: 'Surround mix', codec: 'DDP (DEE)' },
  { title: 'Encoder', target: 'x265', other: 'x264', label: 'Film HEVC', codec: 'x265' },
] as const

async function fixture(page: Page, empty = false) {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const template: Template = {
    video: { source_filter: 'ffms2', crop: { left: 0, top: 0, right: 0, bottom: 0 }, resize: null, filters: [], custom: null },
    encoder: video, mux: { container: 'mkv', extra: '', pgs_zlib: false }, qpf: true, crop_mode: 'keep', subs: null,
    audio: { mode: 'position', slots: [{ track: { ...copy, title: null, language: null, exclude: null, flags: {} }, extra: [] }], rules: [], others: 'keep' },
  }
  const profile: Profile = { id: 'manual', name: 'Manual', default: true, container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }], external_subtitles: true,
    track_editor: true, track_properties: [], defaults: { video: template.video, encoder: video, template } }
  const enc: AudioEncodeInfo = { id: 'ddp', label: 'DDP (DEE)', codec: 'eac3', layouts: ['2.0', '5.1', '7.1'],
    bitrates: { '2': 256, '6': 640, '8': 1024 }, bitrate_choices: [], bitrate_range: null, per_channel_max: null,
    vbr_default: false, default_max: null, missing: [], options: [] }
  const source: AudioTrack = { key: 'id:1', id: 1, index: 0, codec: 'eac3', layout: '2.0', language: 'en', title: '',
    default: true, forced: false, hearing_impaired: false, visual_impaired: false, commentary: false,
    original: false, atmos: false, dtsx: false, bitrate_kbps: 224, delay_ms: 24, format_name: 'E-AC-3', detected: {},
    sample_rate: 48000, bit_depth: null, size_bytes: null, duration_ms: 61000, copy: 0 }
  const job: JobDetail = { id: 'presets', name: 'Preset browsing', label: '', source: 'D:/Show.mkv', profile: 'manual', status: 'ready',
    progress: null, issue: '', output: null, encoder: 'x264', crop: null, custom_script: false, indexed: false,
    index_error: '', index_held: false, audio: [], subs: 0, issues: [], steps: {},
    plan: { encode_path: null, resolution: '1080p', original_language: 'en', chapters_path: null,
      audio: [{ source, action: 'copy', out_codec: 'eac3', out_layout: '2.0', out_atmos: false, bitrate_kbps: 224,
        upmix_50: false, language: 'en', title: '', default: true, forced: false, hearing_impaired: false,
        visual_impaired: false, commentary: false, original: false, options: {}, sync_ms: 0 }],
      subs: [], burn: null, issues: [], profile: 'manual' },
    output_name: null, color_args: null, target: null,
    tracks: { video: null, audio: [source], subs: [], has_chapters: false, count: 1 },
    spec: { id: 'presets', profile: 'manual',
      inputs: { source: 'D:/Show.mkv', encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
      video: template.video, encoder: video, mux: template.mux,
      overrides: { original_language: null, audio_track_ids: null, tracks: {}, order: null, copies: [] },
      qpf: false, output_dir: null, output_policy: 'stop', autocrop: false, audio_template: null, subs_template: null,
      audio_from_template: null, subs_from_template: null, output_name: '', label: '' } }
  const presets: Presets = { video: [], encoder: empty ? [] : [
    { name: 'hevc', label: 'Film HEVC', group: [], data: { ...video, encoder: 'x265', crf: 20, depth: 10 } },
    { name: 'avc', label: 'Film AVC', group: [], data: { ...video, crf: 21 } },
    { name: 'nested-hevc', label: 'Compatibility', group: ['Home cinema', 'Surround'], data: { ...video, encoder: 'x265', crf: 22 } },
    { name: 'nested-avc', label: 'Compatibility', group: ['Home cinema', 'Surround'], data: { ...video, crf: 23 } },
  ], audio: empty ? [] : [
    { name: 'surround', label: 'Surround mix', group: [], data: audio },
    { name: 'nested-ddp', label: 'Compatibility', group: ['Home cinema', 'Surround'], data: audio },
    { name: 'nested-copy', label: 'Compatibility', group: ['Home cinema', 'Surround'], data: copy },
  ], template: [{ name: 'Current template', data: template }], template_defaults: { manual: 'Current template' }, encoder_starters: [] }
  const config: ConfigState = { tools: [], roots: [], roots_custom: false, default_roots: [], profile: 'manual', profile_default: 'manual',
    profiles: [profile], restart: [], index_waits_for_disk: true, parallel_audio: 2, parallel_audio_default: 2,
    delete_work_dir: false, delete_work_dir_default: false, encoder_priority: 'normal', encoder_priority_default: 'normal',
    tool_priority: 'normal', tool_priority_default: 'normal', priorities: ['normal'], records_dir: 'D:/records',
    notifications: [], notification_events: [], actions: [], action_kinds: [], action_tokens: { job: {}, queue: {} }, allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] } }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, unknown> = { '/api/jobs': [job], '/api/jobs/presets': job, '/api/profiles': [profile], '/api/presets': presets,
      '/api/health': { ok: true, version: 'test' }, '/api/filter-presets': [], '/api/config/encoders': [enc],
      '/api/config/video-options/x264': { dashes: '--', options: [] }, '/api/config/video-options/x265': { dashes: '--', options: [] },
      '/api/config': config, '/api/config/tools': [], '/api/settings': { output_dir: 'D:/Output', last_dir: '' },
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] } }
    if (!(path in responses)) throw new Error(`Unexpected preset browsing request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/templates')
  return errors
}

for (const { title, target, other, label, codec } of variants) {
  test(`${title}: saved presets and folders open above built-ins across encoders`, async ({ page }, testInfo) => {
    const errors = await fixture(page)
    const trigger = page.getByRole('button', { name: `${title} presets`, exact: true })
    await trigger.click()
    const menu = page.locator('[data-slot="popover-content"]')
    await expect(menu.getByRole('combobox')).toHaveValue('')
    await expect(menu.getByRole('button', { name: 'Home cinema', exact: true })).toBeVisible()
    const saved = menu.getByRole('region', { name: 'My presets', exact: true })
    await expect(saved.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    const headings = await menu.getByRole('heading').allTextContents()
    expect(headings).toEqual(['My presets', 'Built-in'])
    await saved.getByRole('button', { name: new RegExp(label) }).click()
    await expect(menu).toHaveCount(0)
    if (title === 'Audio') {
      await expect(page.getByRole('group', { name: 'Audio track 1', exact: true }).getByRole('combobox', { name: 'Copy or encode' })).toHaveValue(target)
    } else {
      await expect(page.getByRole('radio', { name: 'x265', exact: true })).toBeChecked()
      await expect(page.getByRole('spinbutton', { name: 'CRF', exact: true })).toHaveValue('20')
    }
    await trigger.click()
    await expect(menu.getByRole('combobox')).toHaveValue('')
    await expect(menu.getByRole('button', { name: 'Home cinema', exact: true })).toBeVisible()
    await expect(menu.getByRole('button', { name: new RegExp(label) })).toHaveAttribute('aria-current', 'true')
    await page.screenshot({ path: testInfo.outputPath(`${title.toLowerCase()}-preset-picker.png`), animations: 'disabled' })
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
    expect(errors).toEqual([])
  })

  test(`${title}: search crosses folders and encoders, with optional filtering and clear empty states`, async ({ page }) => {
    const errors = await fixture(page)
    await page.getByRole('button', { name: `${title} presets`, exact: true }).click()
    const menu = page.locator('[data-slot="popover-content"]')
    const search = menu.getByRole('textbox')
    const filter = menu.getByRole('combobox')
    await search.fill('Compatibility')
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toHaveCount(2)
    await expect(menu.getByRole('button', { name: /Compatibility/ }).first()).toContainText('Home cinema / Surround')
    await filter.selectOption(target)
    await expect(search).toHaveValue('Compatibility')
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toHaveCount(1)
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toContainText(codec)
    await filter.selectOption(other)
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toHaveCount(1)
    await filter.selectOption('')
    await search.fill('Home cinema')
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toHaveCount(2)
    await search.fill(codec)
    await expect(menu.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    await search.fill('no-such-preset')
    await expect(menu.getByRole('status')).toHaveText('No presets match your search.')
    await search.clear()
    await menu.getByRole('button', { name: 'Home cinema', exact: true }).click()
    await menu.getByRole('button', { name: 'Surround', exact: true }).click()
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toHaveCount(2)
    await expect(menu.getByRole('region', { name: 'Built-in presets', exact: true })).toHaveCount(0)
    await search.fill(label)
    await expect(menu.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    await search.clear()
    await expect(menu.getByRole('button', { name: /Compatibility/ })).toHaveCount(2)
    await menu.getByRole('navigation', { name: 'Preset folders' }).getByRole('button', { name: 'My presets', exact: true }).click()
    await expect(menu.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    expect(errors).toEqual([])
  })

  test(`${title}: manager starts at the root and retains the browsing context while selecting`, async ({ page }) => {
    const errors = await fixture(page)
    await page.getByRole('button', { name: `${title} presets`, exact: true }).click()
    await page.getByRole('button', { name: 'Manage presets…', exact: true }).click()
    const manager = page.getByRole('dialog', { name: `${title} presets`, exact: true })
    const filter = manager.getByRole('combobox', { name: `Filter ${title.toLowerCase()} presets by encoder` })
    await expect(filter).toHaveValue('')
    await expect(manager.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    await manager.getByRole('button', { name: 'Home cinema', exact: true }).click()
    await manager.getByRole('button', { name: 'Surround', exact: true }).click()
    await manager.getByRole('button', { name: /Compatibility/ }).filter({ hasText: codec }).click()
    await expect(filter).toHaveValue('')
    await expect(manager.getByRole('button', { name: /Compatibility/ })).toHaveCount(2)
    const search = manager.getByRole('textbox', { name: `Search ${title.toLowerCase()} presets` })
    await search.fill(label)
    await manager.getByRole('button', { name: new RegExp(label) }).click()
    await expect(search).toHaveValue(label)
    await expect(filter).toHaveValue('')
    await search.clear()
    await expect(manager.getByRole('button', { name: /Compatibility/ })).toHaveCount(2)
    expect(errors).toEqual([])
  })

  test(`${title}: Settings library uses the same top-level organization`, async ({ page }) => {
    const errors = await fixture(page)
    await page.goto('/#/settings')
    await page.getByRole('button', { name: title === 'Audio' ? 'Manage audio presets' : 'Manage video encoder presets', exact: true }).click()
    const manager = page.getByRole('dialog', { name: `${title} presets`, exact: true })
    await expect(manager.getByRole('combobox', { name: `Filter ${title.toLowerCase()} presets by encoder` })).toHaveValue('')
    await expect(manager.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    await expect(manager.getByRole('button', { name: 'Home cinema', exact: true })).toBeVisible()
    expect(errors).toEqual([])
  })
}

test('empty custom libraries omit My presets and keep built-ins available', async ({ page }) => {
  const errors = await fixture(page, true)
  for (const { title } of variants) {
    await page.getByRole('button', { name: `${title} presets`, exact: true }).click()
    const menu = page.locator('[data-slot="popover-content"]')
    await expect(menu.getByRole('heading', { name: 'My presets', exact: true })).toHaveCount(0)
    await expect(menu.getByRole('heading', { name: 'Built-in', exact: true })).toBeVisible()
    if (title === 'Encoder') {
      await menu.getByRole('combobox').selectOption('vp9')
      await expect(menu.getByRole('status')).toHaveText('No presets for this encoder.')
      await menu.getByRole('combobox').selectOption('')
      await expect(menu.getByRole('heading', { name: 'Built-in', exact: true })).toBeVisible()
    }
    await page.keyboard.press('Escape')
  }
  expect(errors).toEqual([])
})

test('audio preset picker reflows at 400px and supports keyboard access without accessibility violations', async ({ page }, testInfo) => {
  const errors = await fixture(page)
  await page.setViewportSize({ width: 400, height: 700 })
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await page.getByRole('button', { name: 'Audio presets', exact: true }).click()
  const menu = page.locator('[data-slot="popover-content"]')
  await expect(menu.getByRole('textbox')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(menu.getByRole('combobox')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(menu.getByRole('button', { name: 'Home cinema', exact: true })).toBeFocused()
  const bounds = await menu.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(8)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(392)
  expect(await menu.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('audio-preset-picker-narrow.png'), animations: 'disabled' })
  const accessibility = await new AxeBuilder({ page }).include('[data-slot="popover-content"]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
  expect(accessibility.violations).toEqual([])
  expect(errors).toEqual([])
})

test('New jobs can apply a preset for a different video encoder directly', async ({ page }) => {
  const errors = await fixture(page)
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Encoder presets', exact: true }).click()
  await page.getByRole('button', { name: /Film HEVC/ }).click()
  await expect(page.getByRole('button', { name: 'Encoder presets', exact: true })).toContainText('Film HEVC')
  expect(errors).toEqual([])
})

test('job audio shows saved presets from Copy and keeps incompatible choices disabled with reasons', async ({ page }, testInfo) => {
  const errors = await fixture(page)
  await page.goto('/#/queue/presets')
  await page.getByRole('tab', { name: 'Audio', exact: true }).click()
  await page.getByRole('button', { name: 'Audio presets', exact: true }).click()
  const menu = page.locator('[data-slot="popover-content"]')
  await expect(menu.getByRole('combobox')).toHaveValue('')
  const surround = menu.getByRole('button', { name: /Surround mix/ })
  await expect(surround).toBeDisabled()
  await expect(surround).toContainText('5.1 requires more channels than this 2.0 source')
  await expect(menu.getByRole('button', { name: /2.0 256 kb\/s/ })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('job-audio-preset-picker.png'), animations: 'disabled' })
  await menu.getByRole('button', { name: 'Manage presets…', exact: true }).click()
  const manager = page.getByRole('dialog', { name: 'Audio presets', exact: true })
  await manager.getByRole('button', { name: /Surround mix/ }).click()
  await expect(manager.getByRole('button', { name: 'Apply to this output', exact: true })).toBeDisabled()
  await expect(manager.getByRole('textbox', { name: 'Audio preset name' })).toHaveValue('Surround mix')
  expect(errors).toEqual([])
})
