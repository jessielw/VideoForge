import { test, expect, type Page } from '@playwright/test'
import type { ConfigState, EncoderSettings, Presets, Profile, Template, TemplateBundle } from '../../src/lib/types.ts'

const video: EncoderSettings = {
  encoder: 'x264',
  rate_control: 'crf',
  crf: 18,
  bitrate_kbps: 8000,
  target_mb: null,
  preset: 'slow',
  tune: '',
  depth: 8,
  options: {},
  extra: '',
  source_color: true,
  hdr10plus: false,
  dolby_vision: false,
}

async function fixture(page: Page) {
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
    mux: { container: 'mkv', extra: '', pgs_zlib: false },
    qpf: true,
    crop_mode: 'keep',
    audio: null,
    subs: null,
  }
  const profile: Profile = {
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
  const names = ['Loose', 'Group / 1080p / Film', 'Group / 1080p / Grain']
  const presets: Presets = {
    video: [],
    encoder: [],
    audio: [],
    template: names.map((name) => ({ name, data: template })),
    template_defaults: {},
    encoder_starters: [],
  }
  const config: ConfigState = {
    tools: [],
    roots: [],
    roots_custom: false,
    default_roots: [],
    profile: 'manual',
    profile_default: 'manual',
    profiles: [profile],
    restart: [],
    index_waits_for_disk: true,
    sample_quality: false,
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
    notifications: [],
    notification_events: [],
    actions: [],
    action_kinds: [],
    action_tokens: { job: {}, queue: {} },
    allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  const calls: string[] = []
  const deletes: { kind: string; names: string[] }[] = []
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const keepBoth = url.searchParams.get('keep_both') === 'true'
    if (path === '/api/presets/templates/preview' || path === '/api/presets/templates/import') {
      calls.push(`${path.split('/').pop()}${keepBoth ? ' keep both' : ''}`)
      const bundle: TemplateBundle = request.postDataJSON()
      const plan = keepBoth
        ? { names: bundle.templates.map((t) => `${t.name} (2)`), actions: bundle.templates.map(() => 'copy') }
        : {
            names: bundle.templates.map((t) => t.name),
            actions: bundle.templates.map((t) => (t.name === 'Loose' ? 'unchanged' : 'replaced')),
          }
      return route.fulfill({ json: path.endsWith('preview') ? { bundle, ...plan } : { presets, ...plan } })
    }
    if (path === '/api/presets/delete') {
      const body = request.postDataJSON() as { kind: string; names: string[] }
      deletes.push(body)
      presets.template = presets.template.filter((t) => !body.names.includes(t.name))
      return route.fulfill({ json: presets })
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [],
      '/api/profiles': [profile],
      '/api/presets': presets,
      '/api/health': { ok: true, version: 'test' },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config/video-options/x264': { dashes: '--', options: [] },
      '/api/config': config,
      '/api/config/tools': [],
      '/api/settings': { output_dir: 'D:/Output', last_dir: '' },
      '/api/plugins': { folder: 'plugins', items: [], failures: [], management_enabled: true, restart: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected preset cleanup request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/templates')
  return { errors, calls, deletes, template }
}

test('importing templates again replaces them; Keep both adds numbered copies', async ({ page }, testInfo) => {
  const { errors, calls, template } = await fixture(page)
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Import templates' })
  const file = {
    format: 'videoforge.templates',
    version: 1,
    templates: [
      { name: 'Loose', data: template },
      { name: 'Group / 1080p / Film', data: template },
    ],
  }
  await dialog
    .locator('input[type=file]')
    .setInputFiles({ name: 'pack.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(file)) })
  await expect(dialog).toContainText('1 replace yours · 1 unchanged')
  await expect(dialog).toContainText('Group / 1080p / Filmreplaces yours')
  await expect(dialog).toContainText('Loosealready the same')
  await page.screenshot({ path: testInfo.outputPath('import-replace.png'), animations: 'disabled' })

  await dialog.getByRole('checkbox', { name: /Keep both/ }).check()
  await expect(dialog).toContainText('2 numbered copies')
  await expect(dialog).toContainText('Loose → Loose (2)')
  await dialog.getByRole('checkbox', { name: /Keep both/ }).uncheck()
  await expect(dialog).toContainText('1 replace yours · 1 unchanged')
  await dialog.getByRole('button', { name: 'Import 2' }).click()
  await expect(dialog).toHaveCount(0)
  expect(calls).toEqual(['preview', 'preview keep both', 'preview', 'import'])
  expect(errors).toEqual([])
})

test('Select deletes several templates at once; a folder picks everything in it', async ({ page }, testInfo) => {
  const { errors, deletes } = await fixture(page)
  const list = page.getByRole('list', { name: 'Templates' })
  await page.getByRole('button', { name: 'Select', exact: true }).click()
  await expect(page.getByRole('button', { name: 'New template' })).toHaveCount(0)
  await list.getByRole('checkbox', { name: 'Select everything in 1080p' }).check()
  await expect(list.getByRole('checkbox', { name: 'Select everything in Group' })).toBeChecked()
  await list.getByRole('checkbox', { name: 'Select Group / 1080p / Grain' }).uncheck()
  await expect(list.getByRole('checkbox', { name: 'Select everything in 1080p' })).toHaveAttribute(
    'data-state',
    'indeterminate',
  )
  await list.getByRole('button', { name: 'Grain', exact: true }).click() // the name toggles it too
  await list.getByRole('checkbox', { name: 'Select Loose' }).check()
  await expect(page.getByText('3 selected')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('template-select.png'), animations: 'disabled' })
  await page.getByRole('button', { name: 'Delete 3' }).click()
  await expect(page.getByRole('alert')).toContainText("Delete 3 templates? This can't be undone.")
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect
    .poll(() => deletes)
    .toEqual([{ kind: 'template', names: ['Group / 1080p / Film', 'Group / 1080p / Grain', 'Loose'] }])
  await expect(page.getByRole('button', { name: 'New template' })).toBeVisible()
  await expect(list.getByRole('button', { name: /Group/ })).toHaveCount(0)
  expect(errors).toEqual([])
})
