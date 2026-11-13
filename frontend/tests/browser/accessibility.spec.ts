import { test, expect, type Page, type WebSocketRoute } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { AudioTrack, ConfigState, JobDetail, RuleSet, SubTrack, Template } from '../../src/lib/types.ts'

// Every page, job tab and main dialog passes axe (WCAG 2.2 AA), in light and dark mode and in every palette.
const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const PALETTES = ['gold', 'indigo', 'ocean', 'forest', 'ember', 'rose', 'slate']

const sub = (id: number, language: string, title: string): SubTrack => ({
  key: `id:${id}`,
  id,
  index: id,
  format: 'srt',
  language,
  title,
  default: false,
  forced: false,
  hearing_impaired: false,
  visual_impaired: false,
  commentary: false,
  original: false,
  element_count: 27,
  external_path: null,
  detected: {},
})

const audio = (id: number, language: string, title: string): AudioTrack => ({
  key: `id:${id}`,
  id,
  index: id - 1,
  codec: 'flac',
  layout: '5.1',
  language,
  title,
  default: id === 1,
  forced: false,
  hearing_impaired: false,
  visual_impaired: false,
  commentary: false,
  original: false,
  atmos: false,
  dtsx: false,
  bitrate_kbps: 2189,
  delay_ms: 0,
  format_name: 'FLAC',
  detected: {},
  sample_rate: 48000,
  bit_depth: 24,
  size_bytes: 36_000_000,
  duration_ms: 137_000,
  copy: 0,
})

