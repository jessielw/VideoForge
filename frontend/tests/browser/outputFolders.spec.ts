import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, EncoderSettings, Presets, RuleSet, Template } from '../../src/lib/types.ts'

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

async function fixture(page: Page, folders: { path: string; pinned: boolean }[]) {
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
  const ruleSet: RuleSet = {
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
    rule_set: 'manual',
    rule_set_default: 'manual',
    rule_sets: [ruleSet],
    restart: [],
    index_waits_for_disk: true,
    index_during_video: true,
    sample_quality: false,
    auto_index: true,
    auto_crop: true,
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
      '/api/rule-sets': [ruleSet],
      '/api/presets': presets,
      '/api/health': { ok: true, version: 'test' },
      '/api/profiles': { profiles: [{ id: 'default', name: 'Default' }], active: 'default' },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config': config,
      '/api/config/tools': [],
      '/api/settings': { output_dir: '', last_dir: '', output_folders: folders, output_default: '' },
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected output folder request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/new')
  return errors
}

const folder = (n: number, pinned = false) => ({ path: `D:/Out/show-${n}`, pinned })

test('a few saved folders show no filter box, and picking one fills the output folder', async ({ page }) => {
  const errors = await fixture(page, [folder(1, true), folder(2), folder(3)])
  await page.getByRole('button', { name: 'Saved output folders' }).click()
  await expect(page.getByRole('textbox', { name: 'Filter saved folders' })).toHaveCount(0)
  await page.getByRole('menuitem', { name: /show-2/ }).click()
  await expect(page.getByRole('list', { name: 'Output folder' })).toContainText('show-2')
  expect(errors).toEqual([])
})

test('a long list gets a filter box that narrows it and keeps typing inside it', async ({ page }, testInfo) => {
  const errors = await fixture(page, [folder(1, true), ...Array.from({ length: 9 }, (_, i) => folder(i + 2))])
  await page.getByRole('button', { name: 'Saved output folders' }).click()
  const filter = page.getByRole('textbox', { name: 'Filter saved folders' })
  await expect(page.getByRole('menuitem')).toHaveCount(10)
  await filter.fill('show-1') // show-1 and show-10
  await expect(filter).toBeFocused()
  await expect(page.getByRole('menuitem')).toHaveCount(2)
  await page.screenshot({ path: testInfo.outputPath('filtered.png'), animations: 'disabled' })
  await filter.fill('nothing')
  await expect(page.getByText('No saved folder matches.')).toBeVisible()
  expect(errors).toEqual([])
})
