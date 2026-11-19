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
  const files: string[] = [] // and the files it lists there
  const removed: Record<string, unknown>[] = []
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const request = route.request()
    if (path === '/api/fs/list')
      return route.fulfill({
        json: {
          path: 'D:/Media',
          parent: 'D:/',
          dirs: folders.map((p) => ({ name: p.slice(9), path: p, mtime: 1_700_000_000 })),
          files: files.map((p, i) => ({
            name: p.slice(9),
            path: p,
            size: [3, 1, 2][i % 3] * 1e9,
            mtime: 1_700_000_000 + i,
          })),
        },
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
  return { errors, sources, removed, files }
}

async function paste(page: Page, text: string) {
  await page.evaluate((t) => {
    const data = new DataTransfer()
    data.setData('text/plain', t)
    document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }))
  }, text)
}

test('Matched files keeps its size while the sources match again', async ({ page }) => {
  const { errors, sources } = await fixture(page, [])
  await paste(page, sources.map((p) => `"${p}"`).join(String.fromCharCode(13, 10)))
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  await expect(card).toContainText('2 job(s)')
  const before = (await card.boundingBox())!.height
  // Hold the next match, so the page stays in "Matching…" while it is measured.
  let release!: () => void
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/match', async (route) => (await held, await route.fallback()))
  await paste(page, '"D:/Media/Show.S01E03.mkv"')
  await expect(card).toContainText('Matching…')
  expect((await card.boundingBox())!.height).toBeGreaterThanOrEqual(Math.min(before, 192)) // no collapse to one line
  release()
  await expect(card.getByText('Show.S01E03.mkv')).toBeVisible()
  expect(errors).toEqual([])
})

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
  await expect(page.getByRole('checkbox', { name: 'Index', exact: true })).toHaveAccessibleDescription(
    '(indexes each job in the background for its preview)',
  )
  await page.getByRole('checkbox', { name: 'Index', exact: true }).click()
  await expect(bar).toContainText('will neither index nor crop')
  await bar.getByRole('button', { name: /Add 2 jobs/ }).click()

  await expect(bar.getByRole('status')).toContainText('Added 2 jobs')
  await expect(bar.getByRole('button', { name: 'Open queue' })).toBeVisible()
  expect(posted).toHaveLength(1)
  expect(posted[0]).toMatchObject({ auto_index: false, auto_crop: false, output_dir: 'D:/Output', rule_set: 'manual' })
  expect(posted[0].sources).toEqual(sources)

  await bar.getByRole('button', { name: 'Add more' }).click() // a clean form for the next batch
  await expect(bar).toContainText('Paste file paths on any page, or Browse')
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

test('the file picker ticks a range with Shift+click and every file with Ctrl+A or the All box', async ({ page }) => {
  const { errors, files } = await fixture(page, [])
  files.push(...[1, 2, 3, 4, 5].map((n) => `D:/Media/E0${n}.mkv`))
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Browse…' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  const box = (n: number) => picker.getByRole('checkbox', { name: `Pick E0${n}.mkv` })
  const all = picker.getByRole('checkbox', { name: 'Pick all files' })

  await picker.getByText('E02.mkv').click() // the row ticks, not only the box
  await box(4).click({ modifiers: ['Shift'] })
  for (const n of [2, 3, 4]) await expect(box(n)).toBeChecked()
  for (const n of [1, 5]) await expect(box(n)).not.toBeChecked()
  await expect(all).toHaveAttribute('data-state', 'indeterminate')
  await expect(picker).toContainText('3 selected')

  await box(3).click({ modifiers: ['Shift'] }) // unticks 4 back to 3
  for (const n of [3, 4]) await expect(box(n)).not.toBeChecked()
  await expect(box(2)).toBeChecked()

  await box(1).press('ControlOrMeta+a')
  for (const n of [1, 2, 3, 4, 5]) await expect(box(n)).toBeChecked()
  await expect(picker.getByRole('checkbox', { name: 'Pick Old' })).not.toBeChecked() // files only
  await all.click()
  await expect(picker).not.toContainText('selected')

  await all.click()
  await picker.getByRole('button', { name: 'Add' }).click()
  await expect(page.getByRole('list', { name: 'Sources' }).getByRole('listitem')).toHaveCount(5)
  expect(errors).toEqual([])
})

