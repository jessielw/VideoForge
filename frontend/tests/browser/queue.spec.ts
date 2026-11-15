import { test, expect, type Locator, type Page, type WebSocketRoute } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { JobDetail, JobSummary, Status, Template } from '../../src/lib/types.ts'

async function queueFixture(
  page: Page,
  count = 10_000,
  statuses: Status[] = ['ready', 'done'],
  sample: JobDetail['sample'] = null,
  search: JobDetail['search'] = null,
  made: JobDetail['made'] = null,
  facts: (i: number) => JobSummary['source_facts'] = () => null,
) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const jobs: JobSummary[] = Array.from({ length: count }, (_, i) => ({
    id: `job-${i}`,
    name: `Episode ${String(i).padStart(5, '0')}`,
    label: '',
    source: `D:\\Show\\Season${i < count / 2 ? 1 : 2}\\${i}.mkv`,
    rule_set: 'manual',
    status: statuses[i % statuses.length],
    progress: null,
    issue: '',
    output: null,
    encoder: 'x265',
    crop: null,
    custom_script: false,
    pause_after_pass1: false,
    indexed: false,
    source_facts: facts(i),
    index_error: '',
    index_held: false,
    sample_waiting: false,
    sample_error: '',
    searching: false,
    search_error: '',
    audio: [],
    subs: 0,
  }))
  const detail = (job: JobSummary): JobDetail => ({
    ...job,
    issues: [],
    steps: {},
    made,
    plan: null,
    tracks: null,
    output_name: null,
    output_title: null,
    color_args: null,
    target: null,
    sample,
    search,
    compare: { encode: false, sample: !!sample, filters: false },
    spec: {
      id: job.id,
      rule_set: 'manual',
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
        color_override: false,
        hdr10plus: false,
        dolby_vision: false,
      },
      mux: {
        container: 'mkv',
        extra: '',
        pgs_zlib: false,
        name_template: '',
        template_file_name: false,
        template_title: false,
        name_suffix: '',
      },
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
  const calls: { path: string; body: { ids?: string[]; [key: string]: unknown } }[] = []
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
    else if (path === '/api/profiles') json = { profiles: [{ id: 'default', name: 'Default' }], active: 'default' }
    else if (path === '/api/presets')
      json = { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] }
    else if (path === '/api/queue/reuse') json = { jobs: [] }
    else if (path === '/api/config/video-options/x265') json = { dashes: '--', options: [] }
    else if (path === '/api/jobs/reorder') json = { ids: request.postDataJSON().ids }
    else if (/^\/api\/jobs\/job-\d+$/.test(path)) json = detail(jobs.find((job) => job.id === path.split('/').at(-1))!)
    else if (path === '/api/queue/start') json = {}
    else if (path === '/api/queue/enqueue') json = { enqueued: request.postDataJSON().ids }
    else if (['/api/rule-sets', '/api/config/encoders', '/api/filter-presets'].includes(path)) json = []
    else if (path === '/api/settings') json = { output_dir: '', last_dir: '' }
    else if (path === '/api/fs/roots') json = ['D:\\']
    else if (path === '/api/fs/list')
      json = {
        path: 'D:\\Show',
        parent: 'D:\\',
        dirs: [{ name: '1.mkv_tmp', path: 'D:\\Show\\1.mkv_tmp' }],
        files: [{ name: 'videoforge-job.json', path: 'D:\\Show\\videoforge-job.json', size: 900 }],
      }
    else if (path === '/api/fs/kinds')
      json = (request.postDataJSON().paths as string[]).map((p) => ({
        path: p,
        kind: p.endsWith('_tmp') ? 'folder' : 'file',
      }))
    else if (path === '/api/jobs/import') json = { added: [], skipped: [] }
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

test('job files to add are pasted or browsed for on the server, and checked as they go in', async ({ page }) => {
  const { calls, errors } = await queueFixture(page, 3)
  await page.getByRole('button', { name: 'Add jobs from job files', exact: true }).click()
  const add = page.getByRole('button', { name: 'Add jobs', exact: true })
  await expect(add).toBeDisabled()
  const slot = page.getByRole('dialog', { name: 'Add jobs from job files' }).getByRole('group', { name: 'Job files' })
  await slot.evaluate((el) => {
    const data = new DataTransfer()
    data.setData('text/plain', ['"D:\\Show\\1.mkv_tmp"', 'D:\\Show\\notes.txt'].join(String.fromCharCode(13, 10)))
    el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }))
  })
  await expect(page.getByText('notes.txt: not .json')).toBeVisible() // checked on the way in
  const list = page.getByRole('dialog', { name: 'Add jobs from job files' }).getByRole('list', { name: 'Job files' })
  await expect(list.getByRole('listitem')).toHaveText(['1.mkv_tmp\\'])
  await page.getByRole('button', { name: 'Browse…', exact: true }).click()
  const browser = page.getByRole('dialog', { name: 'Job files', exact: true })
  await browser.getByRole('checkbox', { name: 'Pick 1.mkv_tmp' }).click() // already listed: not added twice
  await browser.getByText('videoforge-job.json').click()
  await browser.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(browser).toBeHidden()
  await expect(list.getByRole('listitem')).toHaveText(['1.mkv_tmp\\', 'videoforge-job.json'])
  await add.click()
  await expect
    .poll(() => calls.find((call) => call.path === '/api/jobs/import')?.body.paths)
    .toEqual(['D:\\Show\\1.mkv_tmp', 'D:\\Show\\videoforge-job.json'])
  expect(errors).toEqual([])
})