async function fixture(page: Page, mode: 'light' | 'dark', palette = 'gold') {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const video = {
    source_filter: 'ffms2' as const,
    crop: { left: 0, top: 20, right: 0, bottom: 20 },
    resize: null,
    filters: [],
    custom: null,
  }
  const encoder = {
    encoder: 'x264' as const,
    rate_control: 'crf' as const,
    crf: 18,
    bitrate_kbps: 0,
    target_mb: null,
    preset: 'slow',
    tune: '',
    depth: 8,
    options: {},
    extra: '',
    source_color: true,
    color_override: false,
    hdr10plus: false,
    dolby_vision: false,
  }
  const mux = { container: 'mkv', extra: '', pgs_zlib: false }
  const template: Template = {
    video,
    encoder: { ...encoder, rate_control: '2pass', bitrate_kbps: 8000, target_mb: 5000 }, // shows Target size
    mux,
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
    track_properties: [
      { key: 'default', label: 'Default', kind: 'audio', help: 'The track players pick' },
      { key: 'commentary', label: 'Commentary', kind: 'audio', help: 'A commentary track' },
      { key: 'forced', label: 'Forced', kind: 'sub', help: 'Shown even when subtitles are off' },
      { key: 'hearing_impaired', label: 'SDH', kind: 'sub', help: 'For the deaf and hard of hearing' },
    ],
    defaults: { video, encoder, template },
  }
  const tracks = {
    video: null,
    audio: [
      audio(1, 'en', ''),
      audio(2, 'ja', ''),
      { ...audio(3, 'en', "Director's Commentary"), commentary: true, detected: { commentary: true } },
    ],
    subs: [
      sub(4, 'en', ''),
      { ...sub(5, 'en', 'SDH'), hearing_impaired: true, detected: { hearing_impaired: true } },
      sub(6, 'ja', ''),
    ],
    has_chapters: false,
    count: 7,
  }
  const job: JobDetail = {
    id: 'a11y',
    name: 'Show.S01E01.mkv',
    label: '',
    source: 'D:/Media/Show.S01E01.mkv',
    rule_set: 'manual',
    status: 'ready',
    progress: null,
    issue: '',
    output: null,
    encoder: 'x264',
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
    subs: 3,
    issues: [],
    steps: {},
    made: null,
    plan: {
      encode_path: null,
      resolution: '1080p',
      original_language: 'en',
      chapters_path: null,
      audio: tracks.audio.map((source) => ({
        source,
        action: 'copy' as const,
        out_codec: 'flac',
        out_layout: '5.1',
        out_atmos: false,
        bitrate_kbps: null,
        upmix_50: false,
        language: source.language,
        title: source.title,
        default: source.default,
        forced: false,
        hearing_impaired: source.hearing_impaired,
        commentary: source.commentary, // pressed flag pills in the track rows
        original: false,
        visual_impaired: false,
        options: {},
        sync_ms: 0,
      })),
      subs: tracks.subs.map((source) => ({
        source,
        slot: `${source.language}_srt`,
        language: source.language,
        title: source.title,
        default: false,
        forced: false,
        hearing_impaired: source.hearing_impaired,
        visual_impaired: false,
        commentary: false,
        original: false,
      })),
      burn: null,
      issues: [],
      rule_set: 'manual',
    },
    output_name: null,
    color_args: null,
    target: null,
    sample: null,
    search: null,
    compare: { encode: false, sample: false },
    tracks,
    spec: {
      id: 'a11y',
      rule_set: 'manual',
      inputs: {
        source: 'D:/Media/Show.S01E01.mkv',
        encode: null,
        subtitles: [],
        chapters: null,
        encode_state: '',
        audio: [],
      },
      video,
      encoder,
      mux,
      overrides: { original_language: 'en', audio_track_ids: null, order: null, copies: [], tracks: {} },
      qpf: true,
      output_dir: 'D:/Output',
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
    roots: ['D:\\'],
    roots_custom: false,
    default_roots: ['D:\\'],
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
    records_dir: 'D:\\VideoForge\\records',
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [{ id: 'move', label: 'Move output' }],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  const responses: Record<string, unknown> = {
    '/api/jobs': [job],
    '/api/jobs/a11y': job,
    '/api/jobs/a11y/log-snapshot': { seq: 0, steps: [], lines: [] },
    '/api/rule-sets': [ruleSet],
    '/api/health': { ok: true, version: 'test' },
    '/api/profiles': { profiles: [{ id: 'default', name: 'Default' }], active: 'default' },
    '/api/presets': {
      video: [],
      encoder: [],
      audio: [],
      template: [{ name: 'Film', data: template }],
      template_defaults: { manual: 'Film' },
      encoder_starters: [],
    },
    '/api/preset-packs/managed': { presets: [], problems: [] },
    '/api/filter-presets': [],
    '/api/config/encoders': [],
    '/api/config/video-options/x264': { dashes: '--', options: [{ name: 'bframes', help: 'Consecutive B-frames' }] },
    '/api/settings': { output_dir: 'D:\\Output', last_dir: 'D:\\Media' },
    '/api/config': config,
    '/api/config/tools': [],
    '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    '/api/fs/roots': ['D:\\'],
    '/api/fs/list': {
      path: 'D:\\Media',
      parent: 'D:\\',
      dirs: [{ name: 'Season 01', path: 'D:\\Media\\Season 01' }],
      files: [{ name: 'Show.S01E01.mkv', path: 'D:\\Media\\Show.S01E01.mkv', size: 1_000_000, mtime: 0 }],
    },
  }
  await page.addInitScript(
    ([m, p]) => {
      localStorage.setItem('videoforge.mode', m)
      localStorage.setItem('videoforge.palette', p)
    },
    [mode, palette],
  )
  let socket: WebSocketRoute | null = null
  await page.routeWebSocket('**/api/events', (ws) => {
    socket = ws
  })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path in responses) return route.fulfill({ json: responses[path] })
    return route.fulfill({ status: 404, json: { detail: `not mocked: ${path}` } })
  })
  // Enough log lines that the log scrolls.
  const fillLog = () => {
    for (let i = 0; i < 200; i++) socket?.send(JSON.stringify({ type: 'log', id: 'a11y', line: `line ${i}`, seq: i }))
  }
  return { errors, fillLog }
}

