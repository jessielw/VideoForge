import { test, expect, type Locator, type Page } from '@playwright/test'
import type { ConfigState, NamePolicy, RuleSet, Template } from '../../src/lib/types.ts'

/** others: rule sets installed beside Manual (a plugin's), each like Manual but for its id and name. */
async function layoutFixture(page: Page, naming?: NamePolicy, others: Pick<RuleSet, 'id' | 'name'>[] = []) {
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
    encoder: {
      encoder: 'x264',
      rate_control: '2pass',
      crf: 18,
      bitrate_kbps: 8000,
      target_mb: null,
      preset: 'veryslow',
      tune: '',
      depth: 8,
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
    containers: [
      { id: 'mkv', label: 'MKV (mkvmerge)', extension: '.mkv', tool: 'mkvmerge' },
      { id: 'mp4', label: 'MP4 (MP4Box)', extension: '.mp4', tool: 'MP4Box' },
    ],
    external_subtitles: true,
    track_editor: true,
    track_properties: [],
    defaults: { video: template.video, encoder: template.encoder, template },
    naming,
  }
  const more = others.map((r) => ({ ...ruleSet, ...r, default: false }))
  const config: ConfigState = {
    tools: [
      {
        name: 'ffmpeg',
        label: 'ffmpeg',
        purpose: 'Audio and video',
        folder: false,
        path: 'ffmpeg',
        default: 'ffmpeg',
        custom: null,
      },
    ],
    roots: ['D:\\Media'],
    roots_custom: false,
    default_roots: ['D:\\Media'],
    rule_set: 'manual',
    rule_set_default: 'manual',
    rule_sets: [ruleSet, ...more],
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
    records_dir: 'D:\\VideoForge\\records',
    data_dir: 'D:/VideoForge',
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [
      { id: 'move', label: 'Move output' },
      { id: 'copy', label: 'Copy output' },
      { id: 'command', label: 'Run command' },
      { id: 'webhook', label: 'Webhook' },
    ],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  await page.addInitScript(() => localStorage.setItem('videoforge.mode', 'dark'))
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, unknown> = {
      '/api/preset-packs/managed': { presets: [], problems: [] },
      '/api/jobs': [],
      '/api/rule-sets': [ruleSet, ...more],
      '/api/health': { ok: true, version: 'test' },
      '/api/profiles': { profiles: [{ id: 'default', name: 'Default' }], active: 'default' },
      '/api/presets': {
        video: [],
        encoder: [],
        audio: [],
        template: [{ name: 'Film 1080p CEL', data: template }],
        template_defaults: { manual: 'Film 1080p CEL' },
        encoder_starters: [],
      },
      '/api/filter-presets': [],
      '/api/name-tokens': {
        default_template: '{title} {release_year} {resolution}',
        tokens: [
          { name: 'title', description: 'Title' },
          { name: 'video_codec', description: "The encode's codec" },
        ],
        filters: ['upper', 'lower', 'dots'],
      },
      '/api/config/encoders': [],
      '/api/config/video-options/x264': { dashes: '--', options: [] },
      '/api/settings': { output_dir: 'D:\\Output', last_dir: '' },
      '/api/config': config,
      '/api/config/tools': [],
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected layout fixture request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  return errors
}

test('Templates saves optional PGS compression and only shows it for MKV', async ({ page }) => {
  const errors = await layoutFixture(page)
  let saved: Template | null = null
  await page.route('**/api/presets/template/*', async (route) => {
    saved = route.request().postDataJSON() as Template
    await route.fulfill({
      json: {
        video: [],
        encoder: [],
        audio: [],
        template: [{ name: 'Film 1080p CEL', data: saved }],
        template_defaults: {},
        encoder_starters: [],
      },
    })
  })
  await page.goto('/#/templates')
  const compression = page.getByRole('checkbox', { name: 'Compress PGS subtitles with zlib' })
  await expect(compression).not.toBeChecked()
  await compression.check()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect.poll(() => saved?.mux.pgs_zlib).toBe(true)
  await page.getByRole('radio', { name: 'MP4 (MP4Box)', exact: true }).click()
  await expect(compression).toHaveCount(0)
  await page.getByRole('radio', { name: 'MKV (mkvmerge)', exact: true }).click()
  await expect(compression).toBeChecked()
  expect(errors).toEqual([])
})

test('Templates saves a name template, what it names, and a name suffix', async ({ page }) => {
  const errors = await layoutFixture(page)
  let saved: Template | null = null
  await page.route('**/api/presets/template/*', async (route) => {
    saved = route.request().postDataJSON() as Template
    await route.fulfill({
      json: {
        video: [],
        encoder: [],
        audio: [],
        template: [{ name: 'Film 1080p CEL', data: saved }],
        template_defaults: {},
        encoder_starters: [],
      },
    })
  })
  await page.goto('/#/templates')
  const field = page.getByRole('textbox', { name: 'Name template' })
  await expect(page.getByText('Not used until one of these is on.')).toBeVisible()
  await field.focus()
  await expect(field).toHaveAttribute('placeholder', '{title} {release_year} {resolution}')
  // a token goes on the end of the default template when the field is empty
  await page.getByRole('button', { name: 'Tokens' }).click()
  await page.getByRole('button', { name: /\{video_codec\}/ }).click()
  await expect(field).toHaveValue('{title} {release_year} {resolution} {video_codec}')
  // ... and at the cursor in a typed one, left selected so it shows where it went
  await field.fill('{title} {resolution}')
  await field.press('Home')
  for (let i = 0; i < '{title}'.length; i++) await field.press('ArrowRight')
  await page.getByRole('button', { name: 'Tokens' }).click()
  await page.getByRole('button', { name: /\{video_codec\}/ }).click()
  await expect(field).toHaveValue('{title} {video_codec} {resolution}')
  await expect(field).toBeFocused()
  expect(await field.evaluate((el: HTMLTextAreaElement) => el.value.slice(el.selectionStart, el.selectionEnd))).toBe(
    '{video_codec}',
  )
  await field.fill('{title} {release_year} {resolution} {video_codec}')
  await field.blur()
  await page.getByRole('checkbox', { name: 'Name the file with it' }).check()
  await page.getByRole('checkbox', { name: 'Set the MKV title with it' }).check()
  await page.getByRole('textbox', { name: 'Name suffix' }).fill('vf')
  await page.getByRole('textbox', { name: 'Name suffix' }).blur()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect
    .poll(() => saved?.mux)
    .toMatchObject({
      name_template: '{title} {release_year} {resolution} {video_codec}',
      template_file_name: true,
      template_title: true,
      name_suffix: 'vf',
    })
  // the title is MKV's alone
  await page.getByRole('radio', { name: 'MP4 (MP4Box)', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: 'Set the MKV title with it' })).toHaveCount(0)
  expect(errors).toEqual([])
})

test("Templates says when Settings decides a rule set's naming instead of the template", async ({ page }) => {
  const errors = await layoutFixture(page, { file_name: 'off', title: 'template' })
  await page.goto('/#/templates')
  const note = page.getByText(
    'Settings sets this for all Manual jobs, whatever this template says: the file is never named with it.',
  )
  await expect(note).toBeVisible()
  await expect(page.getByText('Not used until one of these is on.')).toBeVisible()
  await page.getByRole('checkbox', { name: 'Name the file with it' }).check() // the template keeps its own switch
  await expect(page.getByText('Not used until one of these is on.')).toBeVisible()
  expect(errors).toEqual([])
})

test('the name template links to the Settings that turns it on or off for every job', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.addInitScript(() => localStorage.setItem('videoforge.settingsTab', 'tools')) // last left elsewhere
  await page.goto('/#/templates')
  await expect(page.getByText('Settings can turn these on or off for all Manual jobs at once.')).toBeVisible()
  await page.getByRole('button', { name: 'Settings › Output names' }).click()
  await expect(page).toHaveURL(/#\/settings$/)
  const heading = page.getByRole('heading', { name: 'Output names', exact: true })
  await expect(heading).toBeFocused()
  await expect(heading).toBeInViewport()
  expect(errors).toEqual([])
})

test('templates uses the available editor width on large windows', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1920, height: 1000 })
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const content = page.locator('fieldset').first()
  await expect(content).toBeVisible()
  const bounds = await content.boundingBox()
  expect(bounds!.x + bounds!.width).toBeGreaterThan(1920 - 40)
  await expect(page.getByRole('button', { name: 'All templates' })).toHaveCount(0) // the list stays beside the editor
  await page.screenshot({ path: testInfo.outputPath('templates-wide.png') })
  expect(errors).toEqual([])
})

