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
    subtitle_info: [],
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
      '/api/match/patterns': [],
      '/api/match/timing': {},
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

test("each Browse on New jobs opens at its own last folder, not at another Browse's", async ({ page }) => {
  const { errors } = await fixture(page, [])
  // Sources were last browsed in D:/Media; the output folder was browsed since (the shared last_dir).
  const settings = {
    output_dir: 'D:/Output',
    last_dir: 'D:/Output',
    last_dirs: { sources: 'D:/Media' },
    output_folders: [],
    output_default: '',
  }
  const saved: Record<string, unknown>[] = []
  await page.route('**/api/settings', (route) => {
    if (route.request().method() === 'PUT') saved.push(route.request().postDataJSON())
    return route.fulfill({ json: settings })
  })
  const opened: string[] = []
  await page.route(/\/api\/fs\/list\?/, (route) => {
    const path = new URL(route.request().url()).searchParams.get('path')!
    opened.push(path)
    return route.fulfill({ json: { path, parent: 'D:/', dirs: [], files: [] } })
  })
  await page.goto('/#/new')
  const main = page.locator('main')
  const browse = main.getByRole('button', { name: 'Browse…', exact: true })

  await browse.first().click() // Sources
  await expect.poll(() => opened).toEqual(['D:/Media'])
  await expect.poll(() => saved).toEqual([{ last_dir: 'D:/Media', last_dirs: { sources: 'D:/Media' } }])
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()

  await browse.nth(1).click() // Output folder: no folder of its own yet, so the shared one
  await expect.poll(() => opened.at(-1)).toBe('D:/Output')
  await expect.poll(() => saved.at(-1)).toEqual({ last_dir: 'D:/Output', last_dirs: { output: 'D:/Output' } })
  expect(errors).toEqual([])
})

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

test('an Add that adds nothing says so, with no next step', async ({ page }) => {
  const { errors, sources } = await fixture(page, [])
  await page.route('**/api/jobs', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ json: { added: [], skipped: ['Show.S01E01.mkv'], unmatched: [], kept: [] } })
      : route.fallback(),
  )
  await paste(page, `"${sources[0]}"`)
  const bar = page.locator('footer[aria-label="Add to queue"]')
  await bar.getByRole('button', { name: /Add 1 job/ }).click()
  await expect(bar.getByRole('status')).toHaveText('Nothing added · 1 already in the queue, kept')
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
  // Two or more go in a queue group, named after the season; the name can be typed, and the box unticked.
  await expect(bar).toContainText('2 jobs in group Show S01 · Sized · will index and auto-crop · saved to D:/Output')
  const groupName = page.getByRole('textbox', { name: 'Group name' })
  await groupName.fill('My show')
  await expect(bar).toContainText('2 jobs in group My show · Sized')
  await page.getByRole('checkbox', { name: 'Group them' }).click()
  await expect(bar).toContainText('2 jobs · Sized')
  await expect(groupName).toBeDisabled()
  await page.getByRole('checkbox', { name: 'Group them' }).click()

  await page.getByRole('checkbox', { name: 'Auto-crop' }).click()
  await expect(bar).toContainText('will index ·')
  await expect(page.getByRole('checkbox', { name: 'Index', exact: true })).toHaveAccessibleDescription(
    '(indexes each job in the background for its preview)',
  )
  await page.getByRole('checkbox', { name: 'Index', exact: true }).click()
  await expect(bar).toContainText('will neither index nor crop')
  await bar.getByRole('button', { name: /Add 2 jobs/ }).click()

  // What comes next, after what was added
  await expect(bar.getByRole('status')).toHaveText(
    'Added 2 jobs · Next: check each job in the Queue, then tick its box to queue it.',
  )
  await expect(bar.getByRole('status').locator('[title]')).toHaveAttribute(
    'title',
    'Added 2 jobs · Next: check each job in the Queue, then tick its box to queue it.',
  )
  await expect(bar.getByRole('button', { name: 'Open queue' })).toBeVisible()
  expect(posted).toHaveLength(1)
  expect(posted[0]).toMatchObject({
    auto_index: false,
    auto_crop: false,
    output_dir: 'D:/Output',
    rule_set: 'manual',
    group_name: 'My show',
  })
  expect(posted[0].sources).toEqual(sources)

  await bar.getByRole('button', { name: 'Add more' }).click() // a clean form for the next batch
  await expect(bar).toContainText('Paste file paths on any page, or Browse')
  await expect(page.getByText('Show.S01E02.mkv')).toHaveCount(0)

  await paste(page, sources[0])
  await expect(page.getByRole('checkbox', { name: 'Group them' })).toHaveCount(0) // one job: no group
  await bar.getByRole('button', { name: /Add 1 job to queue/ }).click()
  await expect.poll(() => posted.length).toBe(2)
  expect(posted[1].group_name).toBeUndefined()
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
  const scrollTop = () => card.evaluate((el) => el.closest('.overflow-auto')!.scrollTop)
  // With "Group them" shown and Linux's wider fonts, the grip starts under the bottom bar, where a grab hits the bar
  await grip.evaluate((el) => el.scrollIntoView({ block: 'nearest', behavior: 'instant' }))
  const start = await scrollTop()
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
  expect(await scrollTop()).toBeGreaterThan(start)

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

