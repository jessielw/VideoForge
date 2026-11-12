import { test, expect } from '@playwright/test'
import type { ConfigState, Presets, ProfileList, Template } from '../../src/lib/types.ts'

test('Settings: profiles are created, renamed, switched to and deleted', async ({ page }) => {
  const errors: string[] = []
  const calls: { method: string; path: string; body: unknown }[] = []
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
      color_override: false,
      hdr10plus: false,
      dolby_vision: false,
    },
    mux: { container: 'mkv', extra: '', pgs_zlib: false },
    qpf: true,
    crop_mode: 'keep',
    audio: null,
    subs: null,
  }
  const ruleSet = {
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
  const config = (parallel_audio: number): ConfigState => ({
    tools: [],
    roots: [],
    roots_custom: false,
    default_roots: [],
    rule_set: 'manual',
    rule_set_default: 'manual',
    rule_sets: [ruleSet],
    restart: [],
    index_waits_for_disk: true,
    index_during_video: true,
    sample_quality: false,
    auto_index: true,
    auto_crop: true,
    parallel_audio,
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
  })
  const presets: Presets = {
    video: [],
    encoder: [],
    audio: [],
    template: [],
    template_defaults: {},
    encoder_starters: [],
  }
  // The first profile has 4 audio encodes at once; a new one starts at the default 2
  const parallel: Record<string, number> = { default: 4 }
  const profiles: ProfileList = { profiles: [{ id: 'default', name: 'Default' }], active: 'default' }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const method = request.method()
    const path = new URL(request.url()).pathname
    const body = request.postDataJSON()
    if (path.startsWith('/api/profiles') && method !== 'GET') calls.push({ method, path, body })
    if (path === '/api/profiles' && method === 'POST') {
      if (profiles.profiles.some((p) => p.name.toLowerCase() === body.name.trim().toLowerCase()))
        return route.fulfill({ status: 422, json: { detail: 'A profile with that name already exists' } })
      const id = `p${profiles.profiles.length}`
      profiles.profiles.push({ id, name: body.name.trim() })
      parallel[id] = body.copy ? parallel[profiles.active] : 2
      return route.fulfill({ json: profiles })
    }
    const one = path.match(/^\/api\/profiles\/([^/]+)(\/activate)?$/)
    if (one) {
      const profile = profiles.profiles.find((p) => p.id === one[1])!
      if (one[2]) profiles.active = profile.id
      else if (method === 'PATCH') profile.name = body.name
      else if (method === 'DELETE') profiles.profiles = profiles.profiles.filter((p) => p !== profile)
      const reply = one[2] ? { ...profiles, config: config(parallel[profile.id]), presets } : profiles
      return route.fulfill({ json: reply })
    }
    const responses: Record<string, unknown> = {
      '/api/preset-packs/managed': { presets: [], problems: [] },
      '/api/jobs': [],
      '/api/rule-sets': [ruleSet],
      '/api/presets': presets,
      '/api/health': { ok: true, version: 'test' },
      '/api/profiles': profiles,
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config': config(parallel[profiles.active]),
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
      '/api/config/tools': [],
    }
    if (!(path in responses)) throw new Error(`Unexpected profiles request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/settings')
  const section = page.getByRole('region', { name: 'Profiles' })
  const audio = page.getByRole('spinbutton').first()
  await expect(section.getByRole('listitem')).toHaveText([/^Default\s*\(active\)\s*Rename…\s*$/])
  await page.getByRole('button', { name: 'Encoding', exact: true }).click()
  await expect(audio).toHaveValue('4')
  await page.getByRole('button', { name: 'General', exact: true }).click()

  await section.getByRole('button', { name: 'New profile…' }).click()
  let dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Name' }).fill('default')
  await dialog.getByRole('button', { name: 'Create' }).click()
  await expect(dialog.getByRole('alert')).toHaveText('A profile with that name already exists')
  await dialog.getByRole('textbox', { name: 'Name' }).fill('Anime')
  await dialog.getByRole('textbox', { name: 'Name' }).press('Enter')
  await expect(dialog).toBeHidden()
  await expect(section.getByRole('listitem').nth(1)).toContainText('Anime')
  expect(calls.at(-1)).toEqual({ method: 'POST', path: '/api/profiles', body: { name: 'Anime', copy: false } })

  await section.getByRole('listitem').nth(1).getByRole('button', { name: 'Switch' }).click()
  await expect(section.getByRole('listitem').nth(1)).toHaveText(/^Anime\s*\(active\)/)
  await page.getByRole('button', { name: 'Encoding', exact: true }).click()
  await expect(audio).toHaveValue('2') // the new profile's settings are in use
  await page.getByRole('button', { name: 'General', exact: true }).click()
  // the active one can't be deleted; the other one can
  await expect(section.getByRole('listitem').nth(1).getByRole('button', { name: 'Delete…' })).toHaveCount(0)

  await section.getByRole('listitem').nth(1).getByRole('button', { name: 'Rename…' }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Name' }).fill('Anime 1080p')
  await dialog.getByRole('button', { name: 'Rename' }).click()
  await expect(section.getByRole('listitem').nth(1)).toHaveText(/^Anime 1080p\s*\(active\)/)

  await section.getByRole('listitem').first().getByRole('button', { name: 'Delete…' }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('Delete Default?')
  await dialog.getByRole('button', { name: 'Delete' }).click()
  await expect(section.getByRole('listitem')).toHaveText([/^Anime 1080p\s*\(active\)\s*Rename…\s*$/])
  expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
    'POST /api/profiles',
    'POST /api/profiles',
    'POST /api/profiles/p1/activate',
    'PATCH /api/profiles/p1',
    'DELETE /api/profiles/default',
  ])
  expect(errors).toEqual([])
})