test('the tab title follows the running job', async ({ page }) => {
  const fixture = await queueFixture(page, 3, ['ready'])
  await expect(page).toHaveTitle('VideoForge')
  fixture.jobs[1].status = 'running'
  fixture.jobs[1].progress = {
    step: 'Encode video (x265)',
    index: 2,
    total: 5,
    fraction: 0.5,
    overall: 0.426,
    reused: false,
    fps: 24,
    eta: 600,
    elapsed: 900,
    left: 1200,
  }
  fixture.refresh()
  await expect(page).toHaveTitle('job 42% · Episode 00001 · VideoForge')
  fixture.jobs[1].status = 'done'
  fixture.jobs[1].progress = null
  fixture.refresh()
  await expect(page).toHaveTitle('VideoForge')
  expect(fixture.errors).toEqual([])
})

test('? opens the keyboard shortcuts, but not while typing', async ({ page }, testInfo) => {
  const fixture = await queueFixture(page, 3, ['ready'])
  const sheet = page.getByRole('dialog', { name: 'Keyboard shortcuts' })
  await page.getByRole('searchbox').press('?')
  await expect(page.getByRole('searchbox')).toHaveValue('?')
  await expect(sheet).toBeHidden()
  await page.getByRole('searchbox').fill('')
  await page.locator('[data-job="job-0"]').press('?')
  await expect(sheet).toBeVisible()
  await expect(sheet.getByRole('region', { name: 'Frame preview (click it first)' })).toContainText(
    'Save the frame as a PNG',
  )
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([])
  await sheet.screenshot({ path: testInfo.outputPath('shortcuts.png') })
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
  await page.getByRole('button', { name: 'Keyboard shortcuts', exact: true }).click()
  await expect(sheet).toBeVisible()
  expect(fixture.errors).toEqual([])
})

test('a done job says what its run made', async ({ page }) => {
  const made = { output_bytes: 4.5 * 1024 ** 3, source_bytes: 18 * 1024 ** 3, seconds: 5025, reused: 2, kbps: 6120 }
  const fixture = await queueFixture(page, 1, ['done'], null, null, made)
  await page.goto('/#/queue/job-0')
  await expect(page.getByText('Made 4.5 GB', { exact: false })).toContainText(
    '25.0% of the source · 6,120 kb/s · took 1:23:45 (2 reused)',
  )
  expect(fixture.errors).toEqual([])
})

test('a test encode shows its quality score only when it has one', async ({ page }, testInfo) => {
  const result: NonNullable<JobDetail['sample']> = {
    percent: 5,
    cycle: 960,
    length: 48,
    frames: 144,
    total_frames: 2400,
    fps: 23.976,
    bytes: 300_000,
    seconds: 12,
    encoder: 'x265 crf 18',
    finished: '2026-10-30T12:00:00',
    kbps: 4000,
    estimate_mb: 50,
    estimate_seconds: 200,
    encode_fps: 12,
    ssimulacra2: 82.43,
    ssimulacra2_p5: 74.08,
    xpsnr: 44.12,
    current: true,
    file: 'D:\\Show\\0.mkv_tmp\\sample\\sample.mkv',
  }
  const fixture = await queueFixture(page, 1, ['ready'], result)
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const card = page.getByRole('region', { name: 'Test encode', exact: true })
  await expect(card).toContainText('4,000 kb/s')
  await expect(card).toContainText('SSIMULACRA2 82.4')
  await expect(card).toContainText('worst 5% 74.1')
  await expect(card).toContainText('XPSNR 44.1 dB')
  await expect(card).toContainText('90 visually lossless')
  await card.screenshot({ path: testInfo.outputPath('sample-quality.png') })

  Object.assign(result, { ssimulacra2: null, ssimulacra2_p5: null, xpsnr: null }) // the setting was off
  fixture.refresh()
  await expect(card).toContainText('4,000 kb/s')
  await expect(card).not.toContainText('Quality')
  await expect(card).not.toContainText('SSIMULACRA2')
  expect(fixture.errors).toEqual([])
})

