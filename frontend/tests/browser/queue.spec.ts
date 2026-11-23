import { test, expect, type Locator, type Page, type WebSocketRoute } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { JobDetail, JobSummary, Status, Template, Tracks, VideoColor, VideoHdr } from '../../src/lib/types.ts'

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
    group: null,
    group_name: '',
    source: `D:\\Show\\Season${i < count / 2 ? 1 : 2}\\${i}.mkv`,
    rule_set: 'manual',
    status: statuses[i % statuses.length],
    progress: null,
    issue: '',
    issue_counts: { block: 0, warn: 0 },
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
    else if (path === '/api/jobs/remove') json = { removed: request.postDataJSON().ids, deleted: [], kept: {} }
    else if (path === '/api/queue/start') json = {}
    else if (path === '/api/queue/enqueue') json = { enqueued: request.postDataJSON().ids }
    else if (['/api/rule-sets', '/api/config/encoders', '/api/filter-presets'].includes(path)) json = []
    else if (path === '/api/settings') json = { output_dir: '', last_dir: '' }
    else if (path === '/api/fs/roots') json = ['D:\\']
    else if (path === '/api/fs/list')
      json = {
        path: 'D:\\Show',
        parent: 'D:\\',
        dirs: [{ name: '1.mkv_tmp', path: 'D:\\Show\\1.mkv_tmp', mtime: 1_700_000_000 }],
        files: [
          { name: 'videoforge-job.json', path: 'D:\\Show\\videoforge-job.json', size: 900, mtime: 1_700_000_000 },
        ],
      }
    else if (path === '/api/fs/kinds')
      json = (request.postDataJSON().paths as string[]).map((p) => ({
        path: p,
        kind: p.endsWith('_tmp') ? 'folder' : 'file',
      }))
    else if (path === '/api/jobs/import') json = { added: [], skipped: [] }
    // Queue groups, as the server does them (enough for the list to show the result).
    else if (path === '/api/jobs/move') {
      const { ids, before, group } = request.postDataJSON() as { ids: string[]; before: string | null; group: string }
      const moving = jobs.filter((j) => ids.includes(j.id))
      const rest = jobs.filter((j) => !ids.includes(j.id))
      const name = rest.find((j) => j.group === group)?.group_name ?? moving.find((j) => j.group === group)?.group_name
      for (const j of moving) [j.group, j.group_name] = group ? [group, name ?? ''] : [null, '']
      const at = before === null ? rest.length : rest.findIndex((j) => j.id === before)
      jobs.splice(0, jobs.length, ...rest.slice(0, at), ...moving, ...rest.slice(at))
      json = { ids: jobs.map((j) => j.id) }
    } else if (path === '/api/jobs/group') {
      const { ids, name } = request.postDataJSON() as { ids: string[]; name: string }
      for (const j of jobs) if (ids.includes(j.id)) [j.group, j.group_name] = ['g-new', name]
      json = { group: 'g-new' }
    } else if (/^\/api\/groups\/[^/]+\/(rename|ungroup)$/.test(path)) {
      const [, , , id, action] = path.split('/')
      for (const j of jobs.filter((j) => j.group === id))
        [j.group, j.group_name] = action === 'rename' ? [id, request.postDataJSON().name] : [null, '']
      json = { group: id }
    } else throw new Error(`Unhandled queue fixture request: ${request.method()} ${path}`)
    await route.fulfill({ json })
  })
  await page.goto('/#/queue')
  await expect(page.getByRole('status')).toContainText(`${count} of ${count} jobs match`)
  return {
    jobs,
    calls,
    errors,
    refresh: () => socket.send(JSON.stringify({ type: 'job', id: jobs[0].id })),
    send: (event: Record<string, unknown>) => socket.send(JSON.stringify(event)), // a server event, such as 'queue'
  }
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
  await page.getByRole('button', { name: 'More actions', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Add jobs from job files…', exact: true }).click()
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

test('the Shortcuts dialog carries the note about actions on the selection', async ({ page }) => {
  const fixture = await queueFixture(page, 2, ['ready'])
  await page.getByRole('button', { name: 'Keyboard shortcuts', exact: true }).click()
  await expect(
    page.getByRole('dialog', { name: 'Keyboard shortcuts' }).getByRole('region', { name: 'Queue list' }),
  ).toContainText(
    'Actions on the selection include jobs on other pages and jobs hidden by filters. Index uses the selected jobs, or every job when none is selected.',
  )
  expect(fixture.errors).toEqual([])
})

test('the status filter lists statuses with jobs, and keeps the chosen one at zero', async ({ page }) => {
  const fixture = await queueFixture(page, 4, ['ready', 'done'])
  const select = page.getByRole('combobox', { name: 'Filter jobs by status' })
  const options = () => select.locator('option').allTextContents()
  expect(await options()).toEqual(['All statuses (4)', 'Ready (2)', 'Done (2)'])
  await select.selectOption('ready')
  await page.getByRole('searchbox').fill('Episode 00001')
  // Ready has no match now, but stays listed because it is chosen.
  expect(await options()).toEqual(['All statuses (1)', 'Ready (0)', 'Done (1)'])
  await select.selectOption('')
  await page.getByRole('searchbox').fill('nothing matches')
  expect(await options()).toEqual(['All statuses (0)'])
  expect(fixture.errors).toEqual([])
})

test('at 1024 px the rail chips carry a status mark and a name with the status', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 700 })
  const fixture = await queueFixture(page, 3, ['done', 'warn', 'ready'])
  await page.goto('/#/queue/job-0')
  const rail = page.getByRole('region', { name: 'Queue rail', exact: true })
  const done = rail.locator('[data-job="job-0"]')
  const warn = rail.locator('[data-job="job-1"]')
  const ready = rail.locator('[data-job="job-2"]')
  await expect(done).toHaveAccessibleName('1. Episode 00000, Done')
  await expect(warn).toHaveAccessibleName('2. Episode 00001, Ready with warnings')
  await expect(done.locator('svg.lucide-check[aria-hidden="true"]')).toHaveCount(1)
  await expect(warn.locator('svg.lucide-triangle-alert[aria-hidden="true"]')).toHaveCount(1)
  await expect(ready.locator('svg')).toHaveCount(0)
  expect(fixture.errors).toEqual([])
})