test('settings keeps one readable column on large windows', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1920, height: 1000 })
  const errors = await layoutFixture(page)
  await page.goto('/#/settings')
  for (const tab of ['Tools', 'Queue & indexing']) {
    await page.getByRole('button', { name: tab, exact: true }).click()
    const content = await page.getByRole('group', { name: tab, exact: true }).boundingBox()
    expect(content!.width, tab).toBeLessThanOrEqual(896) // 56rem
  }
  // groups go one under another, so a short one never sits beside a tall one
  const indexing = await page.getByRole('heading', { name: 'Batch indexing', exact: true }).boundingBox()
  const audio = await page.getByRole('heading', { name: 'Audio encodes', exact: true }).boundingBox()
  expect(audio!.y).toBeGreaterThan(indexing!.y)
  expect(Math.abs(audio!.x - indexing!.x)).toBeLessThan(2)
  await page.screenshot({ path: testInfo.outputPath('settings-wide.png') })
  expect(errors).toEqual([])
})

for (const width of [960, 800]) {
  test(`New jobs scrolls at ${width} CSS pixels without clipping its form`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 540 })
    const errors = await layoutFixture(page)
    await page.goto('/#/new')
    const output = page.getByRole('list', { name: 'Output folder', exact: true })
    await expect(output).toContainText('Output')
    const form = output.locator('xpath=../..')
    const formBounds = await form.boundingBox()
    const outputBounds = await output.boundingBox()
    expect(outputBounds!.y + outputBounds!.height).toBeLessThanOrEqual(formBounds!.y + formBounds!.height)
    await output.scrollIntoViewIfNeeded()
    await expect(output).toBeInViewport()
    const add = page.getByRole('button', { name: /Add.*to queue/ })
    await add.scrollIntoViewIfNeeded()
    await expect(add).toBeInViewport()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await page.screenshot({ path: testInfo.outputPath('new-jobs-short.png') })
    expect(errors).toEqual([])
  })
}

