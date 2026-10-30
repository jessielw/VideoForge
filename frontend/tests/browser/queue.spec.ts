import { test, expect, type Page, type WebSocketRoute } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { JobDetail, JobSummary, Status } from '../../src/lib/types.ts'

async function queueFixture(page: Page, count = 10_000, statuses: Status[] = ['ready', 'done']) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const jobs: JobSummary[] = Array.from({ length: count }, (_, i) => ({
    id: `job-${i}`,
    name: `Episode ${String(i).padStart(5, '0')}`,
    label: '',
    source: `D:\\Show\\Season${i < count / 2 ? 1 : 2}\\${i}.mkv`,
    profile: 'manual',
    status: statuses[i % statuses.length],
    progress: null,
    issue: '',
    output: null,
    encoder: 'x265',
    crop: null,
    custom_script: false,
    indexed: false,
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
  const calls: { path: string; body: { ids?: string[] } }[] = []
  let socket: WebSocketRoute
  await page.routeWebSocket('**/api/events', (ws) => {
    socket = ws
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') calls.push({ path, body: request.postDataJSON() })
    let json: unknown
    if (path === '/api/jobs') json = jobs
    else if (path === '/api/health') json = { ok: true, version: 'test' }
    else if (path === '/api/presets')
      json = { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] }
    else if (path === '/api/queue/reuse') json = { jobs: [] }
    else if (path === '/api/config/video-options/x265') json = { dashes: '--', options: [] }
    else if (path === '/api/jobs/reorder') json = { ids: request.postDataJSON().ids }
    else if (/^\/api\/jobs\/job-\d+$/.test(path)) json = detail(jobs.find((job) => job.id === path.split('/').at(-1))!)
    else if (path === '/api/queue/start') json = {}
    else if (path === '/api/queue/enqueue') json = { enqueued: request.postDataJSON().ids }
    else if (['/api/profiles', '/api/config/encoders', '/api/filter-presets'].includes(path)) json = []
    else throw new Error(`Unhandled queue fixture request: ${request.method()} ${path}`)
    await route.fulfill({ json })
  })
  await page.goto('/#/queue')
  await expect(page.getByRole('status')).toContainText(`${count} of ${count} jobs match`)
  return { jobs, calls, errors, refresh: () => socket.send(JSON.stringify({ type: 'job', id: jobs[0].id })) }
}

test('10,000 jobs: bounded rows, combined filters, counts, and explicit action scope', async ({ page }) => {
  const { calls, errors } = await queueFixture(page)
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await expect(list.locator('[data-job]')).toHaveCount(100)
  await page.getByRole('searchbox').fill('SEASON2 episode')
  await page.getByRole('combobox', { name: 'Filter jobs by status' }).selectOption('ready')
  await expect(page.getByRole('status')).toContainText('2500 of 10000 jobs match')
  await page.getByRole('button', { name: 'Select matching jobs', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('2500 selected')
  await page.getByRole('searchbox').fill('no matches')
  await expect(page.getByRole('status')).toContainText('2500 hidden by filters')
  await page.getByRole('button', { name: 'Move selected jobs up', exact: true }).click()
  await expect.poll(() => calls.find((call) => call.path === '/api/jobs/reorder')?.body.ids?.length).toBe(10000)
  const order = calls.find((call) => call.path === '/api/jobs/reorder')!.body.ids!
  expect(new Set(order).size).toBe(10000)
  expect(order.slice(4999, 5001)).toEqual(['job-5000', 'job-4999'])
  await page.getByRole('button', { name: 'Run selected (2500)', exact: true }).click()
  await expect.poll(() => calls.find((call) => call.path === '/api/queue/start')?.body.ids?.length).toBe(2500)
  expect(calls.find((call) => call.path === '/api/queue/start')!.body.ids).toEqual(
    Array.from({ length: 2500 }, (_, i) => `job-${5000 + i * 2}`),
  )
  await page.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Run selected (0)', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).first().click()
  // Nothing queued: Start queue has nothing to run; a tick (or Queue on a selection) queues jobs.
  await expect(page.getByRole('button', { name: 'Start queue (0)', exact: true })).toBeDisabled()
  await page.getByRole('checkbox', { name: 'Queued: Episode 00000', exact: true }).click()
  await expect.poll(() => calls.find((call) => call.path === '/api/queue/enqueue')?.body.ids).toEqual(['job-0'])
  await expect(page.locator('[data-job="job-0"]')).toHaveAttribute('aria-pressed', 'false') // a tick doesn't select
  await page.getByRole('button', { name: 'Select matching jobs', exact: true }).click()
  await page.getByRole('button', { name: 'Queue (10000)', exact: true }).click()
  await expect
    .poll(() => calls.filter((call) => call.path === '/api/queue/enqueue').at(-1)?.body.ids?.length)
    .toBe(10000)
  expect(errors).toEqual([])
})

test('keyboard focus crosses pages, ranges follow matches, and live status changes keep selection visible', async ({
  page,
}) => {
  const fixture = await queueFixture(page, 205)
  await page.locator('[data-job="job-0"]').press('End')
  await expect(page.locator('[data-job="job-204"]')).toBeFocused()
  await page.locator('[data-job="job-204"]').press('Home')
  await expect(page.locator('[data-job="job-0"]')).toBeFocused()
  await page.getByRole('button', { name: 'Next queue page', exact: true }).click()
  await expect(page.locator('[data-job="job-100"]')).toBeFocused()
  await page.locator('[data-job="job-100"]').press('Enter')
  await page.locator('[data-job="job-100"]').press('Shift+ArrowUp')
  await expect(page.locator('[data-job="job-99"]')).toBeFocused()
  await expect(page.getByRole('status')).toContainText('2 selected')
  await page.locator('[data-job="job-99"]').press('ControlOrMeta+a')
  await expect(page.getByRole('status')).toContainText('205 selected')
  await page.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await page.getByRole('combobox', { name: 'Filter jobs by status' }).selectOption('ready')
  await page.locator('[data-job="job-0"]').press('Enter')
  fixture.jobs[0].status = 'done'
  fixture.refresh()
  await expect(page.getByRole('status')).toContainText('1 selected (1 hidden by filters)')
  await expect(page.locator('[data-job="job-2"]')).toBeFocused()
  await page.locator('[data-job="job-2"]').press('Shift+ArrowDown')
  await expect(page.locator('[data-job="job-4"]')).toBeFocused()
  await expect(page.getByRole('status')).toContainText('1 selected.')
  expect(fixture.errors).toEqual([])
})

test('deep links reveal jobs beyond page one; shrinking a live result clamps its page', async ({ page }) => {
  const fixture = await queueFixture(page, 205)
  await page.goto('/#/queue/job-204')
  await expect(page.locator('[data-job="job-204"]')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Showing 201–205 of 205', { exact: true })).toBeVisible()
  fixture.jobs.splice(100)
  fixture.refresh()
  await expect(page.getByRole('status')).toContainText('100 of 100 jobs match. 0 selected')
  await expect(page.getByText('Showing 1–100 of 100', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Next queue page', exact: true })).toBeDisabled()
  expect(fixture.errors).toEqual([])
})

test('narrow list and rail preserve focus; Escape restores the opener', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 800, height: 450 })
  const { errors } = await queueFixture(page, 205)
  await page.locator('[data-job="job-0"]').press('Enter')
  await expect(
    page.getByRole('region', { name: 'Queue rail', exact: true }).locator('[data-job="job-0"]'),
  ).toBeFocused()
  await page.getByRole('button', { name: 'Show the queue list', exact: true }).click()
  await expect(page.getByRole('searchbox')).toBeFocused()
  await page.screenshot({ path: testInfo.outputPath('queue-800.png') })
  await expect(page.getByRole('region', { name: 'Job settings', exact: true })).toHaveAttribute('inert', '')
  await page.getByRole('searchbox').press('Escape')
  await expect(page.getByRole('button', { name: 'Show the queue list', exact: true })).toBeFocused()
  await page.getByRole('button', { name: 'Show the queue list', exact: true }).press('Enter')
  await page.getByRole('searchbox').fill('episode 00101')
  await expect(page.getByRole('status')).toContainText('1 of 205 jobs match')
  await page.getByRole('region', { name: 'Queue list', exact: true }).locator('[data-job="job-101"]').press('Enter')
  await expect(
    page.getByRole('region', { name: 'Queue rail', exact: true }).locator('[data-job="job-101"]'),
  ).toBeFocused()
  expect(errors).toEqual([])
})

test('320 CSS pixel reflow keeps queue controls reachable without horizontal scrolling', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 256 })
  const { errors } = await queueFixture(page, 205)
  await page.getByRole('searchbox').fill('episode 00002')
  await expect(page.getByRole('status')).toContainText('1 of 205 jobs match')
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  expect(overflow).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('queue-320.png') })
  await page.getByRole('button', { name: 'Select matching jobs', exact: true }).click()
  await page.getByRole('button', { name: 'Show the queue list', exact: true }).click()
  await page.getByRole('button', { name: 'Clear selection', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('0 selected')
  await expect(page.getByRole('searchbox')).toBeFocused()
  expect(errors).toEqual([])
})

for (const theme of ['light', 'dark']) {
  test(`queue controls and every status pass automated WCAG AA checks in ${theme} mode`, async ({ page }) => {
    await page.addInitScript((theme) => localStorage.setItem('videoforge.mode', theme), theme)
    await queueFixture(page, 205, [
      'ready',
      'warn',
      'blocked',
      'queued',
      'running',
      'done',
      'invalid',
      'failed',
      'skipped',
      'cancelled',
      'indexing',
      'index-queued',
      'probing',
      'error',
      'cropping',
    ])
    const list = page.getByRole('region', { name: 'Queue list', exact: true })
    await expect(list.locator('[data-job][tabindex="0"]')).toHaveCount(1)
    await page.locator('[data-job="job-0"]').press('Enter')
    await expect(page.locator('[data-job="job-0"]')).toHaveAttribute('aria-pressed', 'true')
    await page.locator('[data-job="job-0"]').press('Tab')
    await expect(page.getByRole('button', { name: 'Next queue page', exact: true })).toBeFocused()
    const results = await new AxeBuilder({ page })
      .include('section[aria-label="Queue list"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze()
    expect(results.violations).toEqual([])
  })
}
