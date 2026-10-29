import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, EncoderSettings, Presets, Profile, Template } from '../../src/lib/types.ts'

const video: EncoderSettings = {
  encoder: 'x264',
  rate_control: 'crf',
  crf: 18,
  bitrate_kbps: 8000,
  target_mb: null,
  preset: 'slow',
  tune: '',
  depth: 8,
  options: {},
  extra: '',
  source_color: true,
  hdr10plus: false,
  dolby_vision: false,
}

async function fixture(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const template: Template = {
    video: {
      source_filter: 'ffms2',
      crop: { left: 0, top: 0, right: 0, bottom: 0 },
      resize: null,
      filters: [],
      custom: null,
    },
    encoder: video,
    mux: { container: 'mkv', extra: '', pgs_zlib: false },
    qpf: true,
    crop_mode: 'keep',
    audio: null,
    subs: null,
  }
  const profile: Profile = {
    id: 'manual',
    name: 'Manual',
    default: true,
    container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }],
    external_subtitles: true,
    track_editor: true,
    track_properties: [],
    defaults: { video: template.video, encoder: video, template },
  }
  const names = ['Loose', 'Group / 1080p / Film', 'Group / 1080p / Grain', 'Group / 2160p / Film']
  const presets: Presets = {
    video: [],
    encoder: [],
    audio: [],
    template: names.map((name) => ({ name, data: template })),
    template_defaults: { manual: 'Group / 1080p / Film' },
    encoder_starters: [],
  }
  const config: ConfigState = {
    tools: [],
    roots: [],
    roots_custom: false,
    default_roots: [],
    profile: 'manual',
    profile_default: 'manual',
    profiles: [profile],
    restart: [],
    index_waits_for_disk: true,
    parallel_audio: 2,
    parallel_audio_default: 2,
    delete_work_dir: false,
    delete_work_dir_default: false,
    encoder_priority: 'normal',
    encoder_priority_default: 'normal',
    tool_priority: 'normal',
    tool_priority_default: 'normal',
    priorities: ['normal'],
    records_dir: 'D:/records',
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  const calls: string[] = []
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = decodeURIComponent(url.pathname)
    if (route.request().method() !== 'GET') {
      calls.push(`${route.request().method()} ${path}`)
      if (path.startsWith('/api/presets/template/') && path.endsWith('/rename')) {
        const from = path.slice('/api/presets/template/'.length, -'/rename'.length)
        const to = (route.request().postDataJSON() as { to: string }).to
        presets.template = presets.template.map((t) => (t.name === from ? { ...t, name: to } : t))
      }
      return route.fulfill({ json: presets })
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [],
      '/api/profiles': [profile],
      '/api/presets': presets,
      '/api/health': { ok: true, version: 'test' },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config/video-options/x264': { dashes: '--', options: [] },
      '/api/config': config,
      '/api/config/tools': [],
      '/api/settings': { output_dir: 'D:/Output', last_dir: '' },
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected template folders request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/templates')
  return { errors, calls }
}

test('templates show as a folder tree; the folder box moves one', async ({ page }, testInfo) => {
  const { errors, calls } = await fixture(page)
  const list = page.getByRole('list', { name: 'Templates' })
  await expect(list.getByRole('button', { name: /^Group\s*3$/ })).toHaveAttribute('aria-expanded', 'true')
  await expect(list.getByRole('button', { name: /^1080p\s*2$/ })).toBeVisible()
  // the starred one opens: its folder and label in two boxes
  await expect(page.getByRole('textbox', { name: 'Template folder' })).toHaveValue('Group / 1080p')
  await expect(page.getByRole('textbox', { name: 'Template name' })).toHaveValue('Film')
  await page.screenshot({ path: testInfo.outputPath('template-tree.png'), animations: 'disabled' })

  await list.getByRole('button', { name: /^1080p\s*2$/ }).click()
  await expect(list.getByRole('button', { name: 'Grain', exact: true })).toHaveCount(0)
  await list.getByRole('button', { name: /^1080p\s*2$/ }).click()
  await expect(list.getByRole('button', { name: 'Grain', exact: true })).toBeVisible()

  await page.getByRole('textbox', { name: 'Template folder' }).fill('Group/Archive')
  await expect(page.getByText('Unsaved changes')).toBeVisible()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect.poll(() => calls).toContain('POST /api/presets/template/Group / 1080p / Film/rename')
  await expect(page.getByRole('textbox', { name: 'Template folder' })).toHaveValue('Group / Archive')
  await expect(list.getByRole('button', { name: /^Archive\s*1$/ })).toBeVisible()
  expect(errors).toEqual([])
})