test('Templates stacks editor columns when zoom leaves insufficient panel width', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const columns = page.locator('fieldset').first()
  await expect(columns).toBeVisible()
  const children = columns.locator(':scope > *')
  const video = await children.nth(0).boundingBox()
  const output = await children.nth(1).boundingBox()
  expect(output!.y).toBeGreaterThanOrEqual(video!.y + video!.height)
  const extra = page.getByRole('textbox', { name: /^Extra arguments for \S+$/ })
  await extra.scrollIntoViewIfNeeded()
  await expect(extra).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('templates-narrow.png') })
  expect(errors).toEqual([])
})

test('Templates on a 320 px window shows the list or the editor, and All templates goes back', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const list = page.getByRole('list', { name: 'Templates' })
  const row = list.getByRole('button', { name: 'Film 1080p CEL', exact: true })
  const name = page.getByRole('textbox', { name: 'Template name' })
  const back = page.getByRole('button', { name: 'All templates' })
  await expect(list).toBeVisible()
  await expect(name).toBeHidden()

  await row.click()
  await expect(list).toBeHidden()
  await expect(name).toBeFocused()
  const editor = page.locator('[class*="@container/template-editor"]')
  expect(await editor.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0)
  await back.click()
  await expect(list).toBeVisible()
  await expect(name).toBeHidden()
  await expect(row).toBeFocused()

  // leaving an edited template this way asks first, like any other way out
  await row.click()
  await name.fill('Film 1080p CEL edited')
  await back.click()
  await expect(page.getByRole('dialog')).toContainText('Save changes to Film 1080p CEL edited?')
  await page.getByRole('button', { name: 'Stay', exact: true }).click()
  await expect(name).toBeVisible()
  await back.click()
  await page.getByRole('button', { name: 'Discard', exact: true }).click()
  await expect(list).toBeVisible()
  await expect(row).toBeFocused()

  // a built-in's name can't be edited, so focus goes to All templates
  await list.getByRole('button', { name: /^Manual defaults/ }).click()
  await expect(back).toBeFocused()
  expect(errors).toEqual([])
})

test('Templates on a 320 px window: Stay reaches an edit kept from before a reload', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const list = page.getByRole('list', { name: 'Templates' })
  const name = page.getByRole('textbox', { name: 'Template name' })
  await list.getByRole('button', { name: 'Film 1080p CEL', exact: true }).click()
  await name.fill('Film 1080p CEL edited')
  await page.reload() // the draft survives it, but the window opens on the list
  await expect(list).toBeVisible()
  await list.getByRole('button', { name: 'Film 1080p CEL', exact: true }).click()
  await page.getByRole('button', { name: 'Stay', exact: true }).click()
  await expect(name).toBeFocused()
  await expect(name).toHaveValue('Film 1080p CEL edited')
  expect(errors).toEqual([])
})

