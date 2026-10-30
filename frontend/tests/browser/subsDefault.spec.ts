import { test, expect } from '@playwright/test'
import type { ConfigState, Presets, Profile, Template, TemplateSubs } from '../../src/lib/types.ts'

test('Settings: default subtitle rules save as they change, naming included, and turn off', async ({ page }) => {
  const errors: string[] = []
  const saves: (TemplateSubs | null)[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const template: Template = {
    video: {
      source_filter: 'ffms2',
      crop: { left: 0, top: 0, right: 0, bottom: 0 },
      resize: null,
      filters: [],
      custom: null,
    },
    encoder: {
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
    },
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
    defaults: { video: template.video, encoder: template.encoder, template },
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
    sample_quality: false,
    parallel_audio: 2,
    parallel_audio_default: 2,
    delete_work_dir: false,
    delete_work_dir_default: false,
    encoder_priority: 'normal',
    encoder_priority_default: 'normal',
    tool_priority: 'normal',
    tool_priority_default: 'normal',
    priorities: ['normal'],
    records_dir: 'D:\\records',
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  const presets: Presets = {
    video: [],
    encoder: [],
    audio: [],
    template: [],
    template_defaults: {},
    encoder_starters: [],
    subs_default: null,
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/presets/subs-default') {
      presets.subs_default = request.postDataJSON()
      saves.push(structuredClone(presets.subs_default ?? null))
      return route.fulfill({ json: presets })
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [],
      '/api/profiles': [profile],
      '/api/presets': presets,
      '/api/health': { ok: true, version: 'test' },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config': config,
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
      '/api/config/tools': [],
    }
    if (!(path in responses)) throw new Error(`Unexpected default subtitles request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/settings')
  const section = page.getByRole('region', { name: 'Default subtitles' })
  await expect(section).toContainText('new jobs keep every subtitle track')

  await section.getByRole('checkbox', { name: "Choose every new job's subtitles by rules" }).click()
  await expect.poll(() => saves.length).toBe(1)
  const languages = section.getByRole('combobox', { name: 'Rule 1: languages' })
  await languages.fill('eng')
  await languages.press('Enter')
  await expect.poll(() => saves.at(-1)?.rules[0].languages).toEqual(['en'])
  await section.getByRole('checkbox', { name: 'Name untitled tracks' }).click()
  await expect.poll(() => saves.at(-1)?.name_untitled).toBe(true)
  await expect(section.getByRole('combobox', { name: 'Rule 1: languages' }).locator('..')).toContainText('English')

  await section.getByRole('checkbox', { name: "Choose every new job's subtitles by rules" }).click()
  await expect.poll(() => saves.at(-1)).toBeNull()
  expect(errors).toEqual([])
})