test('Matched files tags each subtitle, flags odd rows, lists unmatched files first, and drops unticked subtitles', async ({
  page,
}) => {
  const posted: Record<string, unknown>[] = []
  const { errors } = await fixture(page, posted)
  const label = (path: string, tags: string[], track: number | null, match: string) => ({
    path,
    language: 'en',
    language_name: 'English',
    format: path.slice(-3),
    tags,
    track,
    match,
  })
  const synced = (n: number) => `D:/Media/subs/Show.S01E0${n}.en.synced.srt`
  const extracted = 'D:/Media/Show.S01E01_track7_[eng].ass'
  await page.route('**/api/match', (route) => {
    const sources = route.request().postDataJSON().sources as string[]
    const subs: Record<string, string[]> = {
      'D:/Media/Show.S01E01.mkv': [extracted, synced(1)],
      'D:/Media/Show.S01E02.mkv': [synced(2)],
      'D:/Media/Show.S01E03.mkv': [synced(3)],
      'D:/Media/Show.S01E10.mkv': [],
    }
    return route.fulfill({
      json: {
        jobs: [...sources].sort().map((source) => ({
          source,
          encode: null,
          encode_state: null,
          subtitles: subs[source],
          subtitle_info: subs[source].map((p) =>
            label(
              p,
              p.includes('synced') ? ['synced'] : [],
              p === extracted ? 7 : null,
              p === extracted ? 'other_episode' : 'name', // as if its name said another episode
            ),
          ),
          chapters: null,
          existing_id: null,
          existing_status: null,
        })),
        unmatched: ['D:/Media/Stray.srt'],
      },
    })
  })
  await paste(
    page,
    ['S01E10', 'S01E02', 'S01E03', 'S01E01'].map((e) => `"D:/Media/Show.${e}.mkv"`).join(String.fromCharCode(13, 10)),
  )

  const chips = page.getByRole('list', { name: 'Sources' }).getByRole('listitem')
  await expect(chips).toHaveText(['Show.S01E01.mkv', 'Show.S01E02.mkv', 'Show.S01E03.mkv', 'Show.S01E10.mkv']) // reading order
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  const rows = card.locator('tbody tr')
  await expect(rows.first()).toContainText('Not matched to any source: Stray.srt')
  await expect(card).toContainText('1 without subtitles · 1 with a different number of subtitles')
  await expect(rows.nth(1)).toContainText('2 subtitles; most have 1')
  await expect(rows.nth(4)).toContainText('No subtitles; most have 1')

  const ass = card.getByRole('button', { name: 'en · ass · track 7: Show.S01E01_track7_[eng].ass' })
  await expect(card.getByRole('button', { name: /^en · srt · synced: Show\.S01E0\d\.en\.synced\.srt$/ })).toHaveCount(3)
  await expect(card.getByRole('button', { name: /^Starts with the source’s name\./ })).toHaveCount(3)
  await expect(rows.nth(1).getByRole('button', { name: /name is for another episode/ })).toBeVisible()
  await expect(card).toContainText('1 subtitle named for another episode')
  await ass.click()
  await expect(ass).toHaveAttribute('aria-pressed', 'false')
  await expect(rows.nth(1)).not.toContainText('most have') // E01 is back to one subtitle
  await expect(card).toContainText('1 without subtitles')
  await expect(card).not.toContainText('different number')
  await expect(card).not.toContainText('named for another episode') // unticked, so no longer counted

  await page
    .locator('footer[aria-label="Add to queue"]')
    .getByRole('button', { name: /Add 4 jobs/ })
    .click()
  await expect.poll(() => posted.length).toBe(1)
  expect(posted[0].exclude_subtitles).toEqual([extracted])
  expect(errors).toEqual([])
})