test('Templates on a 320 px window: after Delete, focus is in the list', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const errors = await layoutFixture(page)
  await page.route('**/api/presets/template/*', (route) =>
    route.fulfill({
      json: { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] },
    }),
  )
  await page.goto('/#/templates')
  const list = page.getByRole('list', { name: 'Templates' })
  await list.getByRole('button', { name: 'Film 1080p CEL', exact: true }).click()
  const remove = page.getByRole('button', { name: 'Delete', exact: true })
  await remove.click()
  await page.getByRole('button', { name: 'Confirm?', exact: true }).click()
  await expect(list).toBeVisible()
  await expect(list.getByRole('button', { name: 'Film 1080p CEL', exact: true })).toHaveCount(0)
  // on the open template's name, not on a row's star, where Enter would change the default
  await expect(list.locator(':focus')).toHaveAttribute('aria-current', 'true')
  expect(errors).toEqual([])
})

test('the sidebar keeps one left edge: logo, icons and status', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/new')
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  const logo = await nav.locator('img').boundingBox()
  const icon = await nav.getByRole('button', { name: 'New jobs' }).locator('svg').boundingBox()
  const status = await nav.getByText('Idle', { exact: true }).boundingBox()
  expect(Math.abs(logo!.x - icon!.x)).toBeLessThanOrEqual(1)
  expect(Math.abs(status!.x - icon!.x)).toBeLessThanOrEqual(1)
  expect(errors).toEqual([])
})

test('palette cards in one row start their name and swatch on one line', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/settings')
  await page.getByRole('button', { name: 'Appearance', exact: true }).click()
  const cards = await page.getByRole('radiogroup', { name: 'Palette' }).evaluate((group) =>
    [...group.querySelectorAll('[role=radio]')].map((card) => ({
      top: Math.round(card.getBoundingClientRect().top),
      name: card.querySelector('[id^=palette-]')!.getBoundingClientRect().top,
      swatch: card.querySelector('div[aria-hidden=true]')!.getBoundingClientRect().bottom, // the mock, not the check icon
    })),
  )
  const rows = new Map<number, typeof cards>()
  for (const card of cards) rows.set(card.top, [...(rows.get(card.top) ?? []), card])
  expect([...rows.values()].some((row) => row.length > 1)).toBe(true)
  for (const row of rows.values()) {
    expect(Math.max(...row.map((c) => c.name)) - Math.min(...row.map((c) => c.name))).toBeLessThanOrEqual(1)
    expect(Math.max(...row.map((c) => c.swatch)) - Math.min(...row.map((c) => c.swatch))).toBeLessThanOrEqual(1)
  }
  expect(errors).toEqual([])
})

test('a selected choice has its accent border on all four sides', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  await page.getByRole('checkbox', { name: 'Set the audio tracks' }).check()
  const rules = page.getByText('By rules', { exact: true })
  await rules.click()
  await expect(rules).toHaveAttribute('data-state', 'on')
  const sides = await rules.evaluate((el) => {
    const cs = getComputedStyle(el)
    return [cs.borderTopWidth, cs.borderRightWidth, cs.borderBottomWidth, cs.borderLeftWidth]
  })
  expect(sides).toEqual(['1px', '1px', '1px', '1px'])
  expect(errors).toEqual([])
})

test('filter values read as figures', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  // The fixture's template has no filter steps: serve it with the crop and resize steps, whose rows show values.
  const presets = await page.evaluate(() => fetch('/api/presets').then((r) => r.json()))
  const step = (category: string, name: string) => ({ category, name, script: '', enabled: true })
  presets.template[0].data.video.filters = [step('crop', 'Crop'), step('resize', 'Resize')]
  await page.route('**/api/presets', (route) => route.fulfill({ json: presets }))
  // The page saves its open draft as it unloads; drop it before the app starts, or the old draft comes back.
  await page.addInitScript(() => sessionStorage.removeItem('videoforge.draft.templates'))
  await page.reload()
  const video = page.locator('[data-slot=card]').filter({ hasText: 'Source filter' })
  await expect(video.getByText('off', { exact: true })).toHaveCSS('font-family', /^"?Cascadia Mono/)
  expect(errors).toEqual([])
})