test('the file picker ticks the rows a mouse press drags over, and unticks them from a ticked row', async ({
  page,
}) => {
  const { errors, files } = await fixture(page, [])
  files.push(...[1, 2, 3, 4, 5].map((n) => `D:/Media/E0${n}.mkv`))
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Browse…' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  const box = (n: number) => picker.getByRole('checkbox', { name: `Pick E0${n}.mkv` })
  async function drag(from: number, ...through: number[]) {
    await box(from).hover()
    await page.mouse.down()
    for (const n of through) await picker.getByText(`E0${n}.mkv`).hover()
    await page.mouse.up()
  }

  await drag(1, 3, 4, 2) // down to 4, then back up to 2
  for (const n of [1, 2]) await expect(box(n)).toBeChecked()
  for (const n of [3, 4, 5]) await expect(box(n)).not.toBeChecked()

  await drag(5, 4, 3)
  await expect(picker).toContainText('5 selected')
  await drag(2, 3) // starts on a ticked row, so it unticks
  for (const n of [1, 4, 5]) await expect(box(n)).toBeChecked()
  for (const n of [2, 3]) await expect(box(n)).not.toBeChecked()

  await box(2).click() // a plain click after a drag still ticks one
  await expect(box(2)).toBeChecked()
  await expect(picker).toContainText('4 selected')
  expect(errors).toEqual([])
})

test('the file picker filters the folder, ticks only what it shows, and keeps the filter on Refresh', async ({
  page,
}) => {
  const { errors, files } = await fixture(page, [])
  files.push('D:/Media/Show.S01E01.mkv', 'D:/Media/Show.S01E02.mkv', 'D:/Media/Show.S02E01.mkv')
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Browse…' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  const filter = picker.getByRole('searchbox', { name: 'Filter this folder' })
  const box = (name: string) => picker.getByRole('checkbox', { name: `Pick ${name}` })

  await filter.fill('s01 MKV')
  await expect(box('Show.S01E01.mkv')).toBeVisible()
  await expect(box('Show.S02E01.mkv')).toHaveCount(0)
  await expect(box('Old')).toHaveCount(0)
  await box('Show.S01E01.mkv').press('ControlOrMeta+a')
  await expect(picker).toContainText('2 selected') // only the two it shows

  files.push('D:/Media/Show.S01E03.mkv')
  await picker.getByRole('button', { name: 'Refresh' }).click()
  await expect(filter).toHaveValue('s01 MKV')
  await expect(box('Show.S01E03.mkv')).toBeVisible()

  await filter.fill('nope')
  await expect(picker).toContainText('Nothing here matches “nope”')
  await filter.press('Escape') // clears the filter; the picker stays open
  await expect(filter).toHaveValue('')
  await expect(box('Show.S02E01.mkv')).toBeVisible()
  await expect(picker).toContainText('2 selected') // ticks it hid are kept
  expect(errors).toEqual([])
})