async function violations(page: Page, rules?: string[]) {
  const builder = rules ? new AxeBuilder({ page }).withRules(rules) : new AxeBuilder({ page }).withTags(WCAG)
  return (await builder.analyze()).violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
  )
}

const nav = (page: Page, name: string) =>
  page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name, exact: false }).first().click()

for (const mode of ['light', 'dark'] as const) {
  test(`every page, job tab and main dialog passes axe in ${mode} mode`, async ({ page }) => {
    test.setTimeout(120_000)
    const { errors, fillLog } = await fixture(page, mode)
    const found: Record<string, string[]> = {}
    const check = async (state: string) => {
      await page.waitForTimeout(300)
      const v = await violations(page)
      if (v.length) found[state] = v
    }

    await page.goto('/#/new')
    await expect(page.getByRole('heading', { name: 'New jobs', level: 1 })).toBeVisible()
    await check('new jobs')
    await page.getByRole('button', { name: 'Browse…' }).first().click()
    await expect(page.getByRole('dialog')).toContainText('Show.S01E01.mkv')
    await check('file browser')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Keyboard shortcuts' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await check('shortcuts')
    await page.keyboard.press('Escape')

    await nav(page, 'Queue')
    await expect(page.getByText('Show.S01E01.mkv').first()).toBeVisible()
    await check('queue')
    await page.goto('/#/queue/a11y')
    for (const tab of ['Video', 'Encoder', 'Audio', 'Subtitles', 'Output', 'Log']) {
      await page.getByRole('tab', { name: tab, exact: true }).click()
      await check(`job ${tab}`)
    }

    await nav(page, 'Templates')
    await expect(page.getByText('Film').first()).toBeVisible()
    await check('templates')
    await nav(page, 'Settings')
    for (const section of [
      'Jobs',
      'Queue & indexing',
      'Presets',
      'Files & folders',
      'Tools',
      'Plugins',
      'Automation',
      'Appearance',
      'Profiles',
      'Import & export',
    ]) {
      await page
        .getByRole('navigation', { name: 'Settings sections' })
        .getByRole('button', { name: section, exact: true })
        .click()
      await check(`settings ${section}`)
    }
    await nav(page, 'Log')
    fillLog()
    await expect(page.getByText('line 199')).toBeVisible()
    await check('log')

    expect(found).toEqual({})
    expect(errors).toEqual([])
  })
}

test('a skip link jumps past the menu to the page', async ({ page }) => {
  const { errors } = await fixture(page, 'light')
  await page.goto('/#/new')
  await expect(page.getByRole('heading', { name: 'New jobs', level: 1 })).toBeVisible()
  await page.keyboard.press('Tab')
  const skip = page.getByRole('button', { name: 'Skip to main content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeInViewport()
  await page.keyboard.press('Enter')
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => !!document.activeElement?.closest('main'))).toBe(true)
  expect(errors).toEqual([])
})

