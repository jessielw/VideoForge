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

async function fixture(page: Page, posted: Record<string, unknown>[]) {
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
  const sources = ['D:/Media/Show.S01E01.mkv', 'D:/Media/Show.S01E02.mkv']
  const job = (source: string) => ({
    source,
    encode: null,
    encode_state: null,
    subtitles: [],
    chapters: null,
    existing_id: null,
    existing_status: null,
  })
  const folders = ['D:/Media/Old'] // what the folder picker lists in D:/Media
  const removed: Record<string, unknown>[] = []
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const request = route.request()
    if (path === '/api/fs/list')
      return route.fulfill({
        json: { path: 'D:/Media', parent: 'D:/', dirs: folders.map((p) => ({ name: p.slice(9), path: p })), files: [] },
      })
    if (path === '/api/fs/mkdir') {
      const made = `D:/Media/${request.postDataJSON().name}`
      folders.push(made)
      return route.fulfill({ json: { path: made } })
    }
    if (path === '/api/fs/rmdir') {
      removed.push(request.postDataJSON())
      folders.splice(folders.indexOf(request.postDataJSON().path), 1)
      return route.fulfill({ json: { path: request.postDataJSON().path } })
    }
    if (path === '/api/fs/kinds')
      return route.fulfill({
        json: (request.postDataJSON().paths as string[]).map((p) => ({ path: p, kind: 'file' })),
      })
    if (path === '/api/match')
      return route.fulfill({
        json: { jobs: (request.postDataJSON().sources as string[]).map(job), unmatched: [] },
      })
    if (path === '/api/jobs' && request.method() === 'POST') {
      posted.push(request.postDataJSON())
      return route.fulfill({ json: { added: ['a', 'b'], skipped: [], unmatched: [], kept: [] } })
    }
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
      '/api/settings': { output_dir: 'D:/Output', last_dir: '' },
      '/api/fs/roots': ['D:/'],
    }
    if (!(path in responses)) throw new Error(`Unexpected request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/queue')
  return { errors, sources, removed }
}

async function paste(page: Page, text: string) {
  await page.evaluate((t) => {
    const data = new DataTransfer()
    data.setData('text/plain', t)
    document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }))
  }, text)
}

test('pasted paths land on New jobs; the bottom bar says what Add will do and then offers the queue', async ({
  page,
}) => {
  const posted: Record<string, unknown>[] = []
  const { errors, sources } = await fixture(page, posted)

  await paste(page, 'just some words') // ordinary text is left alone
  await expect(page).toHaveURL(/#\/queue/)

  await paste(page, sources.map((p) => `"${p}"`).join(String.fromCharCode(13, 10))) // from any page
  await expect(page).toHaveURL(/#\/new/)
  await expect(page.getByText('Show.S01E02.mkv')).toBeVisible()
  const tops = await page.evaluate(() => [
    document.querySelector('nav')!.lastElementChild!.getBoundingClientRect().top,
    document.querySelector('footer[aria-label="Add to queue"]')!.getBoundingClientRect().top,
  ])
  expect(tops[1]).toBe(tops[0]) // the bar's top line meets the nav's status block's
  const bar = page.locator('footer[aria-label="Add to queue"]')
  await expect(bar).toContainText('2 jobs · Sized · will index and auto-crop · saved to D:/Output')

  await page.getByRole('checkbox', { name: 'Auto-crop' }).click()
  await expect(bar).toContainText('will index ·')
  await page.getByRole('checkbox', { name: 'Index', exact: true }).click()
  await expect(bar).toContainText('will neither index nor crop')
  await bar.getByRole('button', { name: /Add 2 jobs/ }).click()

  await expect(bar.getByRole('status')).toContainText('Added 2 jobs')
  await expect(bar.getByRole('button', { name: 'Open queue' })).toBeVisible()
  expect(posted).toHaveLength(1)
  expect(posted[0]).toMatchObject({ auto_index: false, auto_crop: false, output_dir: 'D:/Output', rule_set: 'manual' })
  expect(posted[0].sources).toEqual(sources)

  await bar.getByRole('button', { name: 'Add more' }).click() // a clean form for the next batch
  await expect(bar).toContainText('Paste file paths anywhere')
  await expect(page.getByText('Show.S01E02.mkv')).toHaveCount(0)

  await paste(page, sources[0])
  await bar.getByRole('button', { name: /Add 1 job to queue/ }).click()
  await bar.getByRole('button', { name: 'Open queue' }).click()
  await expect(page).toHaveURL(/#\/queue/)
  expect(errors).toEqual([])
})

test('the folder picker offers Delete only on a folder made in it, and asks to delete only an empty one', async ({
  page,
}) => {
  const { errors, removed } = await fixture(page, [])
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Browse…' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  await expect(picker.getByRole('button', { name: 'Old', exact: true })).toBeVisible()
  await expect(picker.getByRole('button', { name: 'Delete Old' })).toHaveCount(0) // not made here

  await picker.getByRole('button', { name: 'New folder' }).click()
  await picker.getByRole('textbox', { name: 'New folder name' }).fill('Oops')
  await picker.getByRole('button', { name: 'Create' }).click()
  await picker.getByRole('button', { name: 'Delete Oops' }).click()

  const confirm = page.getByRole('dialog', { name: 'Delete Oops?' })
  await expect(confirm).toContainText("It's empty, so no files are deleted.")
  await confirm.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(picker.getByRole('button', { name: 'Oops', exact: true })).toHaveCount(0)
  expect(removed).toEqual([{ path: 'D:/Media/Oops' }])
  expect(errors).toEqual([])
})
