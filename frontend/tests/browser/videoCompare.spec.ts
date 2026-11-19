import { test, expect, type Page } from '@playwright/test'
import type { JobDetail, JobSummary } from '../../src/lib/types.ts'

// The Video tab's preview: the compare (always offered, with what each needs), the filters' before and after,
// the split view, bookmarks, and going to a time. Frames are SVGs, one colour per stage, so each side is known.
const FRAMES = 240
const COLOURS: Record<string, string> = { crop: '#204060', output: '#204060', unfiltered: '#a03020' }

async function fixture(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const frames: string[] = [] // each frame request's stage:n
  const job: JobSummary = {
    id: 'job-0',
    name: 'Show S01E01',
    label: '',
    source: 'D:\\Media\\Show.S01E01.mkv',
    rule_set: 'manual',
    status: 'ready',
    progress: null,
    issue: '',
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
  }
  const detail: JobDetail = {
    ...job,
    issues: [],
    steps: {},
    made: null,
    plan: null,
    tracks: null,
    output_name: null,
    output_title: null,
    color_args: null,
    target: null,
    sample: null,
    search: null,
    compare: { encode: false, sample: false, filters: true },
    spec: {
      id: job.id,
      rule_set: 'manual',
      inputs: { source: job.source, encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
      video: {
        source_filter: 'ffms2',
        crop: { left: 0, top: 0, right: 0, bottom: 0 },
        resize: null,
        filters: [
          { category: 'crop', name: 'Crop', script: '', enabled: true },
          { category: 'deband', name: 'Deband', script: 'clip = deband(clip)', enabled: true },
          { category: 'resize', name: 'Resize', script: '', enabled: true },
        ],
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
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const stage = url.searchParams.get('stage') ?? 'output'
    if (path.endsWith('/video/frame')) {
      frames.push(`${stage}:${url.searchParams.get('n')}`)
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="36"><rect width="64" height="36" fill="${COLOURS[stage]}"/></svg>`
      return route.fulfill({ body: svg, contentType: 'image/svg+xml', headers: { 'X-Frame-Type': 'I' } })
    }
    let json: unknown
    if (path === '/api/jobs') json = [job]
    else if (path === '/api/health') json = { ok: true, version: 'test' }
    else if (path === '/api/profiles') json = { profiles: [{ id: 'default', name: 'Default' }], active: 'default' }
    else if (path === '/api/presets')
      json = { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] }
    else if (path === '/api/jobs/job-0') json = detail
    else if (path === '/api/jobs/job-0/log-snapshot') json = { seq: 0, steps: [], lines: [] }
    else if (path === '/api/jobs/job-0/video/info')
      json = { frames: FRAMES, width: 64, height: 36, fps_num: 24, fps_den: 1, format: 'YUV420P10', bits: 10, fps: 24 }
    else if (path === '/api/config/video-options/x265') json = { dashes: '--', options: [] }
    else if (['/api/rule-sets', '/api/config/encoders', '/api/filter-presets'].includes(path)) json = []
    else return route.fulfill({ status: 404, json: { detail: `not mocked: ${path}` } })
    await route.fulfill({ json })
  })
  await page.goto('/#/queue')
  await page.locator('[data-job="job-0"]').click()
  await expect(page.getByRole('tab', { name: 'Video', exact: true })).toHaveAttribute('aria-selected', 'true')
  return { errors, frames }
}

test('compare is always offered, saying what each choice needs', async ({ page }) => {
  const { errors } = await fixture(page)
  const compare = page.getByRole('combobox', { name: 'Compare', exact: true })
  await expect(compare).toBeVisible()
  await expect(compare.locator('option[value="filters"]')).toBeEnabled()
  await expect(compare.locator('option[value="sample"]')).toBeDisabled()
  await expect(compare.locator('option[value="sample"]')).toHaveText(
    'Compare: test encode (run one on the Encoder tab)',
  )
  await expect(compare.locator('option[value="encode"]')).toBeDisabled()
  expect(errors).toEqual([])
})

test("the filters' compare flips and splits the frame before and after them", async ({ page }) => {
  const { errors, frames } = await fixture(page)
  await page.getByRole('combobox', { name: 'Compare', exact: true }).selectOption('filters')
  await expect(page.getByText('After filters · C flips')).toBeVisible()
  await expect.poll(() => frames.includes('unfiltered:0') && frames.includes('output:0')).toBe(true)

  // Flips show the kept frames: each side was loaded once.
  await page.getByRole('radio', { name: 'Before', exact: true }).click()
  await page.getByRole('radio', { name: 'After', exact: true }).click()
  await page.getByRole('radio', { name: 'Before', exact: true }).click()
  await expect(page.getByText('Before filters · C flips')).toBeVisible()
  expect(frames.filter((f) => f === 'unfiltered:0' || f === 'output:0').sort()).toEqual(['output:0', 'unfiltered:0'])

  // Split: the picked side left of the line, the other right of it, both at this frame.
  await page.getByRole('button', { name: 'Split', exact: true }).click()
  await expect(page.getByText('Left: Before filters · Right: After filters · C swaps')).toBeVisible()
  await expect(page.getByRole('application').locator('[data-compare-notice]')).toHaveCount(0) // by the buttons, off the frame
  const line = page.getByRole('slider', { name: 'Split line', exact: true })
  await expect(line).toHaveAttribute('aria-valuenow', '50')
  await expect(page.getByRole('img', { name: 'The other side of frame 0' })).toBeVisible()
  await line.focus()
  await page.keyboard.press('Shift+ArrowLeft')
  await expect(line).toHaveAttribute('aria-valuenow', '40')
  const box = (await page.getByRole('img', { name: 'Frame 0', exact: true }).boundingBox())!
  await line.hover()
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height / 2)
  await page.mouse.up()
  await expect(line).toHaveAttribute('aria-valuenow', '75')
  expect(errors).toEqual([])
})

test('bookmarks mark frames on the scrub bar, and [ and ] go between them; a time goes to its frame', async ({
  page,
}) => {
  const { errors } = await fixture(page)
  const viewport = page.getByRole('application')
  const box = page.getByRole('textbox', { name: 'Frame number or time', exact: true })
  await viewport.focus()
  await page.keyboard.press('m')
  await expect(page.locator('[data-mark="0"]')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Bookmark this frame' })).toHaveAttribute('aria-pressed', 'true')

  await box.fill('0:05')
  await box.press('Enter')
  await expect(box).toHaveValue('120')
  await page.getByRole('button', { name: 'Bookmark this frame' }).click()
  await expect(page.locator('[data-mark]')).toHaveCount(2)

  await viewport.focus()
  await page.keyboard.press('Home')
  await page.keyboard.press(']')
  await expect(box).toHaveValue('120')
  await page.keyboard.press('[')
  await expect(box).toHaveValue('0')

  // Kept in this browser: a reload brings them back.
  await page.reload()
  await page.locator('[data-job="job-0"]').click()
  await expect(page.locator('[data-mark]')).toHaveCount(2)
  expect(errors).toEqual([])
})

test('the preview and the script check show their figures in the code font', async ({ page }) => {
  const { errors } = await fixture(page)
  // The script and a passing check, so the Video tab shows the check's grid of figures.
  const script = { script: 'video.vpy', head: ['clip = src'], body: [], tail: ['clip.set_output()'], custom: false }
  const info = { frames: 240, width: 64, height: 36, fps_num: 24, fps_den: 1, format: 'YUV420P10', bits: 10, fps: 24 }
  await page.route('**/api/jobs/job-0/video/script', (route) => route.fulfill({ json: script }))
  await page.route('**/api/jobs/job-0/video/check', (route) => route.fulfill({ json: { ok: true, info } }))
  await page.reload()
  const mono = /^"?Cascadia Mono/
  const sizeLine = page.getByText(/^64×36 · \d+%/)
  await expect(sizeLine).toHaveCSS('font-family', mono) // the frame's size and zoom
  // The wider code font still fits the preview's toolbar at 1280 px.
  await page.setViewportSize({ width: 1280, height: 800 })
  const fits = await sizeLine.evaluate((el) => {
    const bar = el.parentElement!
    return (
      el.getBoundingClientRect().right <= bar.getBoundingClientRect().right + 1 && bar.scrollWidth <= bar.clientWidth
    )
  })
  expect(fits).toBe(true)
  await expect(page.getByText(/^\/ \d+ · /)).toHaveCSS('font-family', mono) // the frame count and time
  // The frame controls fit their row at every width the layout gives them (352 px at 1440, 512 at 1600),
  // and squeezed by the splitter, where previous, the slider and next share the first line above the rest.
  const controls = page
    .getByRole('textbox', { name: 'Frame number or time', exact: true })
    .locator('xpath=ancestor::div[contains(@class, "@container")][1]/div')
  for (const width of [1280, 1440, 1600, 1920]) {
    await page.setViewportSize({ width, height: 800 })
    await expect.poll(() => controls.evaluate((row) => row.scrollWidth <= row.clientWidth)).toBe(true)
  }
  for (const width of ['220px', '300px', '400px']) {
    await controls.evaluate((row, w) => (row.parentElement!.style.width = w), width)
    await expect
      .poll(() =>
        controls.evaluate((row) => {
          const box = (sel: string) => row.querySelector(sel)!.getBoundingClientRect()
          const slider = box('input[type=range]')
          const mid = (r: DOMRect) => r.top + r.height / 2
          const [prev, next, field] = [
            box('[aria-label="Previous frame"]'),
            box('[aria-label="Next frame"]'),
            box('[aria-label="Frame number or time"]'),
          ]
          return (
            row.scrollWidth <= row.clientWidth &&
            prev.right <= slider.left &&
            slider.right <= next.left &&
            Math.abs(mid(prev) - mid(slider)) < 2 &&
            Math.abs(mid(next) - mid(slider)) < 2 &&
            slider.bottom <= field.top
          )
        }),
      )
      .toBe(true)
  }
  await controls.evaluate((row) => (row.parentElement!.style.width = ''))
  await page.setViewportSize({ width: 1280, height: 800 })
  // The script check (on the Script side tab): its values are figures, its labels stay in the normal font.
  await page.getByRole('tab', { name: 'Script', exact: true }).click()
  const label = page.getByText('Size', { exact: true })
  const size = label.locator('xpath=..') // the label's row: "Size 64×36"
  await expect(size).toContainText('64×36')
  await expect(size.locator('.readout')).toHaveText('64×36')
  await expect(size.locator('.readout')).toHaveCSS('font-family', mono)
  await expect(label).not.toHaveCSS('font-family', mono)
  expect(errors).toEqual([])
})
