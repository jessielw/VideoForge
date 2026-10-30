import { test, expect, type Page, type WebSocketRoute } from '@playwright/test'
import type { JobDetail, JobSummary, Status } from '../../src/lib/types.ts'

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })

const LONG = 'The.Very.Long.Show.Name.S01E01.Pilot.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-GROUP'

async function phoneFixture(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const statuses: Status[] = ['running', 'queued', 'failed', 'ready']
  const jobs: JobSummary[] = statuses.map((status, i) => ({
    id: `job-${i}`,
    name: i === 0 ? LONG : `Show S01E0${i + 1}`,
    label: '',
    source: `D:\\Media\\Show\\Season 01\\Show.S01E0${i + 1}.mkv`,
    profile: 'manual',
    status,
    progress:
      status === 'running'
        ? {
            step: 'Encode video (x265)',
            index: 2,
            total: 5,
            fraction: 0.42,
            overall: 0.51,
            reused: false,
            fps: 23.4,
            eta: 1840,
            elapsed: 3600,
            left: 2900,
          }
        : null,
    issue: status === 'failed' ? 'x265 exited with code 1' : '',
    output: null,
    encoder: 'x265',
    crop: null,
    custom_script: false,
    indexed: true,
    index_error: '',
    index_held: false,
    sample_waiting: false,
    sample_error: '',
    audio: [],
    subs: 0,
  }))
  const detail = (job: JobSummary): JobDetail => ({
    ...job,
    issues: [],
    steps: {},
    plan: null,
    tracks: null,
    output_name: null,
    color_args: null,
    target: null,
    sample: null,
    compare: { encode: false, sample: false },
    spec: {
      id: job.id,
      profile: 'manual',
      inputs: { source: job.source, encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
      video: {
        source_filter: 'ffms2',
        crop: { left: 0, top: 0, right: 0, bottom: 0 },
        resize: null,
        filters: [],
        custom: null,
      },
      encoder: {
        encoder: 'x265',
        rate_control: 'crf',
        crf: 18,
        bitrate_kbps: 0,
        target_mb: null,
        preset: 'medium',
        tune: '',
        depth: 10,
        options: {},
        extra: '',
        source_color: true,
        hdr10plus: false,
        dolby_vision: false,
      },
      mux: { container: 'mkv', extra: '', pgs_zlib: false },
      overrides: { original_language: null, audio_track_ids: null, tracks: {}, order: null, copies: [] },
      qpf: false,
      output_dir: null,
      output_policy: 'stop',
      autocrop: false,
      audio_template: null,
      subs_template: null,
      audio_from_template: null,
      subs_from_template: null,
      output_name: '',
      label: '',
    },
  })
  let socket!: WebSocketRoute
  await page.routeWebSocket('**/api/events', (ws) => {
    socket = ws
  })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let json: unknown
    if (path === '/api/jobs') json = jobs
    else if (path === '/api/health') json = { ok: true, version: 'test' }
    else if (path === '/api/presets')
      json = { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] }
    else if (/^\/api\/jobs\/job-\d+$/.test(path)) json = detail(jobs.find((job) => job.id === path.split('/')[3])!)
    else if (/^\/api\/jobs\/job-\d+\/log-snapshot$/.test(path)) json = { seq: 0, steps: [], lines: [] }
    else if (path === '/api/config/video-options/x265') json = { dashes: '--', options: [] }
    else if (['/api/profiles', '/api/config/encoders', '/api/filter-presets'].includes(path)) json = []
    else return route.fulfill({ status: 404, json: { detail: `not mocked: ${path}` } })
    await route.fulfill({ json })
  })
  return { errors, socket: () => socket }
}

const pageScrolls = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)

test('a phone shows the queue or a job, with a bar back to the list', async ({ page }) => {
  const { errors } = await phoneFixture(page)
  await page.goto('/#/queue')
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await expect(list.locator('[data-job]')).toHaveCount(4)
  await expect(page.getByRole('region', { name: 'Job settings', exact: true })).toBeHidden()
  expect(await pageScrolls(page)).toBe(false)

  // A running job opens on its log, the whole width: no rail beside it.
  await list.locator('[data-job="job-0"]').click()
  await expect(page.getByRole('heading', { name: LONG })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Log', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tab', { name: 'Log', exact: true })).toBeInViewport()
  await expect(page.getByRole('region', { name: 'Queue rail', exact: true })).toHaveCount(0)
  expect(await pageScrolls(page)).toBe(false)

  // The bar opens the list over the page; picking a job closes it. A ready job opens on Video.
  await page.getByRole('button', { name: 'Show the queue list', exact: true }).click()
  await expect(list).toBeInViewport()
  await list.locator('[data-job="job-3"]').click()
  await expect(list).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Show S01E04' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Video', exact: true })).toHaveAttribute('aria-selected', 'true')
  expect(await pageScrolls(page)).toBe(false)
  expect(errors).toEqual([])
})

test('a phone wraps the log instead of scrolling it sideways', async ({ page }) => {
  const { errors, socket } = await phoneFixture(page)
  await page.goto('/#/queue')
  await expect(page.locator('[data-job]')).toHaveCount(4)
  socket().send(
    JSON.stringify({
      type: 'log',
      id: 'job-0',
      step: null,
      seq: 1,
      line: 'x265 [error]: unknown option --very-long-option-name=with-a-value-that-does-not-wrap-anywhere',
    }),
  )
  await page.getByRole('button', { name: 'Log', exact: true }).click()
  const box = page.locator('pre')
  await expect(box).toContainText('unknown option')
  expect(await box.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  expect(await pageScrolls(page)).toBe(false)
  expect(errors).toEqual([])
})