test('files are matched by hand in Matched files and in Review matches, sent with Add, and can be undone', async ({
  page,
}) => {
  const posted: Record<string, unknown>[] = []
  const { errors } = await fixture(page, posted)
  const [e1, e2, e3] = ['D:/Media/Show.S01E01.mkv', 'D:/Media/Show.S01E02.mkv', 'D:/Media/Show.S01E03.mkv']
  const named = 'D:/Media/Show.S01E01.en.srt' // matched by its name
  const stray = 'D:/Media/Show - 02.srt' // unmatched, the closest name suggested
  const [setA, setB] = ['D:/Media/t1_c1.srt', 'D:/Media/t2_c2.srt'] // a numbered set nothing ties to an episode
  const asked: Record<string, string | null>[] = []
  // A stand-in for the server: the user's matches win, the rest go by name or stay unmatched; matching setA by
  // hand offers setB the same way.
  await page.route('**/api/match', (route) => {
    const assign = (route.request().postDataJSON().assign ?? {}) as Record<string, string | null>
    asked.push(assign)
    const files = [named, stray, setA, setB]
    const auto: Record<string, string> = { [named]: e1 }
    const placed = (f: string) => (f in assign ? assign[f] : (auto[f] ?? null))
    const job = (source: string) => {
      const mine = files.filter((f) => placed(f) === source)
      const how = (f: string) => (f in assign ? 'manual' : 'name')
      return {
        source,
        encode: null,
        encode_state: null,
        subtitles: mine,
        subtitle_info: mine.map((path) => ({
          path,
          language: path === setA || path === setB ? 'ja' : 'en', // the set isn't alike the others
          language_name: 'English',
          format: 'srt',
          tags: [],
          track: null,
          match: how(path),
        })),
        chapters: null,
        existing_id: null,
        existing_status: null,
        matches: Object.fromEntries(mine.map((f) => [f, how(f)])),
      }
    }
    const left = files.filter((f) => placed(f) === null)
    const offer = (f: string) =>
      f === stray
        ? [{ source: e2, why: 'similar' }]
        : f === setB && assign[setA] === e1
          ? [{ source: e2, why: 'pattern' }]
          : []
    return route.fulfill({
      json: {
        jobs: [e1, e2, e3].map(job),
        unmatched: left,
        held: left.filter((f) => f in assign),
        suggestions: Object.fromEntries(left.map((f) => [f, offer(f)])),
      },
    })
  })
  await paste(page, [e1, e2, e3].map((p) => `"${p}"`).join(String.fromCharCode(13, 10)))

  // In the table: the suggested source in one click, and undone.
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  await expect(card).toContainText('Not matched to any source: Show - 02.srt')
  const pick = card.getByRole('combobox', { name: 'Match Show - 02.srt to a source' })
  await expect(pick.locator('optgroup[label="Suggested"] option')).toHaveText(['Show.S01E02.mkv'])
  await card.getByRole('button', { name: 'Use Show.S01E02.mkv' }).click()
  await expect.poll(() => asked.at(-1)).toEqual({ [stray]: e2 })
  await expect(card.getByRole('button', { name: /^You matched it to this source\. Change the match/ })).toBeVisible()
  await card.getByRole('button', { name: 'Undo match: Show - 02.srt' }).click()
  await expect.poll(() => asked.at(-1)).toEqual({})

  // Review matches: what needs a look, a filter, a match by hand and the rest of its set the same way.
  await card.getByRole('button', { name: 'Review matches · 3 to check' }).click()
  const dialog = page.getByRole('dialog', { name: 'Review matches' })
  const files = dialog.getByRole('list', { name: 'Files' }).getByRole('listitem')
  await expect(files).toHaveCount(3)
  await dialog.getByRole('textbox', { name: 'Filter by name' }).fill('t1 srt')
  await expect(files).toHaveCount(1)
  await dialog.getByRole('textbox', { name: 'Filter by name' }).fill('')
  await dialog.getByRole('combobox', { name: 'Source for t1_c1.srt' }).selectOption(e1)
  await expect.poll(() => asked.at(-1)).toEqual({ [setA]: e1 })
  await expect(dialog).toContainText('1 more file named like the one you matched.')
  await expect(
    dialog.getByRole('combobox', { name: 'Source for t2_c2.srt' }).locator('option', { hasText: '(like your match)' }),
  ).toHaveCount(1)
  await dialog.getByRole('button', { name: 'Match them the same way' }).click()
  await expect.poll(() => asked.at(-1)).toEqual({ [setA]: e1, [setB]: e2 })
  await expect(files).toHaveCount(3) // changed here, so still listed
  await expect(dialog.getByRole('combobox', { name: 'Source for t2_c2.srt' })).toHaveValue(e2)

  // Any file can move, or go to no source.
  await dialog.getByRole('radio', { name: /All files/ }).click()
  await dialog.getByRole('combobox', { name: 'Source for Show.S01E01.en.srt' }).selectOption(e3)
  await expect.poll(() => asked.at(-1)?.[named]).toBe(e3)
  await dialog.getByRole('button', { name: 'Undo match: Show.S01E01.en.srt' }).click()
  await expect.poll(() => named in (asked.at(-1) ?? {})).toBe(false)
  await dialog.getByRole('combobox', { name: 'Source for Show - 02.srt' }).selectOption('-')
  await expect.poll(() => asked.at(-1)?.[stray]).toBe(null)
  await dialog.getByRole('button', { name: 'Done' }).click()
  await expect(dialog).toBeHidden()
  await expect(card).toContainText('Set to no source by you: Show - 02.srt')

  // A file's match icon opens Review matches on that file.
  await card.getByRole('button', { name: /Change the match of Show\.S01E01\.en\.srt$/ }).click()
  await expect(dialog.getByRole('combobox', { name: 'Source for Show.S01E01.en.srt' })).toBeFocused()
  await page.keyboard.press('Escape')

  await page
    .locator('footer[aria-label="Add to queue"]')
    .getByRole('button', { name: /Add 3 jobs/ })
    .click()
  await expect.poll(() => posted.length).toBe(1)
  expect(posted[0].assign).toEqual({ [setA]: e1, [setB]: e2, [stray]: null })
  expect(errors).toEqual([])
})