test('a done job says what its run made', async ({ page }) => {
  const made = { output_bytes: 4.5 * 1024 ** 3, source_bytes: 18 * 1024 ** 3, seconds: 5025, reused: 2, kbps: 6120 }
  const fixture = await queueFixture(page, 1, ['done'], null, null, made)
  await page.goto('/#/queue/job-0')
  // The job's facts line under its name (one box per figure, so it is read as a whole line).
  await expect(page.locator('header .readout')).toContainText(
    'Made 4.5 GB · 25.0% of the source · 6,120 kb/s · took 1:23:45 (2 reused)',
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
  // Its figures read like every other technical figure: code font, fixed-width digits.
  await expect(card.getByText('4,000 kb/s')).toHaveCSS('font-family', /^"?Cascadia Mono/)
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
  await expect(rows.first()).toContainText('18')
  await expect(rows.first()).not.toContainText('✓')
  await expect(rows.first().getByRole('img', { name: 'Reaches SSIMULACRA2 80' })).toBeVisible()
  await expect(rows.nth(1)).toContainText('2,000 kb/s')
  await expect(rows.first()).toHaveCSS('font-family', /^"?Cascadia Mono/)
  await expect(card.getByText(/144 of 2,400 frames \(2%\)/)).toHaveCSS('font-family', /^"?Cascadia Mono/)
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

// 784 x 450 is a 1568 x 900 window at 200% zoom
for (const [width, height, zoomed] of [
  [784, 450, true],
  [1024, 700, false],
  [1280, 800, false],
  [1366, 768, false],
  [1600, 900, false],
] as const)
  test(`at ${width} px the menu, the job name and the Video tab ${zoomed ? 'make room' : 'stay as they are'}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height })
    const { errors } = await queueFixture(page, 1, ['ready'])
    await page.goto('/#/queue/job-0')
    // the menu: a rail below 1440 px with a job open; below 1024 px there is no way to expand it
    const nav = (await page.getByRole('navigation', { name: 'Main navigation' }).boundingBox())!
    expect(nav.width < 100).toBe(width < 1440)
    await expect(page.getByRole('button', { name: /^(Expand|Collapse) the menu$/ })).toBeVisible({ visible: !zoomed })
    // the job name: its own line when the header is narrow, beside the Queue box otherwise; never cut
    const name = page.getByRole('heading', { name: 'Episode 00000', level: 2 })
    const queue = (await page.getByRole('checkbox', { name: 'Queue', exact: true }).boundingBox())!
    const title = (await name.boundingBox())!
    expect(title.y + title.height <= queue.y).toBe(zoomed)
    expect(await name.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0)
    // the Video tab: the preview above its settings when the tab is narrow, so it keeps a usable width
    await page.getByRole('tab', { name: 'Video', exact: true }).click()
    const preview = (await page.locator('#job-tab-panel > div > div').first().boundingBox())!
    expect(preview.width).toBeGreaterThanOrEqual(300)
    await expect(page.getByRole('separator', { name: 'Resize the side panel' })).toBeVisible({ visible: !zoomed })
    // Expand still fills the whole window: the tab panel it sits in is a query container
    await page.getByRole('button', { name: 'Expand', exact: true }).click()
    const expanded = (await page.locator('#job-tab-panel > div').first().boundingBox())!
    expect([expanded.x, expanded.y, expanded.width, expanded.height]).toEqual([0, 0, width, height])
    expect(errors).toEqual([])
  })

// the longest line 1 each status can have: [status, issue counts, indexed]
const ROW_CASES = [
  ['warn', { block: 0, warn: 2 }, true],
  ['paused', { block: 0, warn: 1 }, true],
  ['warn', { block: 0, warn: 0 }, true],
  ['index-queued', { block: 0, warn: 0 }, false],
  ['blocked', { block: 1, warn: 1 }, true],
] as const
for (const density of ['compact', 'default', 'comfortable'])
  for (const width of [1130, 1280, 1366])
    test(`at ${width} px, ${density}, with a job open the list keeps names and the menu is icons`, async ({ page }) => {
      await page.addInitScript((d) => localStorage.setItem('videoforge.density', d), density)
      await page.setViewportSize({ width, height: 800 })
      const fixture = await queueFixture(page, ROW_CASES.length, ['warn'])
      ROW_CASES.forEach(([status, issue_counts, indexed], i) =>
        Object.assign(fixture.jobs[i], {
          status,
          label: 'Season 1',
          indexed,
          issue_counts,
          source_facts: { resolution: '3840x2160', duration_ms: 3_600_000, hdr: [], interlaced: false },
        }),
      )
      await page.route('**/video/info**', (route) => route.fulfill({ status: 404, json: {} })) // the indexed job's preview
      await page.goto('/#/queue/job-0')
      await expect(page.getByRole('region', { name: 'Queue rail', exact: true })).toHaveCount(0)
      const list = page.getByRole('region', { name: 'Queue list', exact: true })
      await expect(list.locator('[data-job="job-0"]').getByText('2 warnings', { exact: true })).toBeVisible()
      expect((await page.getByRole('navigation', { name: 'Main navigation' }).boundingBox())!.width).toBeLessThan(100)
      // the editor keeps room for its header on one line (44rem, where the job name drops to its own line)
      if (density === 'default')
        expect((await page.getByRole('region', { name: 'Job settings' }).boundingBox())!.width).toBeGreaterThanOrEqual(
          704,
        )
      for (let i = 0; i < ROW_CASES.length; i++) {
        const m = await list.locator(`[data-job="job-${i}"]`).evaluate((el) => {
          const box = (n: Element) => n.getBoundingClientRect()
          const group = el.querySelector<HTMLElement>('.ml-auto')! // the indexed icon, the status and the marks
          const name = el.querySelector<HTMLElement>('.truncate')!
          const probe = document.createElement('span')
          probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre'
          probe.style.font = getComputedStyle(name).font
          probe.textContent = '0'.repeat(15)
          document.body.append(probe)
          const fifteen = probe.getBoundingClientRect().width
          probe.remove()
          const section = el.closest('section')!
          return {
            text: group.textContent!.replace(/\s+/g, ' ').trim(),
            cut: Math.max(...[group, ...group.querySelectorAll('span')].map((n) => n.scrollWidth - n.clientWidth)),
            groupRight: box(group).right,
            listRight: box(el).right - parseFloat(getComputedStyle(el).paddingRight), // the row's own edge, inside its padding
            nameWidth: box(name).width,
            fifteen,
            rowOverflow: el.scrollWidth - el.clientWidth,
            listOverflow: section.scrollWidth - section.clientWidth,
            facts: el.querySelector('.readout')?.textContent,
          }
        })
        const where = `job-${i} (${m.text})`
        expect(m.cut, where).toBeLessThanOrEqual(0)
        expect(m.groupRight, where).toBeLessThanOrEqual(m.listRight + 0.5) // sub-pixel rounding
        expect(m.nameWidth, where).toBeGreaterThanOrEqual(m.fifteen - 1)
        expect(m.rowOverflow, where).toBeLessThanOrEqual(0)
        expect(m.listOverflow, where).toBeLessThanOrEqual(0)
        expect(m.facts, where).toMatch(/^3840×2160 · 1:00:00/)
      }
      expect(fixture.errors).toEqual([])
    })

test('at 1024 px with a job open the list is a rail of chips', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 700 })
  const fixture = await queueFixture(page, 3, ['ready'])
  await page.goto('/#/queue/job-0')
  await expect(page.getByRole('region', { name: 'Queue rail', exact: true })).toBeVisible()
  expect(fixture.errors).toEqual([])
})

test('Expand opens the menu for now while a job is open, without remembering it', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  const fixture = await queueFixture(page, 3, ['ready'])
  await page.goto('/#/queue/job-0')
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect.poll(async () => (await nav.boundingBox())!.width).toBeLessThan(100)
  await page.getByRole('button', { name: 'Expand the menu', exact: true }).click()
  await expect.poll(async () => (await nav.boundingBox())!.width).toBeGreaterThan(150)
  expect(await page.evaluate(() => localStorage.getItem('videoforge.navCollapsed'))).toBeNull()
  // widening the window ends the override, so narrowing again collapses the menu once more
  await page.setViewportSize({ width: 1600, height: 800 })
  await expect(page.getByRole('button', { name: 'Collapse the menu', exact: true })).toBeVisible()
  await page.setViewportSize({ width: 1280, height: 800 })
  await expect.poll(async () => (await nav.boundingBox())!.width).toBeLessThan(100)
  expect(fixture.errors).toEqual([])
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

test('the menu marks the running job with an icon, in both widths', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['running'])
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(nav).toContainText('Episode 00000')
  await expect(nav).not.toContainText('▶')
  await expect(nav.locator('.text-info svg').first()).toBeVisible()
  await page.getByRole('button', { name: 'Collapse the menu', exact: true }).click()
  await expect(nav).not.toContainText('▶')
  await expect(nav.locator('.text-info svg').first()).toBeVisible()
  expect(errors).toEqual([])
})

test('the queue list hint shows its keys as keycaps', async ({ page }) => {
  const { errors } = await queueFixture(page, 3)
  await expect(page.locator('#queue-keys kbd')).toHaveText(['Home', 'End', 'Shift', 'Ctrl+A', 'Cmd+A'])
  await expect(page.locator('#queue-keys')).toContainText('Arrow keys, Home and End move through the list.')
  expect(errors).toEqual([])
})

/** Visible text set under 12 px, in uppercase, or in italics: each as "<reason>: <text>". */
const typeProblems = (page: Page) =>
  page.evaluate(() => {
    const out: string[] = []
    for (const el of document.querySelectorAll<HTMLElement>('body *')) {
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim())
      if (!own || el.closest('.sr-only, [data-sonner-toaster]')) continue
      const r = el.getBoundingClientRect()
      const cs = getComputedStyle(el)
      if (r.width <= 1 || r.height <= 1 || cs.visibility === 'hidden') continue
      const text = el.textContent!.trim().slice(0, 40)
      if (parseFloat(cs.fontSize) < 12) out.push(`${cs.fontSize}: ${text}`)
      if (cs.textTransform === 'uppercase') out.push(`uppercase: ${text}`)
      if (cs.fontStyle === 'italic') out.push(`italic: ${text}`)
    }
    return [...new Set(out)]
  })

test('a placeholder that is a sentence uses the normal font, even in a code-font field', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await page.goto('/#/queue/job-0')
  const placeholderFont = (field: Locator) => field.evaluate((el) => getComputedStyle(el, '::placeholder').fontFamily)
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const extra = page.getByPlaceholder('added at the end, as typed')
  expect(await placeholderFont(extra)).not.toMatch(/Cascadia Mono/)
  await page.getByRole('tab', { name: 'Output', exact: true }).click()
  // Until the field is focused, the name template's placeholder is a sentence, not a template.
  const template = page.getByRole('textbox', { name: 'Name template', exact: true })
  await expect(template).toHaveAttribute('placeholder', 'Empty uses the default template (see Tokens)')
  expect(await placeholderFont(template)).not.toMatch(/Cascadia Mono/)
  expect(errors).toEqual([])
})

test('encoder option names keep their case', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  await page.locator('summary').filter({ hasText: 'Advanced settings' }).click()
  expect(await page.getByText(/^Options \(/).innerText()).toContain('--name value')
  expect(errors).toEqual([])
})

test('job tabs: no text under 12 px, no uppercase labels, no italics', async ({ page }) => {
  const { errors } = await queueFixture(page, 2, ['ready'], null, null, null, () => ({
    resolution: '3840x2160',
    duration_ms: 60_000,
    hdr: ['DV 8.1', 'HDR10'],
    interlaced: false,
  }))
  await page.goto('/#/queue/job-0')
  const problems: string[] = [...(await typeProblems(page)).map((p) => `Queue: ${p}`)]
  for (const tab of ['Encoder', 'Audio', 'Subtitles', 'Output']) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    // the closed Advanced sections' text is checked too
    for (const summary of await page.locator('details:not([open]) > summary').all()) await summary.click()
    problems.push(...(await typeProblems(page)).map((p) => `${tab}: ${p}`))
  }
  expect([...new Set(problems)]).toEqual([])
  expect(errors).toEqual([])
})

for (const count of [12, 120])
  test(`the collapsed menu keeps a count of ${count} jobs inside it, on the icon's top edge`, async ({ page }) => {
    const { errors } = await queueFixture(page, count)
    await page.getByRole('button', { name: 'Collapse the menu', exact: true }).click()
    const queue = page.getByRole('button', { name: `Queue ${count} jobs` })
    const nav = (await page.getByRole('navigation', { name: 'Main navigation' }).boundingBox())!
    const badge = (await queue.locator('[data-slot=badge]').boundingBox())!
    const icon = (await queue.locator('svg').first().boundingBox())!
    expect(badge.x + badge.width).toBeLessThanOrEqual(nav.x + nav.width)
    // It may sit on the icon's corner, but no lower than the old 10 px badge did: the icon's top 6 px.
    expect(badge.y + badge.height - icon.y).toBeLessThanOrEqual(6)
    expect(errors).toEqual([])
  })

test('a running job shows its progress figures in the code font', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['running'])
  const jobs = await page.evaluate(() => fetch('/api/jobs').then((r) => r.json()))
  jobs[0].progress = {
    step: 'Video (x264)',
    index: 4,
    total: 7,
    fraction: 0.42,
    overall: 0.6,
    reused: false,
    fps: 12.5,
    eta: 120,
    elapsed: 300,
    left: 400,
  }
  await page.route('**/api/jobs', (route) => route.fulfill({ json: jobs }))
  await page.goto('/#/queue/job-0')
  await page.reload()
  const mono = /^"?Cascadia Mono/
  await expect(page.getByText('12.5 fps · 5:00 · ~6:40 left', { exact: true })).toHaveCSS('font-family', mono) // queue row
  await expect(page.getByText('Video (x264) · 42.0%', { exact: true })).toHaveCSS('font-family', mono) // queue row step
  await expect(page.locator('header span', { hasText: 'job 60.0%' }).first()).toHaveCSS('font-family', mono) // job header
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

test("the toolbar's first row stays put when a job starts or indexing runs, so Cancel never lands on Run selected", async ({
  page,
}) => {
  const fixture = await queueFixture(page, 3, ['ready'])
  const runSelected = page.getByRole('button', { name: /^Run selected/ })
  // where it starts: its count's digits change its width
  const at = async () => {
    const { x, y, height } = (await runSelected.boundingBox())!
    return { x, y, height }
  }
  const idleAt = await at()
  // A selection brings Queue (1), at the end of the selection's row: the first row stays as it was.
  await page.getByText('Episode 00001', { exact: true }).click()
  await expect(page.getByRole('button', { name: 'Queue (1)', exact: true })).toBeVisible()
  const before = await at()
  expect(before).toEqual(idleAt)
  const firstRowEnd = before.y + before.height
  const below = async (name: string) =>
    expect((await page.getByRole('button', { name, exact: true }).boundingBox())!.y).toBeGreaterThanOrEqual(firstRowEnd)
  const idle = {
    type: 'queue',
    running: false,
    current: null,
    stop_after_current: false,
    paused: false,
    priority: null,
    queued: 0,
    indexing: null,
    sampling: null,
    index_queued: 0,
    index_held: 0,
  }

  fixture.send({ ...idle, running: true, current: 'job-0', queued: 1 })
  await expect(page.getByRole('button', { name: 'Stop after current', exact: true })).toBeVisible()
  expect(await at()).toEqual(before)
  await below('Cancel')
  await below('Pause after pass 1')
  await below('Pause')

  fixture.send({ ...idle, running: true, current: 'job-0', stop_after_current: true })
  await expect(page.getByRole('button', { name: 'Stopping…', exact: true })).toBeVisible()
  expect(await at()).toEqual(before)

  // Indexing with no job running: Start queue keeps its place, and the second row has what applies to indexing.
  fixture.send({ ...idle, indexing: 'job-2' })
  await expect(page.getByRole('button', { name: /^Start queue/ })).toBeVisible()
  expect(await at()).toEqual(before)
  await below('Stop indexing')
  await below('Pause')
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toHaveCount(0)

  fixture.send(idle)
  await expect(page.getByRole('button', { name: 'Stop indexing', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Pause', exact: true })).toHaveCount(0)
  expect(await at()).toEqual(before)
  expect(fixture.errors).toEqual([])
})

test('a paused queue has one primary button, and a pressed Pause after pass 1 is not primary', async ({ page }) => {
  const fixture = await queueFixture(page, 3, ['ready'])
  const primary = page.locator('button.bg-primary')
  const idle = {
    type: 'queue',
    running: false,
    current: null,
    stop_after_current: false,
    paused: false,
    priority: null,
    queued: 0,
    indexing: null,
    sampling: null,
    index_queued: 0,
    index_held: 0,
  }
  await expect(primary.filter({ hasText: /^Start queue/ })).toHaveCount(1)
  fixture.send({ ...idle, paused: true, indexing: 'job-2' })
  await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeVisible()
  await expect(primary.filter({ hasText: /^Start queue/ })).toHaveCount(0)
  await expect(primary.filter({ hasText: 'Resume' })).toHaveCount(1)
  fixture.send({ ...idle, running: true, current: 'job-0' })
  await expect(page.getByRole('button', { name: 'Pause after pass 1', exact: true })).toBeVisible()
  fixture.jobs[0].pause_after_pass1 = true
  fixture.refresh()
  const pressed = page.getByRole('button', { name: 'Pausing after pass 1', exact: true })
  await expect(pressed).toBeVisible()
  await expect(pressed).not.toHaveClass(/(^|\s)bg-primary(\s|$)/)
  await expect(pressed).toHaveClass(/(^|\s)bg-muted(\s|$)/)
  expect(fixture.errors).toEqual([])
})

test('a running job in a paused queue says Paused in the info colour', async ({ page }) => {
  const fixture = await queueFixture(page, 3, ['running'])
  fixture.send({
    type: 'queue',
    running: false,
    current: null,
    stop_after_current: false,
    paused: true,
    priority: null,
    queued: 0,
    indexing: null,
    sampling: null,
    index_queued: 0,
    index_held: 0,
  })
  const label = page.getByText('Paused', { exact: true }).first()
  await expect(label).toHaveClass(/(^|\s)text-info(\s|$)/)
  await expect(label).not.toHaveClass(/text-warning/)
  expect(fixture.errors).toEqual([])
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
  const search = await page.getByPlaceholder('Search name, path, encoder or HDR').boundingBox()
  const tick = await page
    .getByRole('checkbox', { name: /^Queued: / })
    .first()
    .boundingBox()
  expect(Math.abs(tick!.x - search!.x)).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

test('a Queue caption names the checkboxes, and a queued row shows a lock before its status', async ({ page }) => {
  const { errors } = await queueFixture(page, 2, ['queued', 'ready'])
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await expect(list.getByRole('searchbox')).toHaveAccessibleName(
    'Search jobs by name, source path, encoder, resolution or HDR format',
  )
  // The caption sits over the column of checkboxes, visible and read by a screen reader.
  const caption = list.locator('span', { hasText: /^Queued$/ }).first()
  await expect(caption).toBeVisible()
  expect(await caption.evaluate((el) => !!el.closest('[aria-hidden="true"]'))).toBe(false)
  const c = (await caption.boundingBox())!
  const box = (await list.getByRole('checkbox', { name: 'Queued: Episode 00000' }).boundingBox())!
  expect(Math.abs(c.x - box.x)).toBeLessThanOrEqual(1)
  expect(c.y + c.height).toBeLessThanOrEqual(box.y)
  await caption.hover()
  await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText(
    "A ticked job is queued and locked, so you can't edit it until you untick it. Start queue runs the queued jobs.",
  )
  // The selection note moved to the Shortcuts dialog.
  await expect(list).not.toContainText('Actions on the selection')
  await expect(list).not.toContainText('A ticked job is queued')
  // A lock before "Queued", in its color; none on a ready row.
  const queued = page.locator('[data-job="job-0"]')
  await expect(queued.locator('svg.lucide-lock')).toHaveCount(1)
  await expect(queued.getByText('Queued', { exact: true })).toBeVisible()
  await expect(page.locator('[data-job="job-1"]').locator('svg.lucide-lock')).toHaveCount(0)
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

test('Edit the whole script lines up with the Source filter menu above it', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await page.goto('/#/queue/job-0')
  const panel = page.getByRole('complementary')
  await panel.locator('summary').filter({ hasText: 'Advanced' }).click()
  const edit = await visibleLeft(panel.getByRole('button', { name: 'Edit the whole script…', exact: true }))
  const filter = await visibleLeft(panel.getByRole('combobox', { name: 'Source filter', exact: true }))
  expect(Math.abs(edit - filter)).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

test('Video: Source filter and Edit the whole script… sit in a closed Advanced section at the bottom', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await withDetail(page, (d) => (d.spec.video.source_filter = 'bestsource'))
  await page.goto('/#/queue/job-0')
  const panel = page.getByRole('complementary')
  const advanced = panel.locator('summary').filter({ hasText: 'Advanced' })
  const filter = panel.getByRole('combobox', { name: 'Source filter', exact: true })
  const edit = panel.getByRole('button', { name: 'Edit the whole script…', exact: true })
  // BestSource isn't the default, FFMS2.
  await expect(advanced).toHaveText('Advanced (1)')
  await expect(filter).toBeHidden()
  await expect(edit).toBeHidden()
  const filters = (await panel.getByText('Filters', { exact: true }).boundingBox())!
  expect((await advanced.boundingBox())!.y).toBeGreaterThan(filters.y)
  await advanced.click()
  await expect(filter).toHaveValue('bestsource')
  await expect(edit).toBeVisible()
  await expect(advanced).toHaveText('Advanced')
  await page.reload()
  await expect(filter).toBeVisible()
  expect(errors).toEqual([])
})

/** After queueFixture: serve the Manual rule set, with its name and containers, and open job-0 with it. */
async function withRuleSet(page: Page) {
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
}

test('the job header keeps the name on its line and the job facts on the line below', async ({ page }) => {
  const made = { output_bytes: 4.5 * 1024 ** 3, source_bytes: 18 * 1024 ** 3, seconds: 5025, reused: 0, kbps: 6120 }
  const { errors } = await queueFixture(page, 1, ['done'], null, null, made)
  await withRuleSet(page)
  const name = (await page.getByRole('heading', { name: 'Episode 00000' }).boundingBox())!
  const facts = page.getByText(/^Manual · x265/)
  await expect(facts).toContainText('Made 4.5 GB')
  expect((await facts.boundingBox())!.y).toBeGreaterThanOrEqual(name.y + name.height)
  const look = await facts.evaluate((el) => [getComputedStyle(el).fontFamily, getComputedStyle(el).fontVariantNumeric])
  expect(look[0]).toMatch(/^"?Cascadia Mono/)
  expect(look[1]).toContain('tabular-nums')
  expect(errors).toEqual([])
})

test('at 390 px the job header breaks its facts between figures, never inside one', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const made = { output_bytes: 4.5 * 1024 ** 3, source_bytes: 18 * 1024 ** 3, seconds: 5025, reused: 2, kbps: 6120 }
  const { errors } = await queueFixture(page, 1, ['done'], null, null, made)
  // A narrow window opens a done job on its log.
  await page.route('**/api/jobs/job-0/log-snapshot', (route) =>
    route.fulfill({ json: { seq: 0, steps: [], lines: [] } }),
  )
  await page.goto('/#/queue/job-0')
  const facts = page.locator('header .readout')
  await expect(facts).toContainText('took 1:23:45')
  const lineHeight = await facts.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight))
  expect((await facts.boundingBox())!.height).toBeGreaterThan(lineHeight) // it does wrap at this width
  const broken = await facts.evaluate((el, lh) => {
    // Each figure is its own box; one taller than a line broke inside itself.
    const parts = [...el.querySelectorAll(':scope > *')]
    return parts.length < 4
      ? ['one box']
      : parts.filter((p) => p.getBoundingClientRect().height > lh + 1).map((p) => p.textContent)
  }, lineHeight)
  expect(broken).toEqual([])
  expect(errors).toEqual([])
})

test('queue rows show sizes with a times sign, and at 390 px the facts stay on one line', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const { errors } = await queueFixture(page, 3, ['ready'], null, null, null, () => ({
    resolution: '3840x2076',
    duration_ms: 5_400_000,
    hdr: ['DV 7.6 FEL/MEL?', 'HDR10'], // the longest tag hdr.formats() makes: profile 7 before dovi_tool reads it
    interlaced: false,
  }))
  // Rows as long as real ones: an encoder with its CRF, a crop, and track counts.
  const jobs = await page.evaluate(() => fetch('/api/jobs').then((r) => r.json()))
  for (const job of jobs)
    Object.assign(job, {
      encoder: 'x264 CRF 18',
      crop: { left: 0, top: 42, right: 0, bottom: 42 },
      audio: [{}, {}, {}],
      subs: 4,
    })
  await page.route('**/api/jobs', (route) => route.fulfill({ json: jobs }))
  await page.reload()
  const rows = page.locator('[data-job]')
  await expect(rows.first()).toContainText('3840×2076')
  await expect(rows.first()).toContainText('crop 0/42/0/42')
  // The facts line is one line that ends in an ellipsis (its text stays whole in the DOM), never two.
  const lines = await rows.evaluateAll((all) =>
    all.flatMap((row) =>
      [...row.querySelectorAll<HTMLElement>('.readout')].map((line) => line.getBoundingClientRect().height),
    ),
  )
  const problems = lines.filter((h) => h > 21).map((h) => `wraps: ${h}`)
  await expect(rows.first().locator('.readout')).toHaveCSS('text-overflow', 'ellipsis')
  expect(await rows.first().locator('.readout').count()).toBeGreaterThan(0)
  // It is cut (wider than its box) with the whole text still in the DOM; the status beside the name is never cut.
  const cut = await rows
    .first()
    .locator('.readout')
    .first()
    .evaluate((el) => [el.scrollWidth, el.clientWidth])
  expect(cut[0]).toBeGreaterThan(cut[1])
  await expect(rows.first().locator('.readout').first()).toContainText('4 subs')
  const status = rows.first().getByText('Ready', { exact: true })
  await expect(status).toHaveText('Ready')
  const statusCut = await status.evaluate((el) => [el.scrollWidth, el.clientWidth])
  expect(statusCut[0]).toBeLessThanOrEqual(statusCut[1])
  expect([...new Set(problems)]).toEqual([])
  expect(errors).toEqual([])
})

test('Output tab: every label lines up with the first control in its row', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  // The rule set's containers bring the Container and PGS compression rows (a checkbox first: no text baseline).
  await withRuleSet(page)
  await page.getByRole('tab', { name: 'Output', exact: true }).click()
  await page.locator('summary').filter({ hasText: 'Advanced' }).click()
  await expect(page.getByText('PGS compression', { exact: true })).toBeVisible()
  // Each label in the tab's label columns (the tab's, and its Advanced section's) against the first control on its
  // row; a textarea counts by its first line.
  const rows = await page.evaluate(() => {
    const grids = ['Existing output', 'PGS compression'].map((text) =>
      [...document.querySelectorAll<HTMLElement>('main .grid')].find((g) => g.textContent?.includes(text))!,
    )
    const control = 'input:not([type=hidden]), select, textarea, button, [role=checkbox]'
    const out: { label: string; gap: number }[] = []
    for (const label of grids.flatMap((grid) => [...grid.children]) as HTMLElement[]) {
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

test('Output tab: the Rule set menu shows only when there is more than one rule set', async ({ page }) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await withRuleSet(page)
  await page.getByRole('tab', { name: 'Output', exact: true }).click()
  const panel = page.getByRole('tabpanel')
  await expect(panel.getByText('Existing output', { exact: true })).toBeVisible()
  await expect(panel.getByRole('combobox', { name: 'Rule set' })).toHaveCount(0)
  await expect(panel.getByText('Rule set', { exact: true })).toHaveCount(0)
  // The header's facts line still names it.
  await expect(page.locator('header').getByText(/^Manual · x265/)).toBeVisible()

  const ruleSets = await page.evaluate(() => fetch('/api/rule-sets').then((r) => r.json()))
  await page.route('**/api/rule-sets', (route) =>
    route.fulfill({ json: [...ruleSets, { ...ruleSets[0], id: 'house', name: 'House rules', default: false }] }),
  )
  await page.reload()
  await page.getByRole('tab', { name: 'Output', exact: true }).click()
  await expect(page.getByRole('tabpanel').getByRole('combobox', { name: 'Rule set', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('Output: extra arguments, PGS compression, the work folder and finished steps sit in a closed Advanced section', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 1, ['ready'])
  await withDetail(page, (d) => {
    Object.assign(d.spec.mux, { extra: '--no-date', pgs_zlib: true })
    d.steps = { mux: { id: 'mux', fingerprint: 'f', outputs: [], seconds: 3 } }
  })
  await withRuleSet(page)
  await page.getByRole('tab', { name: 'Output', exact: true }).click()
  const advanced = page.locator('summary').filter({ hasText: 'Advanced' })
  const extra = page.getByRole('textbox', { name: 'Extra arguments for mkvmerge', exact: true })
  const pgs = page.getByRole('checkbox', { name: 'Compress PGS subtitles with zlib', exact: true })
  const work = page.getByText('Work folder', { exact: true })
  const steps = page.getByText(/^Finished steps/)
  // The extra arguments and PGS compression differ from the defaults; the work folder and steps aren't settings.
  await expect(advanced).toHaveText('Advanced (2)')
  for (const hidden of [extra, pgs, work, steps]) await expect(hidden).toBeHidden()
  const existing = (await page.getByText('Existing output', { exact: true }).boundingBox())!
  expect((await advanced.boundingBox())!.y).toBeGreaterThan(existing.y)
  await expect(page.getByText('D:\\Show\\Season1\\0.mkv_tmp', { exact: true })).toBeHidden()
  await advanced.click()
  for (const shown of [extra, pgs, work, steps]) await expect(shown).toBeVisible()
  await expect(extra).toHaveValue('--no-date')
  await expect(advanced).toHaveText('Advanced')
  expect(errors).toEqual([])
})

/** Drag a row's grip to `y` of the way down the target row (0 top, 1 bottom), in small steps like a hand. */
async function dragGrip(page: Page, from: Locator, to: Locator, y: number) {
  const grip = (await from.locator('[title^="Drag to move"]').boundingBox())!
  const target = (await to.boundingBox())!
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2)
  await page.mouse.down()
  await page.mouse.move(target.x + target.width / 2, target.y + target.height * y, { steps: 8 })
  await page.waitForTimeout(50) // a frame for the drop line
  await page.mouse.up()
}

const row = (page: Page, id: string) => page.locator('[data-row]', { has: page.locator(`[data-job="${id}"]`) })

test('a group collapses, and a grip drags its jobs out of it and back in', async ({ page }, testInfo) => {
  const fixture = await queueFixture(page, 5, ['ready'])
  for (const j of fixture.jobs.slice(1, 4)) [j.group, j.group_name] = ['g1', 'Show S01']
  fixture.refresh()
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await expect(list.getByRole('button', { name: 'Collapse Show S01', exact: true })).toBeVisible()
  await expect(list.getByText('3 jobs', { exact: true })).toBeVisible()
  await list.screenshot({ path: testInfo.outputPath('queue-group.png') })
  const axe = await new AxeBuilder({ page })
    .include('section[aria-label="Queue list"]')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(axe.violations).toEqual([])

  await list.getByRole('button', { name: 'Collapse Show S01', exact: true }).click()
  await expect(list.locator('[data-job]')).toHaveCount(2)
  await expect(page.getByText('Showing 1–3 of 3 rows (5 jobs)')).toBeVisible()
  await page.locator('[data-job="job-0"]').press('ArrowDown') // the arrows skip a collapsed group
  await expect(page.locator('[data-job="job-4"]')).toBeFocused()
  await page.locator('[data-job="job-4"]').press('Shift+ArrowUp') // ... a range takes all of it
  await expect(page.getByRole('status')).toContainText('5 selected')
  await list.getByRole('button', { name: 'Expand Show S01', exact: true }).click()
  await expect(list.locator('[data-job]')).toHaveCount(5)
  await page.getByRole('button', { name: 'Clear selection', exact: true }).click()

  // Out: above job-4's middle is after the group, not in it.
  await dragGrip(page, row(page, 'job-2'), row(page, 'job-4'), 0.25)
  await expect
    .poll(() => fixture.calls.find((c) => c.path === '/api/jobs/move')?.body)
    .toEqual({
      ids: ['job-2'],
      before: 'job-4',
      group: '',
    })
  await expect(list.getByText('2 jobs', { exact: true })).toBeVisible()

  // In: below a member's middle is in its group, even the last one's.
  await dragGrip(page, row(page, 'job-0'), row(page, 'job-3'), 0.75)
  await expect
    .poll(() => fixture.calls.filter((c) => c.path === '/api/jobs/move').at(-1)?.body)
    .toEqual({
      ids: ['job-0'],
      before: 'job-2',
      group: 'g1',
    })
  await expect(list.getByText('3 jobs', { exact: true })).toBeVisible()
  expect(fixture.jobs.map((j) => j.id)).toEqual(['job-1', 'job-3', 'job-0', 'job-2', 'job-4'])

  // Esc drops nothing.
  const moves = fixture.calls.filter((c) => c.path === '/api/jobs/move').length
  const grip = (await row(page, 'job-4').locator('[title^="Drag to move"]').boundingBox())!
  await page.mouse.move(grip.x + 4, grip.y + 4)
  await page.mouse.down()
  await page.mouse.move(grip.x + 4, grip.y - 60, { steps: 5 })
  await page.keyboard.press('Escape')
  await page.mouse.up()
  expect(fixture.calls.filter((c) => c.path === '/api/jobs/move')).toHaveLength(moves)

  // A drag on the row itself still selects the rows it crosses.
  const a = (await page.locator('[data-job="job-1"]').boundingBox())!
  const b = (await page.locator('[data-job="job-0"]').boundingBox())!
  // (clear of the name, whose tooltip would open over the next row)
  await page.mouse.move(a.x + a.width * 0.6, a.y + a.height / 2)
  await page.mouse.down()
  await page.mouse.move(b.x + b.width * 0.6, b.y + b.height / 2, { steps: 6 })
  await page.waitForTimeout(50) // a frame for the selection to reach the last row
  await page.mouse.up()
  await expect(page.getByRole('status')).toContainText('3 selected')
  expect(fixture.errors).toEqual([])
})

test('Group selected names the group after its folder; its menu renames and ungroups it', async ({ page }) => {
  const fixture = await queueFixture(page, 4, ['ready']) // job-0 and job-1 in Season1, the others in Season2
  await page.locator('[data-job="job-0"]').click()
  await page.locator('[data-job="job-1"]').click({ modifiers: ['ControlOrMeta'] })
  await page.getByRole('button', { name: 'Group the selected jobs', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Group 2 jobs' })
  await expect(dialog.getByRole('textbox', { name: 'Group name' })).toHaveValue('Show Season1')
  await dialog.getByRole('button', { name: 'Group', exact: true }).click()
  await expect
    .poll(() => fixture.calls.find((c) => c.path === '/api/jobs/group')?.body)
    .toEqual({ ids: ['job-0', 'job-1'], name: 'Show Season1' })
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await list.getByRole('button', { name: 'Show Season1 options', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Rename…' }).click()
  const rename = page.getByRole('dialog', { name: 'Rename the group' })
  await rename.getByRole('textbox', { name: 'Group name' }).fill('Extras')
  await rename.getByRole('button', { name: 'Rename', exact: true }).click()
  await expect(list.getByRole('button', { name: 'Collapse Extras', exact: true })).toBeVisible()
  await list.getByRole('button', { name: 'Extras options', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Ungroup' }).click()
  await expect(list.getByRole('button', { name: 'Collapse Extras', exact: true })).toHaveCount(0)
  expect(fixture.calls.map((c) => c.path)).toEqual(
    expect.arrayContaining(['/api/groups/g-new/rename', '/api/groups/g-new/ungroup']),
  )
  expect(fixture.errors).toEqual([])
})

test('a first drag-select keeps the list still, so it ends on the row under the pointer', async ({ page }) => {
  const { errors } = await queueFixture(page, 6, ['ready'])
  await expect(page.getByRole('status')).toContainText('0 selected')
  const first = page.locator('[data-job="job-1"]')
  const before = (await first.boundingBox())!
  const end = (await page.locator('[data-job="job-3"]').boundingBox())!
  await page.mouse.move(before.x + before.width * 0.6, before.y + before.height / 2)
  await page.mouse.down()
  await page.mouse.move(end.x + end.width * 0.6, end.y + end.height / 2, { steps: 6 })
  await page.waitForTimeout(50)
  await page.mouse.up()
  await expect(page.getByRole('status')).toContainText('3 selected')
  await expect(page.getByRole('button', { name: 'Clear selection', exact: true })).toBeVisible()
  expect((await first.boundingBox())!.y).toBe(before.y) // Clear selection showing up moved nothing
  expect(errors).toEqual([])
})

test("a group's menu moves the selected jobs into it or out of it, and a drop that changes nothing sends nothing", async ({
  page,
}) => {
  const fixture = await queueFixture(page, 4, ['ready'])
  for (const j of fixture.jobs.slice(1, 3)) [j.group, j.group_name] = ['g1', 'Show S01']
  fixture.refresh()
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await expect(list.getByText('2 jobs', { exact: true })).toBeVisible()
  const moves = () => fixture.calls.filter((c) => c.path === '/api/jobs/move').map((c) => c.body)

  // Its own place: no line, no request.
  await dragGrip(page, row(page, 'job-1'), row(page, 'job-1'), 0.25)
  await page.waitForTimeout(100)
  expect(moves()).toEqual([])

  await page.locator('[data-job="job-3"]').click()
  await list.getByRole('button', { name: 'Show S01 options', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Move the selected job here' }).click()
  await expect.poll(moves).toEqual([{ ids: ['job-3'], before: null, group: 'g1' }])
  await expect(list.getByText('3 jobs', { exact: true })).toBeVisible()

  await list.getByRole('button', { name: 'Show S01 options', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'Move the selected job here' })).toHaveCount(0)
  await page.getByRole('menuitem', { name: 'Take the selected job out' }).click()
  await expect.poll(() => moves().at(-1)).toEqual({ ids: ['job-3'], before: null, group: '' })
  await expect(list.getByText('2 jobs', { exact: true })).toBeVisible()
  expect(fixture.errors).toEqual([])
})

/** After queueFixture: serve job-0's detail with `change` made to it, for every request the editor sends. */
async function withDetail(page: Page, change: (d: JobDetail) => void) {
  const detail: JobDetail = await page.evaluate(() => fetch('/api/jobs/job-0').then((r) => r.json()))
  change(detail)
  await page.route('**/api/jobs/job-0', (route) => route.fulfill({ json: detail }))
  return detail
}

const PQ: VideoColor = {
  primaries: 'bt2020',
  transfer: 'smpte2084',
  matrix: 'bt2020nc',
  range: 'limited',
  chroma_loc: null,
  master_display: '',
  max_cll: 0,
  max_fall: 0,
}
const DV_HDR10PLUS: VideoHdr = {
  dv_profile: 8,
  dv_compat: 1,
  dv_level: 6,
  dv_layers: 'BL+RPU',
  dv_el: '',
  dv_stream: 0,
  hdr10plus: true,
}
const tracks = (hdr?: VideoHdr): Tracks => ({
  video: { width: 3840, height: 2160, start_ms: 0, default_duration_ns: null, sar_num: 1, sar_den: 1, color: PQ, hdr },
  audio: [],
  subs: [],
  has_chapters: false,
  count: 1,
})

test('Encoder: Advanced settings starts closed, counts what differs from the defaults, and stays as it was left', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 2, ['ready'])
  await withDetail(page, (d) =>
    Object.assign(d.spec.encoder, {
      options: { 'aq-mode': '3', 'psy-rd': '2.0' },
      extra: '--bogus 1',
      source_color: false,
    }),
  )
  await page.route('**/api/config/video-options/x265', (route) =>
    route.fulfill({
      json: {
        dashes: '--',
        options: [
          { name: 'aq-mode', help: 'AQ mode' },
          { name: 'psy-rd', help: 'Psy-RD strength' },
        ],
      },
    }),
  )
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const advanced = page.locator('summary').filter({ hasText: 'Advanced settings' })
  const color = page.getByRole('checkbox', { name: 'Color from the source', exact: true })
  // Two options, the extra arguments and Color from the source off; x265's help doesn't list --bogus.
  await expect(advanced).toHaveText('Advanced settings (4) · 1 warning')
  await expect(color).toBeHidden()
  await advanced.click()
  await expect(color).toBeVisible()
  await expect(advanced).toHaveText('Advanced settings')

  await page.reload()
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  await expect(color).toBeVisible()
  // The Queue's multi-job panel shows the same section, and it's open there too.
  await page.goto('/#/queue')
  await page.locator('[data-job="job-0"]').click()
  await page.locator('[data-job="job-1"]').click({ modifiers: ['Shift'] })
  const panel = page.getByRole('region', { name: 'Job settings', exact: true })
  await expect(panel.getByRole('checkbox', { name: 'Color from the source', exact: true })).toBeVisible()
  await panel.locator('summary').filter({ hasText: 'Advanced settings' }).click()
  await expect(panel.getByRole('checkbox', { name: 'Color from the source', exact: true })).toBeHidden()
  await page.locator('[data-job="job-0"]').click()
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  await expect(color).toBeHidden()
  expect(errors).toEqual([])
})

test('Encoder: HDR10+ and Dolby Vision sit in an HDR section that shows when the source has either', async ({
  page,
}, testInfo) => {
  const fixture = await queueFixture(page, 1, ['ready'])
  const detail = await withDetail(page, (d) => {
    d.tracks = tracks(DV_HDR10PLUS)
    d.color_args = ['--colorprim', 'bt2020', '--transfer', 'smpte2084', '--colormatrix', 'bt2020nc']
    d.spec.encoder.depth = 8
  })
  await page.route('**/api/config/video-options/x264', (route) =>
    route.fulfill({ json: { dashes: '--', options: [] } }),
  )
  await page.goto('/#/queue/job-0')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const hdr10plus = page.getByRole('checkbox', { name: /^HDR10\+ from the source/ })
  const dv = page.getByRole('checkbox', { name: /^Dolby Vision from the source/ })
  const label = page.getByText('HDR', { exact: true })
  const tenBit = page.getByText('An HDR source: encode it at 10-bit.', { exact: true })
  // With Advanced settings closed, the HDR section and the 10-bit note still show, in order under Bit depth.
  await expect(page.locator('summary').filter({ hasText: 'Advanced settings' })).toHaveText('Advanced settings')
  await expect(hdr10plus).toBeVisible()
  await expect(dv).toBeVisible()
  const depth = (await page.getByRole('combobox', { name: 'Bit depth' }).boundingBox())!
  const note = (await tenBit.boundingBox())!
  const section = (await label.boundingBox())!
  const summary = (await page.locator('summary').filter({ hasText: 'Advanced settings' }).boundingBox())!
  expect(note.y).toBeGreaterThanOrEqual(depth.y + depth.height)
  expect(section.y).toBeGreaterThan(note.y)
  expect(summary.y).toBeGreaterThan(section.y)
  await page.getByRole('tabpanel').screenshot({ path: testInfo.outputPath('encoder-hdr.png') })

  // A source without HDR10+ or Dolby Vision, and one whose tracks aren't read yet: no HDR section.
  detail.tracks = tracks()
  fixture.refresh()
  await expect(hdr10plus).toBeHidden()
  await expect(label).toBeHidden()
  detail.tracks = null
  fixture.refresh()
  await expect(page.getByText('The source has no HDR10+.')).toHaveCount(0)
  await expect(hdr10plus).toBeHidden()

  // An encoder that can't carry them: the section holds only what the source loses.
  detail.tracks = tracks(DV_HDR10PLUS)
  detail.spec.encoder.encoder = 'x264'
  fixture.refresh()
  await expect(page.getByText(/can't carry the source's Dolby Vision and HDR10\+/)).toBeVisible()
  await expect(hdr10plus).toBeHidden()
  expect(fixture.errors).toEqual([])
})

test('Encoder: with no one source, the HDR section shows for the encoders that carry HDR10+ and Dolby Vision', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 2, ['ready'])
  await page.locator('[data-job="job-0"]').click()
  await page.locator('[data-job="job-1"]').click({ modifiers: ['Shift'] })
  const panel = page.getByRole('region', { name: 'Job settings', exact: true })
  await expect(panel.getByRole('checkbox', { name: /^HDR10\+ from the source/ })).toBeVisible()
  await expect(panel.getByRole('checkbox', { name: /^Dolby Vision from the source/ })).toBeVisible()
  await expect(panel.getByText('HDR', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('More actions holds Save job files, Add jobs from job files and Read tracks again', async ({ page }) => {
  const { errors } = await queueFixture(page, 3, ['ready'])
  const reprobed: string[][] = []
  await page.route('**/api/jobs/reprobe', async (route) => {
    reprobed.push(route.request().postDataJSON().ids)
    await route.fulfill({ json: { ids: [] } })
  })
  for (const gone of [
    'Save job files of the selected jobs',
    'Add jobs from job files',
    "Read the selected jobs' tracks again",
  ])
    await expect(page.getByRole('button', { name: gone, exact: true })).toHaveCount(0)
  const more = page.getByRole('button', { name: 'More actions', exact: true })
  // Adding jobs needs no selection; the other two act on the selected jobs.
  await more.click()
  await expect(page.getByRole('menuitem', { name: 'Save job files', exact: true })).toBeDisabled()
  await expect(page.getByRole('menuitem', { name: 'Add jobs from job files…', exact: true })).toBeEnabled()
  await expect(page.getByRole('menuitem', { name: 'Read tracks again', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await page.locator('[data-job="job-1"]').click()
  await more.click()
  await expect(page.getByRole('menuitem', { name: 'Save job files', exact: true })).toBeEnabled()
  await page.getByRole('menuitem', { name: 'Read tracks again', exact: true }).click()
  await expect.poll(() => reprobed).toEqual([['job-1']])
  expect(errors).toEqual([])
})

test('the key hint is for screen readers only, and still describes the list', async ({ page }) => {
  const { errors } = await queueFixture(page, 3, ['ready'])
  const list = page
    .getByRole('region', { name: 'Queue list', exact: true })
    .getByRole('group', { name: 'Matching jobs', exact: true })
  await expect(list).toHaveAccessibleDescription(/Arrow keys, Home and End move through the list/)
  const hint = (await page.locator('#queue-keys').boundingBox())!
  expect(hint.width * hint.height).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

test("a queue row and its rail button count the job's errors and warnings instead of naming one", async ({ page }) => {
  const fixture = await queueFixture(page, 3, ['ready'])
  Object.assign(fixture.jobs[0], {
    status: 'blocked',
    issue: 'The output file is shared with another job',
    issue_counts: { block: 1, warn: 2 },
  })
  Object.assign(fixture.jobs[1], {
    status: 'warn',
    issue: 'The output file exists',
    issue_counts: { block: 0, warn: 1 },
  })
  Object.assign(fixture.jobs[2], {
    status: 'warn',
    issue: 'The output file exists',
    issue_counts: { block: 0, warn: 2 },
  })
  fixture.refresh()
  const rows = page.getByRole('region', { name: 'Queue list', exact: true })
  // A blocked row's status is its error count; its warnings follow as a compact mark.
  await expect(rows.locator('[data-job="job-0"]')).toContainText('1 error')
  await expect(rows.locator('[data-job="job-0"]').getByRole('img', { name: '2 warnings' })).toBeVisible()
  // A warn row's status is its warning count, so the old "Warning" word and the line under it are gone.
  await expect(rows.locator('[data-job="job-1"]').getByText('1 warning', { exact: true })).toBeVisible()
  await expect(rows.locator('[data-job="job-2"]').getByText('2 warnings', { exact: true })).toBeVisible()
  await expect(rows.locator('[data-job="job-1"]').getByText('Warning', { exact: true })).toHaveCount(0)
  await expect(rows.locator('[data-job="job-1"]')).not.toContainText('Ready')
  await expect(rows.getByText('The output file is shared with another job')).toHaveCount(0)

  await page.getByRole('button', { name: 'Collapse the queue list', exact: true }).click()
  await page.getByRole('region', { name: 'Queue rail', exact: true }).locator('[data-job="job-0"]').hover()
  await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText('Episode 00000: Blocked (1 error, 2 warnings)')
  expect(fixture.errors).toEqual([])
})

test('a row is two lines: the name and status, then one facts line that truncates but keeps its text', async ({
  page,
}) => {
  const long = (i: number) => ({
    resolution: '3840x2160',
    duration_ms: 3_600_000 + i,
    hdr: ['HDR10', 'Dolby Vision 7?'],
    interlaced: true,
  })
  const fixture = await queueFixture(page, 3, ['warn', 'queued', 'ready'], null, null, null, long)
  fixture.jobs[0].issue_counts = { block: 0, warn: 1 }
  fixture.jobs[1].issue_counts = { block: 0, warn: 1 }
  Object.assign(fixture.jobs[2], { custom_script: true, audio: ['a', 'b', 'c'], subs: 4 })
  fixture.refresh()
  const rows = page.getByRole('region', { name: 'Queue list', exact: true })
  const warn = rows.locator('[data-job="job-0"]')
  await expect(warn.getByText('1 warning', { exact: true })).toBeVisible()
  // The row's own padding plus its two lines (the name line, the facts line and its margin), so a third line fails.
  for (const id of ['job-0', 'job-1']) {
    const [height, expected] = await rows.locator(`[data-job="${id}"]`).evaluate((el) => {
      const css = getComputedStyle(el)
      const facts = el.querySelector<HTMLElement>('.readout')!
      return [
        el.getBoundingClientRect().height,
        parseFloat(css.paddingTop) +
          parseFloat(css.paddingBottom) +
          el.firstElementChild!.getBoundingClientRect().height +
          facts.getBoundingClientRect().height +
          parseFloat(getComputedStyle(facts).marginTop),
      ]
    })
    expect(height).toBeLessThanOrEqual(expected + 1)
  }
  // A Dolby Vision profile 7 row carries the note in its accessible name, once.
  const dv7 = await rows.locator('[data-job="job-2"]').evaluate((el) => el.textContent!)
  expect(dv7.match(/dovi_tool/g)).toHaveLength(1)
  await expect(rows.getByRole('button', { name: /dovi_tool/ })).toHaveCount(3)
  // Queued keeps its status word and gets the compact mark, named for screen readers.
  const queued = rows.locator('[data-job="job-1"]')
  await expect(queued).toContainText('Queued')
  await expect(queued.getByRole('img', { name: '1 warning' })).toHaveText('1')
  // The facts line starts with the resolution and length, and holds the rest in the DOM.
  const facts = rows.locator('[data-job="job-2"] .readout')
  await expect(facts).toContainText(/^3840×2160 · 1:00:00 · interlaced/)
  await expect(facts).toContainText('Dolby Vision 7?')
  await expect(facts).toContainText('x265 · custom script · 3 audio · 4 subs')
  fixture.errors.length = 0
})

const HLG = "Dolby Vision 8.4 (HLG) isn't carried yet. Untick Dolby Vision from the source on the Encoder tab"

test('the job header counts the issues, and the Issues tab lists each one with its code', async ({
  page,
}, testInfo) => {
  const { errors } = await queueFixture(page, 1, ['blocked'])
  await withDetail(page, (d) => {
    d.issues = [
      { severity: 'block', code: 'hdr.dv_hlg', message: HLG },
      { severity: 'warn', code: 'video.option_unknown', message: "x265's help doesn't list --foo" },
      { severity: 'warn', code: 'name.token', message: 'The name template has an unknown token.' },
      { severity: 'info', code: 'video.color_source', message: "The source's color wins over the encoder options'" },
    ]
    d.issue_counts = { block: 1, warn: 2 }
  })
  await page.goto('/#/queue/job-0')
  const header = page.locator('header')
  // The header counts them: no messages, no codes.
  await expect(header).toContainText('1 error · 2 warnings')
  await expect(header).not.toContainText('hdr.dv_hlg')
  await expect(header).not.toContainText("isn't carried yet")
  const tab = page.getByRole('tab', { name: 'Issues 3', exact: true })
  await expect(tab).toHaveClass(/bg-destructive\/10/) // the worst issue's tint
  const jobTabs = page.getByRole('tablist', { name: 'Job sections', exact: true }).getByRole('tab')
  await expect(jobTabs.last()).toHaveAccessibleName('Issues 3') // after Log
  await header.screenshot({ path: testInfo.outputPath('issues-header.png') })

  await header.getByRole('button', { name: 'Open the Issues tab', exact: true }).click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
  await expect(header.getByRole('button', { name: 'Open the Issues tab', exact: true })).toHaveCount(0)
  const panel = page.getByRole('tabpanel', { name: 'Issues 3' })
  await expect(panel.getByRole('heading', { name: 'Errors' })).toBeVisible()
  await expect(panel.getByRole('heading', { name: 'Warnings' })).toBeVisible()
  const items = panel.getByRole('listitem')
  await expect(items).toHaveCount(3) // info notes stay out
  // A screen reader hears the kind first; a message gets its final period; the code follows.
  const said = (i: number) => items.nth(i).evaluate((el) => el.textContent!.replace(/\s+/g, ' ').trim())
  expect(await said(0)).toBe(`Error: ${HLG}. hdr.dv_hlg`)
  expect(await said(1)).toBe("Warning: x265's help doesn't list --foo. video.option_unknown")
  expect(await said(2)).toBe('Warning: The name template has an unknown token. name.token')
  await expect(items.nth(0).getByText(HLG, { exact: false })).toHaveCSS('color', await panelText(panel))
  await page.getByRole('tabpanel').screenshot({ path: testInfo.outputPath('issues-tab.png') })
  expect(errors).toEqual([])
})

test('each issue links to where it is fixed, after its message; one with no one place has no link', async ({
  page,
}) => {
  const { errors } = await queueFixture(page, 1, ['blocked'])
  const depth = 'An HDR source needs a 10-bit encode, or its gradients can band. Set the bit depth to 10'
  await withDetail(page, (d) => {
    d.issues = [
      {
        severity: 'block',
        code: 'tools.missing',
        message: 'MKV needs mkvmerge. Set it in Settings › Tools',
        tab: 'tools',
      },
      { severity: 'block', code: 'probe', message: "The source couldn't be read", tab: null },
      { severity: 'warn', code: 'hdr.depth', message: depth, tab: 'encoder' },
    ]
    d.issue_counts = { block: 2, warn: 1 }
  })
  await page.goto('/#/queue/job-0')
  const issues = page.getByRole('tab', { name: /^Issues/ })
  await issues.click()
  const items = page.getByRole('tabpanel').getByRole('listitem')
  await expect(items.nth(1).getByRole('button')).toHaveCount(0)
  const said = await items.nth(2).evaluate((el) => el.textContent!.replace(/\s+/g, ' ').trim())
  expect(said).toBe(`Warning: ${depth}. Go to the Encoder tab hdr.depth`)
  await items.nth(2).getByRole('button', { name: 'Go to the Encoder tab', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'Encoder', exact: true })).toHaveAttribute('aria-selected', 'true')

  await issues.click()
  expect(errors).toEqual([])
  // Settings › Tools: Settings opens on that category (its requests aren't this fixture's)
  await page.route('**/api/**', (route) => route.fulfill({ status: 404, json: {} }))
  await items.nth(0).getByRole('button', { name: 'Go to Settings › Tools', exact: true }).click()
  await expect(page).toHaveURL(/#\/settings$/)
  expect(await page.evaluate(() => localStorage.getItem('videoforge.settingsTab'))).toBe('tools')
})

for (const palette of ['gold', 'indigo', 'ocean', 'forest', 'ember', 'rose', 'slate'])
  for (const mode of ['light', 'dark'])
    test(`the Issues tab's tint and its list keep their contrast: ${palette}, ${mode}`, async ({ page }) => {
      await page.addInitScript(
        ([palette, mode]) => {
          localStorage.setItem('videoforge.palette', palette)
          localStorage.setItem('videoforge.mode', mode)
        },
        [palette, mode],
      )
      const fixture = await queueFixture(page, 1, ['blocked'])
      const detail = await withDetail(page, (d) => {
        d.issues = [
          { severity: 'block', code: 'hdr.dv_hlg', message: HLG },
          { severity: 'warn', code: 'name.token', message: 'The name template has an unknown token.' },
        ]
      })
      await page.goto('/#/queue/job-0')
      const contrast = async () =>
        (await page.waitForTimeout(300), // the tabs' colors fade in
        await new AxeBuilder({ page })
          .include('header')
          .include('#job-tab-panel')
          // the blocked job's dimmed Queue box: a disabled control, which WCAG leaves out
          .exclude('header label:has([role=checkbox][disabled])')
          .withRules(['color-contrast'])
          .analyze()).violations.flatMap((v) => v.nodes.map((n) => `${n.target.join(' ')}: ${n.any[0]?.message}`))
      const tab = page.getByRole('tab', { name: /^Issues/ })
      // An error's tint and a warning's, each while the tab is closed and while it's open.
      for (const issues of [detail.issues, detail.issues.slice(1)]) {
        detail.issues = issues
        fixture.refresh()
        await expect(tab).toHaveAccessibleName(`Issues ${issues.length}`)
        await page.getByRole('tab', { name: 'Video', exact: true }).click()
        expect(await contrast()).toEqual([])
        await tab.click()
        expect(await contrast()).toEqual([])
      }
      expect(fixture.errors).toEqual([])
    })

/** The tab panel's own text color: an issue's message is in it, not in red or yellow. */
async function panelText(panel: Locator) {
  return panel.evaluate((el) => getComputedStyle(el).color)
}

test('the Issues tab shows with issues, and stays saying none are left while it is open', async ({ page }) => {
  const fixture = await queueFixture(page, 1, ['warn'])
  const detail = await withDetail(page, (d) => {
    d.issues = [{ severity: 'warn', code: 'outfile.exists', message: 'The output file is already there' }]
    d.issue_counts = { block: 0, warn: 1 }
  })
  await page.goto('/#/queue/job-0')
  await expect(page.locator('header')).toContainText('Ready with warnings')
  const tab = page.getByRole('tab', { name: 'Issues 1', exact: true })
  await expect(tab).toHaveClass(/bg-warning\/10/)
  await tab.click()

  Object.assign(detail, { issues: [], issue_counts: { block: 0, warn: 0 }, status: 'ready' })
  fixture.refresh()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toHaveText('No issues left.')
  await expect(page.getByRole('button', { name: 'Open the Issues tab', exact: true })).toHaveCount(0)
  await page.getByRole('tab', { name: 'Video', exact: true }).click()
  await expect(page.getByRole('tab', { name: /^Issues/ })).toHaveCount(0)
  expect(fixture.errors).toEqual([])
})

test('removing one job says "Removed 1 job", and the menu says the work folders stay', async ({ page }) => {
  const { errors } = await queueFixture(page, 1)
  await page.getByRole('button', { name: 'Select matching jobs', exact: true }).click()
  await page.getByRole('button', { name: 'Remove', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'Remove and delete work folders' })).toBeVisible()
  await page.getByRole('menuitem', { name: 'Remove and keep work folders' }).click()
  await expect(page.getByText('Removed 1 job', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test("a group's shared facts show once on its header; its rows keep only their own", async ({ page }) => {
  const facts = (i: number) => ({
    resolution: '1920x1080',
    duration_ms: 1_500_000 + i * 60_000,
    hdr: [],
    interlaced: false,
  })
  const fixture = await queueFixture(page, 7, ['ready'], null, null, null, facts)
  for (const j of fixture.jobs) Object.assign(j, { encoder: 'x264 CRF 18', audio: ['a', 'b'], subs: 3 })
  for (const j of fixture.jobs.slice(0, 6)) [j.group, j.group_name] = ['g1', 'Show S01']
  fixture.refresh()
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  const header = list.locator('[data-row]').first()
  await expect(header.locator('.readout').last()).toHaveText('1920×1080 · x264 CRF 18 · 2 audio · 3 subs')
  await expect(header.locator('.readout').last()).toHaveCSS('text-overflow', 'ellipsis')
  // Its rows show their own length and not what the header says.
  const member = list.locator('[data-job="job-1"]')
  await expect(member.locator('.readout')).toHaveText('26:00')
  // A screen reader still hears the whole row: the shared facts are in its name, not on screen.
  await expect(member).toHaveAccessibleName(/26:00 · 1920×1080 · x264 CRF 18 · 2 audio · 3 subs/)
  // An ungrouped job keeps everything.
  await expect(list.locator('[data-job="job-6"] .readout')).toHaveText(
    '1920×1080 · 31:00 · x264 CRF 18 · 2 audio · 3 subs',
  )
  // A collapsed group still shows the shared line.
  await list.getByRole('button', { name: 'Collapse Show S01', exact: true }).click()
  await expect(header.locator('.readout').last()).toContainText('x264 CRF 18')
  expect(fixture.errors).toEqual([])
})

test('a row with nothing left to say after its group is one line', async ({ page }) => {
  const fixture = await queueFixture(page, 3, ['ready'])
  for (const j of fixture.jobs) [j.group, j.group_name] = ['g1', 'Show S01']
  fixture.refresh()
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  await expect(list.locator('[data-row]').first().locator('.readout').last()).toHaveText('x265 · 0 audio · 0 subs')
  await expect(list.locator('[data-job="job-0"] .readout')).toHaveCount(0)
})

test('a group named for its count does not repeat the count in its header', async ({ page }) => {
  const fixture = await queueFixture(page, 6, ['ready'])
  for (const j of fixture.jobs) [j.group, j.group_name] = ['g1', '6 jobs']
  fixture.refresh()
  const list = page.getByRole('region', { name: 'Queue list', exact: true })
  const header = list.locator('[data-row]').first()
  await expect(header.getByRole('button', { name: '6 jobs: select its 6 jobs' })).toBeVisible()
  await expect(header.getByText('6 jobs', { exact: true })).toHaveCount(1)
  fixture.jobs[0].status = 'done'
  fixture.refresh()
  await expect(header).toContainText('1 done')
  await expect(header.getByText('6 jobs', { exact: true })).toHaveCount(1)
})

test('at 390 px a group header cuts its name and shared line, never its counts', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const fixture = await queueFixture(page, 3, ['done'], null, null, null, () => ({
    resolution: '3840x2160',
    duration_ms: 3_600_000,
    hdr: ['HDR10', 'DV 7.6 FEL/MEL?'],
    interlaced: false,
  }))
  for (const j of fixture.jobs) [j.group, j.group_name] = ['g1', 'A season with a very long name to cut off']
  fixture.refresh()
  const header = page.getByRole('region', { name: 'Queue list', exact: true }).locator('[data-row]').first()
  await expect(header.getByText('all done', { exact: true })).toBeVisible()
  const cut = await header.evaluate((el) => {
    const over = (e: Element) => e.scrollWidth > e.clientWidth
    return {
      counts: over(el.querySelector('.ml-auto')!),
      name: over(el.querySelector('.truncate')!),
      line: over(el.querySelector('.readout.truncate')!),
    }
  })
  expect(cut).toEqual({ counts: false, name: true, line: true })
  await expect(header.locator('.readout.truncate')).toContainText(/^3840×2160 · 1:00:00/)
})