test('the Queue menu item says what its count counts, open or collapsed', async ({ page }) => {
  const { errors } = await fixture(page, 'light')
  await page.goto('/#/new')
  const menu = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(menu.getByRole('button', { name: 'Queue 1 job', exact: true })).toBeVisible()
  await menu.getByRole('button', { name: 'Collapse the menu' }).click()
  await expect(menu.getByRole('button', { name: 'Queue 1 job', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('the job tabs name their list and their panel', async ({ page }) => {
  const { errors } = await fixture(page, 'light')
  await page.goto('/#/queue/a11y')
  await expect(page.getByRole('tablist', { name: 'Job sections' })).toBeVisible()
  for (const tab of ['Audio', 'Output']) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    await expect(page.getByRole('tabpanel', { name: tab, exact: true })).toBeVisible()
  }
  expect(errors).toEqual([])
})

test('suggestion lists open when asked, not on focus, and are not a Tab stop', async ({ page }) => {
  const { errors } = await fixture(page, 'light')
  await page.goto('/#/new')
  const language = page.getByRole('combobox', { name: 'Original language' })
  await language.focus()
  await expect(language).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await language.pressSequentially('jap')
  await expect(page.getByRole('listbox')).toHaveAttribute('tabindex', '-1')
  await expect(page.getByRole('option', { name: /Japanese/ })).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('listbox')).toHaveCount(0)

  await page.goto('/#/queue/a11y')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  const option = page.getByRole('combobox', { name: 'New option name' })
  await option.focus()
  await expect(option).toHaveAttribute('aria-expanded', 'false')

  await page.goto('/#/templates')
  const size = page.getByRole('combobox', { name: 'Target size' })
  await size.focus()
  await expect(size).toHaveAttribute('aria-expanded', 'false')
  await size.press('Alt+ArrowDown') // a number box keeps the arrows for stepping: Alt+Down asks for the list
  await expect(page.getByRole('listbox').getByRole('option', { name: /BD$/ }).first()).toBeVisible()
  expect(errors).toEqual([])
})

test('checkbox and palette names leave their help text to the description', async ({ page }) => {
  const { errors } = await fixture(page, 'light')
  await page.goto('/#/settings')
  const settings = page.getByRole('navigation', { name: 'Settings sections' })
  await settings.getByRole('button', { name: 'Appearance', exact: true }).click()
  const gold = page.getByRole('radio', { name: 'Gold', exact: true })
  await expect(gold).toHaveAccessibleDescription(/original look/)
  const black = page.getByRole('checkbox', { name: 'Pure black dark mode', exact: true })
  await expect(black).toHaveAccessibleDescription(/OLED/)
  for (const [category, name, help] of [
    ['Queue & indexing', 'Index new jobs', /preview is ready/],
    ['Queue & indexing', 'Auto-crop new jobs', /crop is detected/],
    ['Queue & indexing', 'Wait while an encode reads the same disk', /jobs on other disks go first/],
    ['Queue & indexing', 'Index anyway while it only encodes video', /reads the source slowly/],
    ['Files & folders', "Delete a job's work folder once it's done", /deleted after the job succeeds/],
    ['Jobs', 'Score its quality', /compare every frame/],
  ] as const) {
    await settings.getByRole('button', { name: category, exact: true }).click()
    await expect(page.getByRole('checkbox', { name, exact: true })).toHaveAccessibleDescription(help)
  }
  await page.goto('/#/queue/a11y')
  await page.getByRole('tab', { name: 'Encoder', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: 'Colour from the source', exact: true })).toHaveAccessibleDescription(
    /colour description/,
  )
  expect(errors).toEqual([])
})

test('track rows have no unnamed buttons', async ({ page }) => {
  const { errors } = await fixture(page, 'light')
  await page.goto('/#/queue/a11y')
  for (const tab of ['Audio', 'Subtitles']) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    await expect(page.getByRole('textbox', { name: 'Title' }).first()).toBeVisible()
    const tree = await page.getByRole('region', { name: 'Job settings' }).ariaSnapshot()
    expect(tree).not.toMatch(/^\s*- button(\s*\[[^\]]*\])*\s*$/m)
  }
  expect(errors).toEqual([])
})

test('every palette keeps text contrast in light mode', async ({ page }) => {
  test.setTimeout(120_000)
  const found: Record<string, string[]> = {}
  for (const palette of PALETTES) {
    await fixture(page, 'light', palette)
    for (const [state, url] of [
      ['job video', '/#/queue/a11y'],
      ['templates', '/#/templates'],
    ]) {
      await page.goto(url)
      await page.waitForTimeout(800)
      const v = await violations(page, ['color-contrast'])
      if (v.length) found[`${palette} ${state}`] = v
    }
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  }
  expect(found).toEqual({})
})