test('a CRF search lists its tries, marks the CRF found and puts it on the job', async ({ page }, testInfo) => {
  const t = (crf: number, ssimulacra2: number) => ({
    crf,
    bytes: 300_000,
    seconds: 12,
    kbps: 4000 - crf * 100,
    estimate_mb: 50,
    ssimulacra2,
    ssimulacra2_p5: ssimulacra2 - 8,
    xpsnr: 44,
  })
  const search: NonNullable<JobDetail['search']> = {
    percent: 2,
    metric: 'ssimulacra2',
    target: 80,
    start: 18,
    encoder: 'x265',
    frames: 144,
    total_frames: 2400,
    started: '2026-10-30T12:00:00',
    tries: [t(18, 82.1), t(22, 78), t(20, 80.6), t(21, 79.4)],
    done: true,
    crf: 20,
    exact: true,
    current: true,
  }
  const fixture = await queueFixture(page, 1, ['ready'], null, search)
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const card = page.getByRole('region', { name: 'CRF search', exact: true })
  await expect(card).toContainText('CRF 20 is the highest that reaches SSIMULACRA2 80.')
  const rows = card.locator('tbody tr')
  await expect(rows).toHaveCount(4)
  await expect(rows.first()).toContainText('18 ✓')
  await expect(rows.nth(1)).toContainText('2,000 kb/s')
  await card.screenshot({ path: testInfo.outputPath('crf-search.png') })

  await card.getByRole('button', { name: 'Use CRF 20' }).click()
  await expect
    .poll(() => fixture.calls.find((c) => c.path === '/api/jobs/job-0')?.body)
    .toMatchObject({
      encoder: { crf: 20 },
    })

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

test('a disabled control shows its styled tooltip, and tipped text in a row keeps focus on the row', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 3)
  const start = page.getByRole('button', { name: /Start queue/ })
  await expect(start).toBeDisabled()
  // A disabled button takes no pointer events: the tip's wrapper under it gets the hover.
  await start.hover({ force: true })
  await expect(page.locator('[data-slot="tooltip-content"]')).toContainText('Nothing is queued')
  await page.getByText('Episode 00001', { exact: true }).click()
  await expect(page.locator('button[data-job="job-1"]')).toBeFocused()
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

test('several jobs: the template line reads as one sentence when the template sets audio and subtitles', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 3)
  // Only what the line reads: the template sets audio and subtitle rules and detects each job's crop.
  const data = { qpf: true, crop_mode: 'auto', audio: { tracks: [] }, subs: { rules: [] } } as unknown as Template
  await page.route('**/api/presets', (route) =>
    route.fulfill({
      json: {
        video: [],
        encoder: [],
        audio: [],
        template: [{ name: 'Full', data }],
        template_defaults: {},
        encoder_starters: [],
      },
    }),
  )
  await page.reload()
  await expect(page.getByRole('status')).toContainText('3 of 3 jobs match')
  await page.getByRole('button', { name: 'Select matching jobs', exact: true }).click()
  await expect(page.getByText(/^Sets video, encoder/)).toHaveText(
    "Sets video, encoder, AutoQPF, audio, subtitles, and the container with its options; the crop is detected for each job. Save templates from a job's Template menu.",
  )
  expect(errors).toEqual([])
})

test("Index on one job it can't take says why, about that one job", async ({ page }) => {
  const { errors } = await queueFixture(page, 3)
  await page.route('**/api/queue/index', (route) => route.fulfill({ json: { taken: [] } }))
  await page.locator('[data-job="job-0"]').click()
  await page.getByRole('button', { name: 'Index the selected jobs', exact: true }).click()
  const why = page.getByText(/^1 left out: /)
  await expect(why).toBeVisible()
  expect(await why.textContent()).toContain("1 left out: it's queued or running") // read now: the toast closes
  expect(errors).toEqual([])
})

