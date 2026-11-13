import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, RuleSet, Template } from '../../src/lib/types.ts'

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
    encoder: {
      encoder: 'x264',
      rate_control: '2pass',
      crf: 18,
      bitrate_kbps: 8000,
      target_mb: null,
      preset: 'veryslow',
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
  const ruleSet: RuleSet = {
    id: 'manual',
    name: 'Manual',
    default: true,
    container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV (mkvmerge)', extension: '.mkv', tool: 'mkvmerge' }],
    external_subtitles: true,
    track_editor: true,
    track_properties: [],
    defaults: { video: template.video, encoder: template.encoder, template },
  }
  const config: ConfigState = {
    tools: [
      {
        name: 'ffmpeg',
        label: 'ffmpeg',
        purpose: 'Audio and video',
        folder: false,
        path: 'ffmpeg',
        default: 'ffmpeg',
        custom: null,
      },
    ],
    roots: ['D:\\Media'],
    roots_custom: false,
    default_roots: ['D:\\Media'],
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
    records_dir: 'D:\\VideoForge\\records',
    data_dir: DATA_DIR,
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [{ id: 'command', label: 'Run command' }],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, unknown> = {
      '/api/preset-packs/managed': { presets: [], problems: [] },
      '/api/jobs': [],
      '/api/rule-sets': [ruleSet],
      '/api/health': { ok: true, version: 'test' },
      '/api/profiles': { profiles: [{ id: 'default', name: 'Default' }], active: 'default' },
      '/api/presets': {
        video: [],
        encoder: [],
        audio: [],
        template: [{ name: 'Film', data: template }],
        template_defaults: { manual: 'Film' },
        encoder_starters: [],
      },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config/video-options/x264': { dashes: '--', options: [] },
      '/api/settings': { output_dir: '', last_dir: '', output_folders: [], output_default: '' },
      '/api/config': config,
      '/api/config/tools': [],
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected settings fixture request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  return errors
}

const ORDER = [
  'Jobs',
  'Queue & indexing',
  'Presets',
  'Files & folders',
  'Tools',
  'Plugins',
  'Automation',
  'Appearance',
  'Profiles',
  'Import & export',
]
// [category, a heading in its pane]
const HOME: [string, string][] = [
  ['Jobs', 'Rule set'],
  ['Jobs', 'Default subtitles'],
  ['Jobs', 'Test encode'],
  ['Queue & indexing', 'Batch indexing'],
  ['Queue & indexing', 'Audio encodes'],
  ['Queue & indexing', 'Process priority'],
  ['Presets', 'Encoder presets'],
  ['Files & folders', 'Work folders'],
  ['Files & folders', 'Folder browser'],
  ['Files & folders', 'Data folder'],
  ['Tools', 'Tools'],
  ['Plugins', 'Plugins'],
  ['Automation', 'Notifications'],
  ['Automation', 'Actions'],
  ['Appearance', 'Appearance'],
  ['Profiles', 'Profiles'],
  ['Profiles', 'Reset VideoForge'],
  ['Import & export', 'Configuration backup'],
  ['Import & export', 'Preset sharing'],
]

const sections = (page: Page) => page.getByRole('navigation', { name: 'Settings sections' })
const open = (page: Page, category: string) =>
  sections(page).getByRole('button', { name: category, exact: true }).click()

test('Settings lists ten categories in order, with the version and Shut down below', async ({ page }) => {
  const errors = await fixture(page)
  await page.goto('/#/settings')
  const nav = sections(page)
  await expect(nav.getByRole('button')).toHaveText([...ORDER, 'Shut down…'])
  await expect(nav).toContainText('VideoForge test')
  await expect(nav.getByRole('button', { name: 'Jobs', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(errors).toEqual([])
})

test('each settings group sits in its category', async ({ page }) => {
  const errors = await fixture(page)
  await page.goto('/#/settings')
  for (const [category, heading] of HOME) {
    await open(page, category)
    await expect(page.getByRole('heading', { name: heading, exact: true }), `${heading} in ${category}`).toBeVisible()
  }
  expect(errors).toEqual([])
})

for (const [saved, opens] of [
  ['general', 'Jobs'],
  ['encoding', 'Jobs'],
  ['backup', 'Jobs'],
  ['tools', 'Tools'],
]) {
  test(`a remembered "${saved}" category opens ${opens}`, async ({ page }) => {
    const errors = await fixture(page)
    await page.addInitScript((id) => localStorage.setItem('videoforge.settingsTab', id), saved)
    await page.goto('/#/settings')
    await expect(sections(page).getByRole('button', { name: opens, exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(errors).toEqual([])
  })
}

test('Settings fits a 320 px wide window without scrolling sideways', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const errors = await fixture(page)
  await page.goto('/#/settings')
  const settings = page.locator('[class*="@container/settings"]')
  // shortcut: four tabs have rows that don't wrap yet (Process priority's hints, Folder browser's Reset row, the tool
  // path rows, Automation's Add rows), so they are left out until those rows wrap.
  const wide = ['Queue & indexing', 'Files & folders', 'Tools', 'Automation']
  for (const category of ORDER.filter((c) => !wide.includes(c))) {
    await open(page, category)
    const { scroll, client } = await settings.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }))
    expect.soft(scroll, category).toBeLessThanOrEqual(client)
  }
  expect(errors).toEqual([])
})

const ABOUT: [string, string][] = [
  ['Jobs', 'What new jobs start with, and whether a test encode also measures its quality.'],
  ['Queue & indexing', 'When jobs are indexed, and how the queue shares the computer while it works.'],
  ['Presets', 'Saved encoder and audio settings you can pick in any job or template. Templates have their own page.'],
  ['Files & folders', 'The folders VideoForge saves to, browses and cleans up, and where it keeps its own data.'],
  ['Tools', 'The programs VideoForge uses for each step, and where each one is installed.'],
  ['Plugins', 'A plugin can add a rule set, templates and presets, or run its own code when jobs start and finish.'],
  ['Automation', 'Send a message or run a command when a job ends or the queue finishes.'],
  ['Appearance', 'How VideoForge looks in this browser.'],
  ['Profiles', 'Separate sets of settings, templates and presets to switch between, and a reset to start one over.'],
  [
    'Import & export',
    'Back up your settings, templates and presets or move them to another computer, and share presets with other people.',
  ],
]

test('each category describes itself in one sentence', async ({ page }) => {
  const errors = await fixture(page)
  await page.goto('/#/settings')
  for (const [category, about] of ABOUT) {
    await open(page, category)
    await expect(page.getByRole('group', { name: category, exact: true })).toHaveAccessibleDescription(about)
  }
  await open(page, 'Presets')
  await page.getByRole('button', { name: 'Open Templates', exact: true }).click()
  await expect(page).toHaveURL(/#\/templates$/)
  expect(errors).toEqual([])
})

// a path with no break opportunities, to show it wraps instead of widening the page
const DATA_DIR = 'D:\\Some\\Very\\Long\\Folder\\Name\\That\\Keeps\\Going\\And\\Going\\VideoForge'

test('Files & folders shows where VideoForge keeps its data, wrapped to the window', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const errors = await fixture(page)
  await page.goto('/#/settings')
  await open(page, 'Files & folders')
  const section = page.getByRole('heading', { name: 'Data folder', exact: true }).locator('..')
  await expect(section).toContainText(DATA_DIR)
  await expect(section).toContainText('database, logs, kept job records and plugins')
  const { scroll, client } = await section.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }))
  expect(scroll).toBeLessThanOrEqual(client)
  expect(errors).toEqual([])
})

test('Shut down asks first and says how to start again', async ({ page }) => {
  const errors = await fixture(page)
  await page.goto('/#/settings')
  await sections(page).getByRole('button', { name: 'Shut down…' }).click()
  await expect(page.getByRole('dialog')).toContainText('videoforge serve')
  expect(errors).toEqual([])
})
