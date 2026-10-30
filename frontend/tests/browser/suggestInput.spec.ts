import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, EncoderSettings, Presets, Profile, Template } from '../../src/lib/types.ts'

const video: EncoderSettings = {
  encoder: 'x264',
  rate_control: '2pass',
  crf: 18,
  bitrate_kbps: 8000,
  target_mb: 5000,
  preset: 'slow',
  tune: '',
  depth: 8,
  options: { ref: '4' },
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
  const presets: Presets = {
    video: [],
    encoder: [],
    audio: [],
    template: [{ name: 'Sized', data: template }],
    template_defaults: { manual: 'Sized' },
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
  const options = [
    { name: 'ref', help: 'Reference frames' },
    { name: 'bframes', help: 'Consecutive B-frames' },
    { name: 'rc-lookahead', help: 'Frames for the lookahead' },
  ]
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
      '/api/config/video-options/x264': { dashes: '--', options },
      '/api/config': config,
      '/api/config/tools': [],
      '/api/settings': { output_dir: 'D:/Output', last_dir: '' },
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected suggestion request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/templates')
  return errors
}

test("target sizes and option names suggest from the app's own list", async ({ page }, testInfo) => {
  const errors = await fixture(page)
  await expect(page.locator('datalist')).toHaveCount(0)

  const size = page.getByRole('combobox', { name: 'Target size' })
  await size.click()
  const list = page.getByRole('listbox')
  await expect(list.getByRole('option')).toHaveCount(4)
  await page.screenshot({ path: testInfo.outputPath('target-sizes.png'), animations: 'disabled' })
  await list.getByRole('option', { name: /25000\s*BD$/ }).click()
  await expect(size).toHaveValue('25000')
  await expect(page.getByText('Unsaved changes')).toBeVisible()

  const name = page.getByRole('combobox', { name: 'New option name' })
  await expect(name).toHaveAttribute('autocomplete', 'off')
  await name.fill('fram') // by name, then by help text
  await expect(list.getByRole('option')).toHaveCount(3)
  await expect(list.getByRole('option').first()).toContainText('bframes')
  await name.press('ArrowDown')
  await name.press('Enter') // takes the suggestion; adds nothing yet
  await expect(name).toHaveValue('bframes')
  await page.getByRole('textbox', { name: 'New option value' }).fill('8')
  await page.getByRole('textbox', { name: 'New option value' }).press('Enter')
  await expect(page.getByRole('combobox', { name: 'Option name', exact: true })).toHaveCount(2)
  await expect(page.getByRole('textbox', { name: '--bframes value' })).toHaveValue('8')

  await name.fill('rc-lookahead') // nothing picked out: Enter adds the row as typed
  await name.press('Enter')
  await expect(page.getByRole('combobox', { name: 'Option name', exact: true })).toHaveCount(3)

  const first = page.getByRole('combobox', { name: 'Option name', exact: true }).first() // rename a row by picking
  await first.fill('look')
  await expect(page.getByRole('listbox')).toHaveCount(1)
  await list.getByRole('option', { name: /rc-lookahead/ }).click()
  await expect(page.getByRole('textbox', { name: '--rc-lookahead value' })).toHaveCount(1)
  expect(errors).toEqual([])
})