test('queue rows of one kind are one height, with or without format tags', async ({ page }) => {
  const { errors } = await queueFixture(page, 3, ['ready'], null, null, null, (i) => ({
    resolution: '1920x1080',
    duration_ms: 60_000,
    hdr: i === 0 ? [] : ['HDR10'],
    interlaced: false,
  }))
  const heights = await page
    .locator('[data-job]')
    .evaluateAll((rows) => rows.map((r) => r.parentElement!.getBoundingClientRect().height))
  expect(heights).toHaveLength(3)
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(0.5)
  expect(errors).toEqual([])
})

test('Encoder tab: the test encode and CRF search cards sit 16 px apart', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const sample = await page.getByRole('region', { name: 'Test encode', exact: true }).boundingBox()
  const search = await page.getByRole('region', { name: 'CRF search', exact: true }).boundingBox()
  expect(search!.y - (sample!.y + sample!.height)).toBeGreaterThanOrEqual(16)
  expect(errors).toEqual([])
})

/** A theme color as the browser computes it, read from a probe element with that Tailwind class. */
const themeColor = (page: Page, cls: string, prop: 'backgroundColor' | 'color') =>
  page.evaluate(
    ([cls, prop]) => {
      const probe = document.createElement('div')
      probe.className = cls
      document.body.append(probe)
      const value = getComputedStyle(probe)[prop as 'color']
      probe.remove()
      return value
    },
    [cls, prop],
  )

