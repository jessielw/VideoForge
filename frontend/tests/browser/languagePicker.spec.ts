import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, EncoderSettings, Presets, Profile, Template, TrackOverride } from '../../src/lib/types.ts'

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
const keep: TrackOverride = {
  exclude: null,
  language: null,
  title: null,
  flags: {},
  action: null,
  bitrate_kbps: null,
  layout: null,
  options: {},
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
    subs: {
      rules: [{ languages: ['en'], formats: [], forced: null, hearing_impaired: null, commentary: null, track: keep }],
      others: 'keep',
    },
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
  const presets: Presets = {
    video: [],
    encoder: [],
    audio: [],
    template: [{ name: 'Subs', data: template }],
    template_defaults: { manual: 'Subs' },
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
    records_dir: 'D:/records',
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
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
    if (!(path in responses)) throw new Error(`Unexpected language picker request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/templates')
  return errors
}

test('rule languages: pick from the list, type a name or a tag, chips come off', async ({ page }, testInfo) => {
  const errors = await fixture(page)
  const box = page.getByRole('combobox', { name: 'Rule 1: languages' })
  await expect(box).toHaveAttribute('autocomplete', 'off')
  const field = box.locator('..')
  await expect(field).toContainText('English')

  await box.click()
  const list = page.getByRole('listbox')
  await expect(list.getByRole('option', { name: /English/ }).first()).toHaveAttribute('aria-selected', 'true')
  await box.fill('jap')
  await expect(list.getByRole('option')).toHaveCount(1)
  await page.screenshot({ path: testInfo.outputPath('language-picker-open.png'), animations: 'disabled' })
  await box.press('Enter')
  await expect(field).toContainText('Japanese')
  await expect(box).toHaveValue('')

  await box.fill('pt-PT') // not listed: offered as typed
  await expect(list.getByRole('option', { name: /pt-PT/ })).toBeVisible()
  await box.press('Enter')
  await expect(field.getByRole('button', { name: /Remove/ })).toHaveCount(3)

  await box.press('Backspace')
  await expect(field.getByRole('button', { name: /Remove/ })).toHaveCount(2)
  await field.getByRole('button', { name: 'Remove English' }).click()
  await expect(field).not.toContainText('English')
  await expect(page.getByText('Unsaved changes')).toBeVisible()

  await box.fill('German') // a whole name, then away: taken on blur
  await page.getByRole('textbox', { name: 'Template name' }).click()
  await expect(field).toContainText('German')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  expect(errors).toEqual([])
})
