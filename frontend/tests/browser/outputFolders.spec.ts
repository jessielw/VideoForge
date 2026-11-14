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
  color_override: false,
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
    mux: {
      container: 'mkv',
      extra: '',
      pgs_zlib: false,
      name_template: '',
      template_file_name: false,
      template_title: false,
      name_suffix: '',
    },
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
    naming: {},
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
    data_dir: 'D:/VideoForge',
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

// Settings › Files & folders: the same saved folders, managed outside the New jobs menu. Answers GET from `current`
// and records each PUT, so a test can change what the next load sees.
async function settingsList(page: Page, folders: { path: string; pinned: boolean }[]) {
  const errors = await fixture(page, folders)
  const state = { current: folders, saved: [] as unknown[] }
  await page.route('**/api/settings', async (route) => {
    const empty = { output_dir: '', last_dir: '' }
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON()
      state.saved.push(body)
      state.current = body.output_folders
      await route.fulfill({ json: { ...empty, ...body } })
    } else await route.fulfill({ json: { ...empty, output_folders: state.current, output_default: '' } })
  })
  await page.goto('/#/settings')
  await page.getByRole('button', { name: 'Files & folders', exact: true }).click()
  return { errors, state, section: page.getByRole('region', { name: 'Saved output folders' }) }
}

test('Files & folders lists saved folders and pins, stars and forgets them', async ({ page }) => {
  const { errors, state, section } = await settingsList(page, [folder(1, true), folder(2)])
  await expect(section.getByRole('listitem')).toHaveText([/show-1/, /show-2/])
  await section.getByRole('button', { name: 'Make D:/Out/show-1 the default' }).click()
  await expect
    .poll(() => state.saved.at(-1))
    .toEqual({ output_folders: [folder(1, true), folder(2)], output_default: 'D:/Out/show-1' })
  await section.getByRole('button', { name: 'Pin D:/Out/show-2' }).click()
  await expect
    .poll(() => state.saved.at(-1))
    .toEqual({ output_folders: [folder(1, true), folder(2, true)], output_default: 'D:/Out/show-1' })
  await section.getByRole('button', { name: 'Forget D:/Out/show-1' }).click()
  await expect.poll(() => state.saved.at(-1)).toEqual({ output_folders: [folder(2, true)], output_default: '' })
  await expect(section.getByRole('listitem')).toHaveText([/show-2/])
  expect(errors).toEqual([])
})

test('Files & folders keeps keyboard focus with the folder through pin, unpin and forget', async ({ page }) => {
  const { errors, section } = await settingsList(page, [folder(1, true), folder(2)])
  await section.getByRole('button', { name: 'Pin D:/Out/show-2' }).press('Enter')
  await expect(section.getByRole('button', { name: 'Unpin D:/Out/show-2' })).toBeFocused()
  await section.getByRole('button', { name: 'Unpin D:/Out/show-2' }).press('Enter')
  await expect(section.getByRole('button', { name: 'Pin D:/Out/show-2' })).toBeFocused()
  await section.getByRole('button', { name: 'Forget D:/Out/show-1' }).press('Enter')
  await expect(section.getByRole('button', { name: 'Forget D:/Out/show-2' })).toBeFocused()
  await section.getByRole('button', { name: 'Forget D:/Out/show-2' }).press('Enter')
  await expect(section.getByRole('heading', { name: 'Saved output folders' })).toBeFocused()
  expect(errors).toEqual([])
})

test('Files & folders says when nothing is saved yet', async ({ page }) => {
  const { errors, section } = await settingsList(page, [])
  await expect(section).toContainText('No saved output folders yet. Each output folder you use for a job appears here.')
  await expect(section.getByRole('list')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('Files & folders explains the list, and says when a change is not saved', async ({ page }) => {
  const { errors, section } = await settingsList(page, [folder(1, true), folder(2)])
  await expect(section).toContainText(
    "Output folders you've sent jobs to are listed here, newest first. Pinned ones stay; only the 10 newest unpinned ones are kept. The default fills in New jobs' output folder.",
  )
  await page.route('**/api/settings', (route) =>
    route.request().method() === 'PUT'
      ? route.fulfill({ status: 500, json: { detail: 'disk full' } })
      : route.fallback(),
  )
  await section.getByRole('button', { name: 'Pin D:/Out/show-2' }).click()
  await expect(page.getByText("Couldn't save the output folders")).toBeVisible()
  await expect(section.getByRole('button', { name: 'Pin D:/Out/show-2' })).toBeVisible() // unchanged
  expect(errors).toEqual([])
})

test("reopening Files & folders shows the active profile's folders", async ({ page }) => {
  const { errors, state, section } = await settingsList(page, [folder(1)])
  await expect(section.getByRole('listitem')).toHaveText([/show-1/])
  state.current = [folder(9)] // as after switching to another profile
  await page.getByRole('button', { name: 'Profiles', exact: true }).click()
  await page.getByRole('button', { name: 'Files & folders', exact: true }).click()
  await expect(section.getByRole('listitem')).toHaveText([/show-9/])
  expect(errors).toEqual([])
})

test('a long saved folder wraps inside Files & folders at 320 px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const long = { path: 'D:\\Some\\Very\\Long\\Folder\\Name\\That\\Keeps\\Going\\And\\Going\\Out', pinned: true }
  const { errors, section } = await settingsList(page, [long])
  await expect(section.getByRole('listitem')).toHaveCount(1)
  const { scroll, client } = await section.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }))
  expect(scroll).toBeLessThanOrEqual(client)
  expect(errors).toEqual([])
})
