import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, Profile, Template } from '../../src/lib/types.ts'

async function layoutFixture(page: Page) {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const template: Template = {
    video: { source_filter: 'ffms2', crop: { left: 0, top: 0, right: 0, bottom: 0 }, resize: null, filters: [], custom: null },
    encoder: { encoder: 'x264', rate_control: '2pass', crf: 18, bitrate_kbps: 8000, target_mb: null, preset: 'veryslow', tune: '', depth: 8, options: {}, extra: '', source_color: true, hdr10plus: false, dolby_vision: false },
    mux: { container: 'mkv', extra: '', pgs_zlib: false }, qpf: true, crop_mode: 'keep', audio: null, subs: null,
  }
  const profile: Profile = {
    id: 'manual', name: 'Manual', default: true, container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV (mkvmerge)', extension: '.mkv', tool: 'mkvmerge' }, { id: 'mp4', label: 'MP4 (MP4Box)', extension: '.mp4', tool: 'MP4Box' }],
    external_subtitles: true, track_editor: true, track_properties: [],
    defaults: { video: template.video, encoder: template.encoder, template },
  }
  const config: ConfigState = {
    tools: [{ name: 'ffmpeg', label: 'ffmpeg', purpose: 'Audio and video', folder: false, path: 'ffmpeg', default: 'ffmpeg', custom: null }],
    roots: ['D:\\Media'], roots_custom: false, default_roots: ['D:\\Media'], profile: 'manual', profile_default: 'manual', profiles: [profile], restart: [],
    index_waits_for_disk: true, parallel_audio: 2, parallel_audio_default: 2, delete_work_dir: false, delete_work_dir_default: false,
    encoder_priority: 'normal', encoder_priority_default: 'normal', tool_priority: 'normal', tool_priority_default: 'normal', priorities: ['normal'],
    records_dir: 'D:\\VideoForge\\records', notifications: [], notification_events: [], actions: [],
    action_kinds: [{ id: 'move', label: 'Move output' }, { id: 'copy', label: 'Copy output' }, { id: 'command', label: 'Run command' }, { id: 'webhook', label: 'Webhook' }], action_tokens: { job: {}, queue: {} }, allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  await page.addInitScript(() => localStorage.setItem('videoforge.mode', 'dark'))
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, unknown> = {
      '/api/jobs': [], '/api/profiles': [profile], '/api/health': { ok: true, version: 'test' },
      '/api/presets': { video: [], encoder: [], audio: [], template: [{ name: 'Hallowed 1080p CEL', data: template }], template_defaults: { manual: 'Hallowed 1080p CEL' }, encoder_starters: [] },
      '/api/filter-presets': [], '/api/config/encoders': [], '/api/config/video-options/x264': { dashes: '--', options: [] },
      '/api/settings': { output_dir: 'D:\\Output', last_dir: '' }, '/api/config': config, '/api/config/tools': [],
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected layout fixture request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  return errors
}

test('Templates saves optional PGS compression and only shows it for MKV', async ({ page }) => {
  const errors = await layoutFixture(page)
  let saved: Template | null = null
  await page.route('**/api/presets/template/*', async route => {
    saved = route.request().postDataJSON() as Template
    await route.fulfill({ json: { video: [], encoder: [], audio: [], template: [{ name: 'Hallowed 1080p CEL', data: saved }], template_defaults: {}, encoder_starters: [] } })
  })
  await page.goto('/#/templates')
  const compression = page.getByRole('checkbox', { name: 'Compress PGS subtitles with zlib' })
  await expect(compression).not.toBeChecked()
  await compression.check()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect.poll(() => saved?.mux.pgs_zlib).toBe(true)
  await page.getByRole('radio', { name: 'MP4 (MP4Box)', exact: true }).click()
  await expect(compression).toHaveCount(0)
  await page.getByRole('radio', { name: 'MKV (mkvmerge)', exact: true }).click()
  await expect(compression).toBeChecked()
  expect(errors).toEqual([])
})

for (const route of ['templates', 'settings']) {
  test(`${route} uses the available editor width on large windows`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1920, height: 1000 })
    const errors = await layoutFixture(page)
    await page.goto(`/#/${route}`)
    const content = route === 'templates' ? page.locator('fieldset').first() : page.getByRole('textbox', { name: 'ffmpeg path', exact: true }).locator('xpath=../../../..')
    await expect(content).toBeVisible()
    const bounds = await content.boundingBox()
    expect(bounds!.x + bounds!.width).toBeGreaterThan(1920 - 40)
    if (route === 'settings') {
      const indexing = await page.getByRole('heading', { name: 'Batch indexing', exact: true }).boundingBox()
      const audio = await page.getByRole('heading', { name: 'Audio encodes', exact: true }).boundingBox()
      expect(Math.abs(indexing!.y - audio!.y)).toBeLessThan(2)
      expect(audio!.x).toBeGreaterThan(1000)
    }
    await page.screenshot({ path: testInfo.outputPath(`${route}-wide.png`) })
    expect(errors).toEqual([])
  })
}

for (const width of [960, 800]) {
  test(`New jobs scrolls at ${width} CSS pixels without clipping its form`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 540 })
    const errors = await layoutFixture(page)
    await page.goto('/#/new')
    const output = page.getByRole('list', { name: 'Output folder', exact: true })
    await expect(output).toContainText('Output')
    const form = output.locator('xpath=../..')
    const formBounds = await form.boundingBox()
    const outputBounds = await output.boundingBox()
    expect(outputBounds!.y + outputBounds!.height).toBeLessThanOrEqual(formBounds!.y + formBounds!.height)
    await output.scrollIntoViewIfNeeded()
    await expect(output).toBeInViewport()
    const add = page.getByRole('button', { name: /Add.*to queue/ })
    await add.scrollIntoViewIfNeeded()
    await expect(add).toBeInViewport()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await page.screenshot({ path: testInfo.outputPath('new-jobs-short.png') })
    expect(errors).toEqual([])
  })
}

test('Templates stacks editor columns when zoom leaves insufficient panel width', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const columns = page.locator('fieldset').first()
  await expect(columns).toBeVisible()
  const children = columns.locator(':scope > *')
  const video = await children.nth(0).boundingBox()
  const output = await children.nth(1).boundingBox()
  expect(output!.y).toBeGreaterThanOrEqual(video!.y + video!.height)
  const extra = page.getByRole('textbox', { name: 'Extra muxer arguments', exact: true })
  await extra.scrollIntoViewIfNeeded()
  await expect(extra).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('templates-narrow.png') })
  expect(errors).toEqual([])
})