test('Templates at 320 px: a filter step shows its whole name, with its value beside or below it', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const presets = await page.evaluate(() => fetch('/api/presets').then((r) => r.json()))
  const step = (category: string, name: string) => ({ category, name, script: '', enabled: true })
  presets.template[0].data.video.filters = [step('crop', 'Crop'), step('resize', 'Resize')]
  await page.route('**/api/presets', (route) => route.fulfill({ json: presets }))
  await page.addInitScript(() => sessionStorage.removeItem('videoforge.draft.templates'))
  await page.reload()
  await page
    .getByRole('list', { name: 'Templates' })
    .getByRole('button', { name: 'Film 1080p CEL', exact: true })
    .click()
  const steps = page.locator('[data-slot=card]').filter({ hasText: 'Source filter' }).locator('ol > li')
  for (const name of ['Crop', 'Resize']) {
    const label = steps.getByText(name, { exact: true })
    expect(await label.evaluate((el) => el.scrollWidth - el.clientWidth), name).toBeLessThanOrEqual(0)
    // the value goes below the name only when the row has no room for both
    const value = (await steps.filter({ hasText: name }).locator('.readout').boundingBox())!
    const box = (await label.boundingBox())!
    expect(value.x >= box.x + box.width || value.y >= box.y + box.height - 1, `${name}'s value clear of it`).toBe(true)
  }
  const crop = (await steps.getByText('Crop', { exact: true }).boundingBox())!
  expect((await steps.filter({ hasText: 'Crop' }).locator('.readout').boundingBox())!.y).toBeGreaterThan(crop.y) // "per job" moved below
  expect(errors).toEqual([])
})

test('controls animate only color and movement, and a dialog does not blur the page', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  // Buttons, button groups and badges name what they animate instead of "all".
  const animated = await page.evaluate(() =>
    [...document.querySelectorAll('[data-slot=button], [data-slot=toggle-group-item], [data-slot=badge]')].map(
      (el) => getComputedStyle(el).transitionProperty,
    ),
  )
  expect(animated.length).toBeGreaterThan(3)
  expect(animated.filter((p) => p.split(', ').includes('all'))).toEqual([])
  // A pressed button moves down 1 px with `translate` (Tailwind 4's translate-y sets that property, not transform).
  const button = page.getByRole('button', { name: 'Keyboard shortcuts', exact: true })
  expect((await button.evaluate((el) => getComputedStyle(el).transitionProperty)).split(', ')).toContain('translate')
  await page.getByRole('button', { name: 'Keyboard shortcuts', exact: true }).click()
  await expect(page.locator('[data-slot=dialog-overlay]')).toHaveCSS('backdrop-filter', 'none')
  expect(errors).toEqual([])
})

test('Matched files shows no empty box before a source is added', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/new')
  const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: 'Matched files' }) })
  expect((await card.boundingBox())!.height).toBeLessThanOrEqual(48)
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

test('pages and Settings: no text under 12 px, no uppercase labels, no italics', async ({ page }) => {
  const errors = await layoutFixture(page)
  const problems: string[] = []
  for (const route of ['new', 'templates', 'log']) {
    await page.goto(`/#/${route}`)
    await expect(page.locator('main h1, main h2').first()).toBeVisible()
    problems.push(...(await typeProblems(page)).map((p) => `${route}: ${p}`))
  }
  await page.goto('/#/settings')
  const sections = page.getByRole('navigation', { name: 'Settings sections' }).getByRole('button')
  for (const name of await sections.allInnerTexts()) {
    if (/shut down/i.test(name)) continue
    await sections.filter({ hasText: name.trim() }).first().click()
    problems.push(...(await typeProblems(page)).map((p) => `Settings ${name.trim()}: ${p}`))
  }
  expect([...new Set(problems)]).toEqual([])
  expect(errors).toEqual([])
})

/** How far a label sits above or below the control beside it: the distance between their vertical centers, in px. */
async function labelGap(label: Locator, control: Locator): Promise<number> {
  const a = (await label.boundingBox())!
  const b = (await control.boundingBox())!
  return Math.abs(a.y + a.height / 2 - (b.y + b.height / 2))
}