test('the file picker sorts by name, size or date, keeps folders first, and remembers the sort', async ({ page }) => {
  const { errors, files } = await fixture(page, [])
  files.push('D:/Media/E10.mkv', 'D:/Media/E2.mkv', 'D:/Media/E1.mkv') // 3, 1 and 2 GB; E1 newest
  await page.goto('/#/new')
  const browse = page.getByRole('button', { name: 'Browse…' }).first()
  await browse.click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  const rows = () => picker.getByRole('checkbox', { name: /^Pick (?!all)/ })
  const shown = async () =>
    (await rows().evaluateAll((xs) => xs.map((x) => x.getAttribute('aria-label')))).map((x) => x!.slice(5))

  await expect.poll(shown).toEqual(['Old', 'E1.mkv', 'E2.mkv', 'E10.mkv']) // by name, numbers in order
  await picker.getByRole('button', { name: 'Sort by size' }).click()
  await expect.poll(shown).toEqual(['Old', 'E10.mkv', 'E1.mkv', 'E2.mkv']) // biggest first
  await picker.getByRole('button', { name: 'Sort by size' }).click()
  await expect.poll(shown).toEqual(['Old', 'E2.mkv', 'E1.mkv', 'E10.mkv'])
  await picker.getByRole('button', { name: 'Sort by modified' }).click()
  await expect.poll(shown).toEqual(['Old', 'E1.mkv', 'E2.mkv', 'E10.mkv']) // newest first
  await expect(picker.getByRole('button', { name: 'Sort by modified' })).toHaveAttribute('aria-pressed', 'true')

  await picker.getByRole('button', { name: 'Cancel' }).click()
  await browse.click()
  await expect(picker.getByRole('button', { name: 'Sort by modified' })).toHaveAttribute('aria-pressed', 'true')
  expect(errors).toEqual([])
})

test('the file picker moves, ticks, opens and adds from the keyboard', async ({ page }) => {
  const { errors, files } = await fixture(page, [])
  files.push(...[1, 2, 3, 4, 5].map((n) => `D:/Media/E0${n}.mkv`))
  const listed: string[] = []
  page.on('request', (r) => {
    const url = new URL(r.url())
    if (url.pathname === '/api/fs/list') listed.push(url.searchParams.get('path')!)
  })
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Browse…' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  const box = (name: string) => picker.getByRole('checkbox', { name: `Pick ${name}` })

  await picker.getByRole('searchbox', { name: 'Filter this folder' }).press('ArrowDown')
  await expect(box('Old')).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(box('E01.mkv')).toBeFocused()
  await page.keyboard.press('Shift+ArrowDown')
  await page.keyboard.press('Shift+ArrowDown')
  await expect(box('E03.mkv')).toBeFocused()
  for (const n of [1, 2, 3]) await expect(box(`E0${n}.mkv`)).toBeChecked()
  await page.keyboard.press('End')
  await expect(box('E05.mkv')).toBeFocused()
  await page.keyboard.press('Space')
  await expect(picker).toContainText('4 selected')
  await picker.getByRole('checkbox', { name: 'Pick all files' }).press('Space')
  await expect(picker).toContainText('5 selected')
  await picker.getByRole('checkbox', { name: 'Pick all files' }).press('Space')
  await expect(picker).not.toContainText('selected')
  await box('E01.mkv').press('Space')
  await box('E03.mkv').press('Shift+Space') // a range, like Shift+click
  await box('E05.mkv').press('Space')
  await expect(box('E02.mkv')).toBeChecked()
  await expect(box('E04.mkv')).not.toBeChecked()
  await expect(picker).toContainText('4 selected')

  await page.keyboard.press('Home')
  await expect(box('Old')).toBeFocused()
  await page.keyboard.press('Enter') // opens the folder, not ticks it
  await expect.poll(() => listed.at(-1)).toBe('D:/Media/Old')
  await expect(box('Old')).not.toBeChecked()
  await expect(box('Old')).toBeFocused() // the mock lists D:/Media again; the cursor is on the first row
  await page.keyboard.press('Backspace')
  await expect.poll(() => listed.at(-1)).toBe('D:/')

  await box('E02.mkv').focus()
  await page.keyboard.press('Enter') // adds what's ticked
  await expect(picker).toBeHidden()
  await expect(page.getByRole('list', { name: 'Sources' }).getByRole('listitem')).toHaveCount(4)
  expect(errors).toEqual([])
})

