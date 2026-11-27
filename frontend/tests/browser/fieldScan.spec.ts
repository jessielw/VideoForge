import { test, expect, type Page } from '@playwright/test'
import type { FieldScanView, JobDetail, JobSummary } from '../../src/lib/types.ts'

// The Video tab's Scan section: the field scan's verdict, its strip and numbers, and Apply, which saves the
// scan's chain as the Field step with the pulldown flags applied (a soft-telecined DVD on FFMS2 moves to
// BestSource). Before a scan, a button puts the job in the index lane; during it (after the index), the job is
// open to edits and the section shows the scan's progress.
const HYBRID: FieldScanView = {
  report: {
    verdict: 'hybrid',
    order: 'tff',
    stream_order: '',
    frames: 41928,
    fps_num: 30000,
    fps_den: 1001,
    moving: 13280,
    combed: 5065,
    left_tff: 1267,
    left_bff: 4963,
    fallback: 2146,
    cadence: 0.69,
    jitter: 1.45,
    strip: 'TTTT..TTIhTT',
    stretches: [
      [7240, 7480, 35],
      [9000, 9010, 4],
    ],
    seconds: 18,
    chunk: 30,
    version: 1,
  },
  label: 'Telecined film with combed parts',
  summary: 'Telecined film with combed parts, top field first (2146 frames left combed)',
  mismatch: false,
  fix: {
    step: {
      category: 'field',
      name: 'Field scan: IVTC + QTGMC',
      script: 'clip = core.vivtc.VFM(clip, order=1)',
      enabled: true,
    },
    pulldown: true,
    source_filter: 'bestsource',
    applied: false,
  },
}

async function fixture(
  page: Page,
  fieldScan: FieldScanView,
  over: Partial<JobSummary> = {},
  specOver: Partial<JobDetail['spec']> = {},
) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const saved: unknown[] = []
  const job: JobSummary = {
    id: 'job-0',
    name: 'Show S01E01',
    label: '',
    group: null,
    group_name: '',
    source: 'D:\\Media\\Show.S01E01.mkv',
    rule_set: 'manual',
    status: 'ready',
    progress: null,
    issue: '',
    issue_counts: { block: 0, warn: 0 },
    output: null,
    encoder: 'x265',
    crop: null,
    custom_script: false,
    pause_after_pass1: false,
    indexed: true,
    source_facts: null,
    index_error: '',
    index_held: false,
    sample_waiting: false,
    sample_error: '',
    searching: false,
    search_error: '',
    audio: [],
    subs: 0,
    ...over,
  }
  const detail = {
    ...job,
    issues: [],
    steps: {},
    made: null,
    plan: null,
    tracks: {
      video: {
        width: 720,
        height: 480,
        start_ms: 0,
        default_duration_ns: 33366667,
        sar_num: 8,
        sar_den: 9,
        scan_type: 'Progressive',
        scan_order: '2:3 Pulldown',
        color: {},
      },
      audio: [],
      subs: [],
      has_chapters: false,
      count: 0,
    },
    output_name: null,
    output_title: null,
    color_args: null,
    target: null,
    sample: null,
    search: null,
    compare: { encode: false, sample: false, filters: false },
    field_scan: fieldScan,
    spec: {
      id: job.id,
      rule_set: 'manual',
      inputs: { source: job.source, encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
      video: {
        source_filter: 'ffms2',
        crop: { left: 0, top: 0, right: 0, bottom: 0 },
        resize: null,
        filters: [
          { category: 'field', name: 'Bwdif', script: 'clip = core.bwdif.Bwdif(clip, field=1)', enabled: true },
          { category: 'crop', name: 'Crop', script: '', enabled: true },
          { category: 'resize', name: 'Resize', script: '', enabled: true },
        ],
        custom: null,
        pulldown: false,
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
      ...specOver,
    },
  } as unknown as JobDetail
  const indexed: unknown[] = []
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/video/frame')) {
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="36"><rect width="64" height="36"/></svg>'
      return route.fulfill({ body: svg, contentType: 'image/svg+xml', headers: { 'X-Frame-Type': 'I' } })
    }
    let json: unknown
    if (path === '/api/jobs') json = [job]
    else if (path === '/api/health') json = { ok: true, version: 'test' }
    else if (path === '/api/profiles') json = { profiles: [{ id: 'default', name: 'Default' }], active: 'default' }
    else if (path === '/api/presets')
      json = { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] }
    else if (path === '/api/jobs/job-0' && route.request().method() === 'PATCH') {
      saved.push(route.request().postDataJSON())
      json = detail
    } else if (path === '/api/jobs/job-0') json = detail
    else if (path === '/api/queue/index') {
      indexed.push(route.request().postDataJSON())
      json = { taken: ['job-0'] }
    } else if (path === '/api/jobs/job-0/log-snapshot') json = { seq: 0, steps: [], lines: [] }
    else if (path === '/api/jobs/job-0/video/info')
      json = { frames: 240, width: 64, height: 36, fps_num: 24, fps_den: 1, format: 'YUV420P8', bits: 8, fps: 24 }
    else if (path === '/api/config/video-options/x265') json = { dashes: '--', options: [] }
    else if (['/api/rule-sets', '/api/config/encoders', '/api/filter-presets'].includes(path)) json = []
    else return route.fulfill({ status: 404, json: { detail: `not mocked: ${path}` } })
    await route.fulfill({ json })
  })
  await page.goto('/#/queue')
  await page.locator('[data-job="job-0"]').click()
  await expect(page.getByRole('tab', { name: 'Video', exact: true })).toHaveAttribute('aria-selected', 'true')
  return { errors, saved, indexed }
}