test('the Encoder tab fills at most one control with the accent', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  await expect(page.getByRole('region', { name: 'CRF search', exact: true })).toBeVisible()
  const primary = await themeColor(page, 'bg-primary', 'backgroundColor')
  // A ticked checkbox is a selection, so it may stay gold; buttons and toggles may not, but for one.
  const filled = await page
    .locator('main')
    .evaluate(
      (main, primary) =>
        [...main.querySelectorAll('button:not([role=checkbox]), [role=radio]')]
          .filter((el) => getComputedStyle(el).backgroundColor === primary)
          .map((el) => el.textContent?.trim()),
      primary,
    )
  expect(filled.length, filled.join(', ')).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

test('a disabled Start queue is gray, not dimmed gold', async ({ page }) => {
  const { errors } = await queueFixture(page, 3, ['ready'])
  const start = page.getByRole('button', { name: /^Start queue/ })
  await expect(start).toBeDisabled()
  const primary = await themeColor(page, 'bg-primary', 'backgroundColor')
  expect(await start.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(primary)
  expect(await start.evaluate((el) => getComputedStyle(el).opacity)).toBe('1')
  expect(errors).toEqual([])
})

test('Dolby Vision tags read like the other format tags, and DV? keeps its warning', async ({ page }) => {
  const hdr = [['DV 8.1', 'HDR10'], ['DV 7?']]
  const { errors } = await queueFixture(page, 2, ['ready'], null, null, null, (i) => ({
    resolution: '3840x2160',
    duration_ms: 60_000,
    hdr: hdr[i],
    interlaced: false,
  }))
  const color = (name: string) => page.getByText(name, { exact: true }).evaluate((el) => getComputedStyle(el).color)
  expect(await color('DV 8.1')).toBe(await color('HDR10'))
  expect(await color('DV 7?')).toBe(await themeColor(page, 'text-warning', 'color'))
  expect(errors).toEqual([])
})

for (const palette of ['gold', 'indigo', 'ocean', 'forest', 'ember', 'rose', 'slate'])
  for (const mode of ['light', 'dark'])
    test(`the selected encoder reads as selected: ${palette}, ${mode}`, async ({ page }) => {
      await page.addInitScript(
        ([palette, mode]) => {
          localStorage.setItem('videoforge.palette', palette)
          localStorage.setItem('videoforge.mode', mode)
        },
        [palette, mode],
      )
      const { errors } = await queueFixture(page, 1, ['ready'])
      await page.goto('/#/queue/job-0')
      await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
      const on = page.locator('main button[data-state=on]').filter({ hasText: /^(x264|x265|VP8|VP9|SVT-AV1)$/ })
      // The selected toggle's border against the surface it sits on: WCAG 1.4.11 asks 3:1 for a state indicator.
      const ratio = await on.evaluate((el) => {
        const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number)
        const lum = ([r, g, b]: number[]) => {
          const f = (v: number) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
          return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
        }
        let surface = el.parentElement
        while (surface && ['transparent', 'rgba(0, 0, 0, 0)'].includes(getComputedStyle(surface).backgroundColor))
          surface = surface.parentElement
        const [a, b] = [
          lum(rgb(getComputedStyle(el).borderTopColor)),
          lum(rgb(getComputedStyle(surface!).backgroundColor)),
        ]
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
      })
      expect(ratio).toBeGreaterThanOrEqual(3)
      expect(errors).toEqual([])
    })

test('queue row checkboxes line up with the search box', async ({ page }) => {
  const { errors } = await queueFixture(page, 3)
  const search = await page.getByPlaceholder('Search name or source path').boundingBox()
  const tick = await page
    .getByRole('checkbox', { name: /^Queued: / })
    .first()
    .boundingBox()
  expect(Math.abs(tick!.x - search!.x)).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

/** Where the eye sees a button's left edge: its border or fill when it has one, else its first text. */
async function visibleLeft(button: Locator): Promise<number> {
  return button.evaluate((el) => {
    const cs = getComputedStyle(el)
    const clear = (c: string) => c === 'transparent' || c === 'rgba(0, 0, 0, 0)'
    if (parseFloat(cs.borderLeftWidth) > 0 && !clear(cs.borderLeftColor)) return el.getBoundingClientRect().left
    if (!clear(cs.backgroundColor)) return el.getBoundingClientRect().left
    const range = document.createRange()
    range.selectNodeContents(el)
    return range.getClientRects()[0]?.left ?? el.getBoundingClientRect().left
  })
}

test('Edit the whole script lines up with the side panel controls', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await page.goto('/#/queue/job-0')
  const edit = await visibleLeft(page.getByRole('button', { name: 'Edit the whole script…', exact: true }))
  const preset = await visibleLeft(page.getByRole('complementary').getByRole('button').first()) // the preset menu
  expect(Math.abs(edit - preset)).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

test('Output tab: every label lines up with the first control in its row', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  // The rule set's containers bring the Container and PGS compression rows (a checkbox first: no text baseline).
  const containers = [
    { id: 'mkv', label: 'MKV (mkvmerge)', extension: '.mkv', tool: 'mkvmerge' },
    { id: 'mp4', label: 'MP4 (MP4Box)', extension: '.mp4', tool: 'MP4Box' },
  ]
  const spec = await page.evaluate(() =>
    fetch('/api/jobs/job-0')
      .then((r) => r.json())
      .then((d) => d.spec),
  )
  const template = { ...spec, crop_mode: 'keep', audio: null, subs: null }
  const defaults = { video: spec.video, encoder: spec.encoder, template }
  await page.route('**/api/rule-sets', (route) =>
    route.fulfill({
      json: [
        { id: 'manual', name: 'Manual', default: true, container: 'mkv', containers, defaults, track_editor: true },
      ],
    }),
  )
  await page.goto('/#/queue/job-0')
  await page.reload()
  await page.getByRole('tab', { name: 'Output', exact: true }).click()
  await expect(page.getByText('PGS compression', { exact: true })).toBeVisible()
  // Each label in the tab's label column against the first control on its row; a textarea counts by its first line.
  const rows = await page.evaluate(() => {
    const grid = [...document.querySelectorAll<HTMLElement>('main .grid')].find((g) =>
      g.textContent?.includes('Existing output'),
    )!
    const control = 'input:not([type=hidden]), select, textarea, button, [role=checkbox]'
    const out: { label: string; gap: number }[] = []
    for (const label of [...grid.children] as HTMLElement[]) {
      const cell = label.nextElementSibling as HTMLElement | null
      const text = label.textContent?.trim()
      if (!cell || !text || label.querySelector(control)) continue
      if (cell.getBoundingClientRect().left <= label.getBoundingClientRect().right) continue
      const first = [...cell.querySelectorAll<HTMLElement>(control)].find((c) => c.getBoundingClientRect().height > 1)
      if (!first) continue
      const r = first.getBoundingClientRect()
      const cs = getComputedStyle(first)
      const center =
        first.tagName === 'TEXTAREA'
          ? r.top + parseFloat(cs.borderTopWidth) + parseFloat(cs.paddingTop) + parseFloat(cs.lineHeight) / 2
          : r.top + r.height / 2
      const l = label.getBoundingClientRect()
      out.push({ label: text, gap: Math.round(Math.abs(l.top + l.height / 2 - center)) })
    }
    return out
  })
  expect(rows.map((r) => r.label)).toEqual(
    expect.arrayContaining(['Existing output', 'Name template', 'PGS compression']),
  )
  expect(rows.filter((r) => r.gap > 2)).toEqual([])
  expect(errors).toEqual([])
})