for (const width of [1600, 1280]) {
  test(`New jobs labels line up with their controls at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = await layoutFixture(page, undefined, [{ id: 'house', name: 'House rules' }])
    await page.goto('/#/new')
    const main = page.locator('main')
    for (const [label, control] of [
      ['Rule set', main.getByRole('combobox', { name: 'Rule set', exact: true })],
      ['Original language', main.getByRole('combobox', { name: 'Original language', exact: true })],
      ['Template', main.getByRole('combobox', { name: 'Template', exact: true })],
      ['Encoder preset', main.getByRole('button', { name: /^Encoder preset/ })],
      ['Container', main.getByRole('combobox', { name: 'Container', exact: true })],
    ] as const)
      expect(await labelGap(main.getByText(label, { exact: true }), control), label).toBeLessThanOrEqual(2)
    expect(errors).toEqual([])
  })
}

/** Each text's top edge on the page, in the order given. */
async function tops(page: Page, texts: string[]): Promise<number[]> {
  const main = page.locator('main')
  return Promise.all(texts.map(async (t) => (await main.getByText(t, { exact: true }).boundingBox())!.y))
}

test('New jobs asks in decision order, and shows Rule set only when there is a choice', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/new')
  const main = page.locator('main')
  // One rule set (a new user's Manual): no menu, no paragraph about it.
  await expect(main.getByText('Template', { exact: true })).toBeVisible()
  await expect(main.getByRole('combobox', { name: 'Rule set' })).toHaveCount(0)
  await expect(main.getByText(/The rule set picks each job's tracks/)).toHaveCount(0)
  const order = ['Sources', 'Output folder', 'Original language', 'Template', 'Encoder preset', 'Container']
  const y = await tops(page, [...order, 'After adding'])
  expect(y).toEqual([...y].sort((a, b) => a - b))
  await expect(
    main.getByText(
      "Template audio rules and some rule sets choose tracks by it. Left empty, VideoForge reads it from the source's audio.",
    ),
  ).toBeVisible()
  await expect(
    main.getByText('The encoder preset and the container change only their part of the template.'),
  ).toBeVisible()
  await expect(main.getByText(/Changes encoder settings only/)).toHaveCount(0)
  expect(errors).toEqual([])
})

test('New jobs shows Rule set, first after the output folder, with two rule sets', async ({ page }) => {
  const errors = await layoutFixture(page, undefined, [{ id: 'house', name: 'House rules' }])
  await page.goto('/#/new')
  const main = page.locator('main')
  await expect(main.getByRole('combobox', { name: 'Rule set', exact: true })).toBeVisible()
  await expect(main.getByText(/The rule set picks each job's tracks/)).toBeVisible()
  const y = await tops(page, ['Output folder', 'Rule set', 'Original language'])
  expect(y).toEqual([...y].sort((a, b) => a - b))
  expect(errors).toEqual([])
})

test('New jobs: After adding stays level with its checkboxes, ticked or not', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/new')
  const label = page.getByText('After adding', { exact: true })
  const index = page.getByRole('checkbox', { name: /^Index/ })
  for (let i = 0; i < 2; i++) {
    expect(await labelGap(label, index), `Index ${await index.getAttribute('aria-checked')}`).toBeLessThanOrEqual(2)
    await index.click() // a checkbox's own baseline changes with its tick
  }
  expect(errors).toEqual([])
})

test('Settings › Tools: each tool name lines up with its path box', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/settings')
  await page.getByRole('button', { name: 'Tools', exact: true }).click()
  const path = page.getByRole('textbox', { name: 'ffmpeg path', exact: true })
  // A 14 px name beside a 12 px path: their baselines meet, so their centers differ by a pixel or so.
  expect(await labelGap(page.getByText('ffmpeg', { exact: true }), path)).toBeLessThanOrEqual(3)
  expect(errors).toEqual([])
})

test('Templates › Video: Crop sits beside its choices, like Source filter', async ({ page }) => {
  const errors = await layoutFixture(page)
  await page.goto('/#/templates')
  const video = page.locator('[data-slot=card]').filter({ hasText: 'Source filter' })
  const crop = video.getByText('Crop', { exact: true }).first()
  const keep = video.getByText("Keep each job's", { exact: true })
  const source = await video.getByText('Source filter', { exact: true }).boundingBox()
  const label = (await crop.boundingBox())!
  expect(Math.abs(label.x - source!.x)).toBeLessThanOrEqual(1)
  expect(label.x + label.width).toBeLessThan((await keep.boundingBox())!.x)
  expect(await labelGap(crop, keep)).toBeLessThanOrEqual(2)
  expect(errors).toEqual([])
})