test('Matched files and Review matches show left-over files, subtitles alike, a subtitle too long for its source, what a guess went on, and forget a remembered pattern', async ({
  page,
}) => {
  const posted: Record<string, unknown>[] = []
  const { errors } = await fixture(page, posted)
  const [e1, e2] = ['D:/Media/Show.S01E01.mkv', 'D:/Media/Show.S01E02.mkv']
  const chapters = 'D:/Media/Show.S01E01.chapters.txt'
  const spare = 'D:/Media/chapters_E01.xml'
  const [plain, synced] = ['D:/Media/Show.S01E01.en.srt', 'D:/Media/Show.S01E01.en.synced.srt']
  const taught = 'D:/Media/t2_c2.srt'
  const shape = 't#_c#'
  let remembered = 1
  let matches = 0
  const forgotten: unknown[] = []
  await page.route('**/api/match/patterns', (route) =>
    route.fulfill({ json: remembered ? [{ shape, position: 1, example: 't1_c1.srt' }] : [] }),
  )
  await page.route('**/api/match/patterns/forget', (route) => {
    forgotten.push(route.request().postDataJSON())
    remembered = 0
    return route.fulfill({ json: { forgotten: 1 } })
  })
  const timed: Record<string, string>[] = []
  await page.route('**/api/match/timing', (route) => {
    timed.push(route.request().postDataJSON().pairs)
    return route.fulfill({ json: { [plain]: { verdict: 'late', last_ms: 2_640_000, source_ms: 1_440_000 } } })
  })
  await page.route('**/api/match', (route) => {
    matches++
    const sub = (path: string, tags: string[], match: string) => ({
      path,
      language: 'en',
      language_name: 'English',
      format: 'srt',
      tags,
      track: null,
      match,
    })
    const learned = remembered > 0
    return route.fulfill({
      json: {
        jobs: [
          {
            source: e1,
            encode: null,
            encode_state: null,
            subtitles: [plain, synced],
            subtitle_info: [sub(plain, [], 'name'), sub(synced, ['synced'], 'name')],
            chapters,
            existing_id: null,
            existing_status: null,
            matches: { [chapters]: 'name', [plain]: 'name', [synced]: 'name' },
          },
          {
            source: e2,
            encode: null,
            encode_state: null,
            subtitles: learned ? [taught] : [],
            subtitle_info: learned ? [{ ...sub(taught, [], 'learned'), language: 'und' }] : [],
            chapters: null,
            existing_id: null,
            existing_status: null,
            matches: learned ? { [taught]: 'learned' } : {},
            details: learned ? { [taught]: 'Named like t1_c1.srt, which you matched before' } : {},
            patterns: learned ? { [taught]: shape } : {},
          },
        ],
        unmatched: learned ? [spare] : [spare, taught],
        held: [],
        spare: { [spare]: e1 },
        suggestions: {},
      },
    })
  })
  await paste(page, [e1, e2].map((p) => `"${p}"`).join(String.fromCharCode(13, 10)))

  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  await expect(card).toContainText(
    'Left over: Show.S01E01.mkv already has chapters, so chapters_E01.xml isn’t used'.replace('’', "'"),
  )
  await expect(card).toContainText('2 alike (same language and type): Show.S01E01.en.srt, Show.S01E01.en.synced.srt')
  await expect(
    card.getByRole('button', { name: /^Named like a set you matched before\. Change the match of t2_c2\.srt$/ }),
  ).toBeVisible()

  await card.getByRole('button', { name: /^Review matches/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Review matches' })
  await expect(dialog).toContainText('Left over: Show.S01E01.mkv already has chapters, Show.S01E01.chapters.txt')
  await expect(dialog).toContainText('Same language and type as Show.S01E01.en.synced.srt')
  await expect(dialog).toContainText(
    'Its last line is at 44:00, 20:00 after the source ends (24:00): another episode or cut?',
  )
  expect(timed[0]).toEqual({ [plain]: e1, [taught]: e2 }) // not the synced one
  await dialog.getByRole('radio', { name: /All files/ }).click()
  await expect(dialog).toContainText('Named like t1_c1.srt, which you matched before')
  await expect(dialog).toContainText('Sets you matched by hand are remembered for later batches · 1')
  const before = matches
  await dialog.getByRole('button', { name: 'Forget this pattern' }).click()
  await expect.poll(() => forgotten).toEqual([{ shape }])
  await expect.poll(() => matches).toBeGreaterThan(before) // matched again without it
  await expect(dialog).not.toContainText('remembered for later batches')
  await expect(dialog.getByRole('combobox', { name: 'Source for t2_c2.srt' })).toHaveValue('')
  expect(errors).toEqual([])
})

test('subtitle timing is checked after matching, counted and shown in Matched files, and checked again when Review matches opens', async ({
  page,
}) => {
  const posted: Record<string, unknown>[] = []
  const { errors } = await fixture(page, posted)
  const source = 'D:/Media/Show.S01E01.mkv'
  const sub = 'D:/Media/Show.S01E01.en.srt'
  const asked: Record<string, string>[] = []
  let late = false // the file is swapped on disk between the two checks
  await page.route('**/api/match/timing', (route) => {
    asked.push(route.request().postDataJSON().pairs)
    const t = late
      ? { verdict: 'late', last_ms: 2_640_000, source_ms: 1_440_000 }
      : { verdict: null, last_ms: 1_400_000, source_ms: 1_440_000 }
    return route.fulfill({ json: { [sub]: t } })
  })
  await page.route('**/api/match', (route) =>
    route.fulfill({
      json: {
        jobs: [
          {
            source,
            encode: null,
            encode_state: null,
            subtitles: [sub],
            subtitle_info: [
              {
                path: sub,
                language: 'en',
                language_name: 'English',
                format: 'srt',
                tags: [],
                track: null,
                match: 'name',
              },
            ],
            chapters: null,
            existing_id: null,
            existing_status: null,
            matches: { [sub]: 'name' },
          },
        ],
        unmatched: [],
        held: [],
        suggestions: {},
      },
    }),
  )
  await paste(page, `"${source}"`)
  await expect.poll(() => asked).toEqual([{ [sub]: source }]) // in the background, before anyone looks
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  await expect(card.getByRole('button', { name: 'Review matches', exact: true })).toBeVisible()

  late = true
  await card.getByRole('button', { name: 'Review matches', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Review matches' })
  await expect.poll(() => asked.length).toBe(2) // asked again on opening
  // Opened on All files (nothing to check then), it moves to Needs a look once the flag turns up.
  await expect(dialog.getByRole('radio', { name: 'Needs a look · 1' })).toHaveAttribute('aria-checked', 'true')
  await expect(dialog).toContainText(
    'Its last line is at 44:00, 20:00 after the source ends (24:00): another episode or cut?',
  )
  await page.keyboard.press('Escape')
  await expect(card).toContainText(
    'Show.S01E01.en.srt ends 20:00 after its source (44:00 of 24:00): another episode or cut?',
  )
  await expect(card.getByRole('button', { name: 'Review matches · 1 to check' })).toBeVisible()
  expect(errors).toEqual([])
})

test('Review matches moves several selected files at once, a Shift+click range or every file shown', async ({
  page,
}) => {
  const posted: Record<string, unknown>[] = []
  const { errors } = await fixture(page, posted)
  const [e1, e2] = ['D:/Media/Show.S01E01.mkv', 'D:/Media/Show.S01E02.mkv']
  const files = ['a', 'b', 'c', 'd'].map((n) => `D:/Media/${n}.srt`)
  const asked: Record<string, string | null>[] = []
  await page.route('**/api/match', (route) => {
    const assign = (route.request().postDataJSON().assign ?? {}) as Record<string, string | null>
    asked.push(assign)
    const job = (source: string) => {
      const mine = files.filter((f) => assign[f] === source)
      return {
        source,
        encode: null,
        encode_state: null,
        subtitles: mine,
        subtitle_info: mine.map((path, i) => ({
          path,
          language: ['en', 'de', 'fr', 'es'][i],
          language_name: '',
          format: 'srt',
          tags: [],
          track: null,
          match: 'manual',
        })),
        chapters: null,
        existing_id: null,
        existing_status: null,
        matches: Object.fromEntries(mine.map((f) => [f, 'manual'])),
      }
    }
    const left = files.filter((f) => !assign[f])
    return route.fulfill({
      json: {
        jobs: [job(e1), job(e2)],
        unmatched: left,
        held: left.filter((f) => f in assign),
        suggestions: Object.fromEntries(left.map((f) => [f, []])),
      },
    })
  })
  await paste(page, [e1, e2].map((p) => `"${p}"`).join(String.fromCharCode(13, 10)))
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  await card.getByRole('button', { name: /^Review matches/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Review matches' })

  await dialog.getByRole('checkbox', { name: 'Select a.srt' }).click()
  await dialog.getByRole('checkbox', { name: 'Select c.srt' }).click({ modifiers: ['Shift'] })
  await expect(dialog).toContainText('3 selected')
  await dialog.getByRole('combobox', { name: 'Move the selected files to' }).selectOption(e2)
  await expect.poll(() => asked.at(-1)).toEqual({ [files[0]]: e2, [files[1]]: e2, [files[2]]: e2 })
  await expect(dialog.getByRole('combobox', { name: 'Source for b.srt' })).toHaveValue(e2)

  await dialog.getByRole('checkbox', { name: 'Select every file shown' }).click()
  await expect(dialog).toContainText('4 selected')
  await dialog.getByRole('combobox', { name: 'Move the selected files to' }).selectOption('-')
  await expect
    .poll(() => asked.at(-1))
    .toEqual({ [files[0]]: null, [files[1]]: null, [files[2]]: null, [files[3]]: null })
  await dialog.getByRole('button', { name: 'Undo their changes' }).click()
  await expect.poll(() => asked.at(-1)).toEqual({})
  await dialog.getByRole('button', { name: 'Clear selection' }).click()
  await expect(dialog).toContainText('Select files to move several at once')
  expect(errors).toEqual([])
})

test('while Add runs the bar says so with a spinner, the inputs are locked, and a paste waits', async ({ page }) => {
  const posted: Record<string, unknown>[] = []
  const { errors, sources } = await fixture(page, posted)
  let release!: () => void
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/jobs', async (route) =>
    route.request().method() === 'POST' ? (await held, await route.fallback()) : route.fallback(),
  )
  await paste(page, sources.map((p) => `"${p}"`).join(String.fromCharCode(13, 10)))
  const bar = page.locator('footer[aria-label="Add to queue"]')
  await bar.getByRole('button', { name: /Add 2 jobs/ }).click()

  await expect(bar.getByRole('status')).toHaveText('Adding 2 jobs to the queue…')
  await expect(bar.getByRole('button', { name: 'Adding…' })).toBeDisabled()
  await expect(bar.getByRole('button', { name: 'Clear all' })).toBeDisabled()
  await expect(
    page.getByRole('list', { name: 'Sources' }).getByRole('button', { name: 'Remove' }).first(),
  ).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Clear all sources' })).toBeDisabled()
  await paste(page, '"D:/Media/Show.S01E03.mkv"') // held until Add is done
  await expect(page.getByRole('list', { name: 'Sources' }).getByRole('listitem')).toHaveCount(2)

  release()
  await expect(bar.getByRole('status')).toContainText('Added 2 jobs')
  await expect(page.getByRole('list', { name: 'Sources' }).getByRole('listitem')).toHaveText(['Show.S01E03.mkv'])
  expect(posted).toHaveLength(1)
  expect(errors).toEqual([])
})