test('Enter on a file with nothing ticked adds that file', async ({ page }) => {
  const { errors, files } = await fixture(page, [])
  files.push('D:/Media/E01.mkv', 'D:/Media/E02.mkv')
  await page.goto('/#/new')
  await page.getByRole('button', { name: 'Browse…' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Sources' })
  await picker.getByRole('checkbox', { name: 'Pick E02.mkv' }).press('Enter')
  await expect(picker).toBeHidden()
  await expect(page.getByRole('list', { name: 'Sources' }).getByRole('listitem')).toHaveText(['E02.mkv'])
  expect(errors).toEqual([])
})

test('each slot counts its paths, scrolls a long list in its box, and clears on its own', async ({ page }) => {
  const { errors } = await fixture(page, [])
  const many = Array.from({ length: 30 }, (_, i) => `"D:/Media/Show.S01E${String(i + 1).padStart(2, '0')}.mkv"`)
  await paste(page, many.join(String.fromCharCode(13, 10)))
  const list = page.getByRole('list', { name: 'Sources' })
  await expect(list.getByRole('listitem')).toHaveCount(30)
  await expect(page.getByText('Sources · 30')).toBeVisible()
  const box = await list.evaluate((el) => ({ height: el.clientHeight, scroll: el.scrollHeight }))
  expect(box.height).toBeLessThanOrEqual(96) // three rows or so, then it scrolls
  expect(box.scroll).toBeGreaterThan(box.height)

  await expect(page.getByRole('button', { name: 'Clear all encodes' })).toHaveCount(0) // only when it has paths
  await page.getByRole('button', { name: 'Clear all sources' }).click()
  await expect(page.getByRole('group', { name: 'Sources' })).toContainText('MKV, MP4 or M2TS')
  await expect(page.getByRole('button', { name: 'Clear all sources' })).toHaveCount(0)
  await expect(page.locator('footer[aria-label="Add to queue"]')).toContainText('Paste file paths on any page')
  expect(errors).toEqual([])
})

test('the grip under Matched files drags it taller past the page, without jumping the page, and is remembered', async ({
  page,
}) => {
  const { errors } = await fixture(page, [])
  await page.setViewportSize({ width: 1280, height: 900 })
  const many = Array.from({ length: 30 }, (_, i) => `"D:/Media/Show.S01E${String(i + 1).padStart(2, '0')}.mkv"`)
  await paste(page, many.join(String.fromCharCode(13, 10)))
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  await expect(card).toContainText('30 job(s)')
  const grip = page.getByRole('separator', { name: 'Resize Matched files' })
  const scrollTop = () => card.evaluate((el) => el.parentElement!.scrollTop)
  const before = (await card.boundingBox())!.height

  const at = (await grip.boundingBox())!
  const x = at.x + at.width / 2
  await page.mouse.move(x, at.y + 6)
  await page.mouse.down()
  await page.mouse.move(x, 880, { steps: 3 }) // below the page, over the bottom bar: the page scrolls
  await page.waitForTimeout(500)
  await page.mouse.up()
  const tall = (await card.boundingBox())!.height
  expect(tall).toBeGreaterThan(before + 100)
  expect(await scrollTop()).toBeGreaterThan(0)

  const top = await scrollTop()
  const now = (await grip.boundingBox())!
  await page.mouse.move(x, now.y + 6)
  await page.mouse.down() // a grab alone moves nothing
  await page.mouse.move(x, now.y + 7)
  await page.mouse.up()
  expect(await scrollTop()).toBe(top)

  await page.reload()
  await expect(card).toContainText('30 job(s)')
  expect(Math.abs((await card.boundingBox())!.height - tall)).toBeLessThan(4) // remembered
  await grip.focus()
  await page.keyboard.press('ArrowDown')
  expect((await card.boundingBox())!.height).toBeGreaterThan(tall + 40)
  await grip.dblclick()
  await expect(grip).toHaveAttribute('aria-valuetext', 'Fills the page')
  expect(errors).toEqual([])
})