test('the scan shows its verdict, and Apply saves its chain with pulldown on BestSource', async ({ page }) => {
  const { errors, saved } = await fixture(page, HYBRID)
  await expect(
    page.getByText('Telecined film with combed parts, top field first (2146 frames left combed)'),
  ).toBeVisible()
  await expect(page.getByRole('img', { name: 'Field scan, per second' })).toBeVisible()
  await expect(page.getByText('9.5% of 13280 moving frames left combed after field matching')).toBeVisible()
  await expect(page.getByText('Left combed: 4:02–4:10 (35 frames), 5:00–5:01 (4 frames).')).toBeVisible()
  await expect(
    page.getByText(
      'Apply adds Field scan: IVTC + QTGMC first in the chain, removes Bwdif, turns on Apply pulldown, switches the source filter to BestSource.',
    ),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Apply', exact: true }).click()
  await expect.poll(() => saved.length).toBeGreaterThan(0)
  const video = (saved.at(-1) as { video: JobDetail['spec']['video'] }).video
  expect(video.filters.map((s) => s.name)).toEqual(['Field scan: IVTC + QTGMC', 'Crop', 'Resize'])
  expect([video.pulldown, video.source_filter]).toEqual([true, 'bestsource'])
  expect(errors).toEqual([])
})

test('before a scan, a button puts the job in the index lane', async ({ page }) => {
  const { errors, indexed } = await fixture(page, { report: null })
  await expect(page.getByText('with the pulldown flags applied')).toBeVisible()
  await page.getByRole('button', { name: 'Scan fields' }).click()
  await expect.poll(() => indexed).toEqual([{ ids: ['job-0'], first: true }])
  expect(errors).toEqual([])
})

test('during the scan the job is open, and the section shows its progress', async ({ page }) => {
  const progress = { step: 'Field scan', index: 1, total: 2, fraction: 0.4, overall: 0.42, reused: false }
  const { errors } = await fixture(
    page,
    { report: null },
    { status: 'scanning', progress: { ...progress, fps: null, eta: null, elapsed: 8, left: 11 } },
  )
  await expect(page.locator('[data-job="job-0"]').getByText('Scanning fields')).toBeVisible()
  await expect(page.getByLabel('Field scan progress')).toContainText('42%')
  await expect(page.getByText('The job can be edited meanwhile')).toBeVisible()
  await expect(page.getByText(/locked/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Scan fields' })).toHaveCount(0)
  expect(errors).toEqual([])
})

test("a template's Field: Auto says the scan's step goes in once it's done", async ({ page }) => {
  const { errors } = await fixture(page, { report: null }, {}, { autofield: true })
  await expect(page.getByText("Field: Auto (from the template): the scan's Field step goes in")).toBeVisible()
  await expect(page.getByRole('button', { name: 'Scan fields' })).toBeVisible()
  expect(errors).toEqual([])
})
