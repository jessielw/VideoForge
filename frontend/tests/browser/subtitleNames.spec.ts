import { test, expect, type Page } from '@playwright/test'
import type { JobDetail, Overrides, Profile, SubTrack } from '../../src/lib/types.ts'

const sub = (id: number, language: string, title: string, flags: Partial<SubTrack> = {}): SubTrack => ({
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
  element_count: null,
  external_path: null,
  detected: {},
  ...flags,
})

async function fixture(page: Page) {
  const errors: string[] = []
  const saves: Overrides[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const subs = [
    sub(2, 'en', ''),
    sub(3, 'en', '', { forced: true }),
    sub(4, 'es-419', 'Spanish', { hearing_impaired: true }),
    sub(5, 'fr-CA', ''), // left out: not named
  ]
  const video = {
    source_filter: 'ffms2' as const,
    crop: { left: 0, top: 0, right: 0, bottom: 0 },
    resize: null,
    filters: [],
    custom: null,
  }
  const encoder = {
    encoder: 'x265' as const,
    rate_control: 'crf' as const,
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
  }
  const mux = { container: 'mkv', extra: '', pgs_zlib: false }
  const job: JobDetail = {
    id: 'names',
    name: 'Subtitle names',
    label: '',
    source: 'D:/Show.mkv',
    profile: 'manual',
    status: 'ready',
    progress: null,
    issue: '',
    output: null,
    encoder: 'x265',
    crop: null,
    custom_script: false,
    indexed: false,
    index_error: '',
    index_held: false,
    audio: [],
    subs: 3,
    issues: [],
    steps: {},
    plan: {
      encode_path: null,
      resolution: '1080p',
      original_language: 'en',
      chapters_path: null,
      audio: [],
      subs: subs.slice(0, 3).map((s) => ({
        source: s,
        slot: '',
        language: s.language,
        title: s.title,
        default: false,
        forced: s.forced,
        hearing_impaired: s.hearing_impaired,
        visual_impaired: false,
        commentary: false,
        original: false,
      })),
      burn: null,
      issues: [],
      profile: 'manual',
    },
    output_name: null,
    color_args: null,
    target: null,
    tracks: { video: null, audio: [], subs, has_chapters: false, count: 4 },
    spec: {
      id: 'names',
      profile: 'manual',
      inputs: { source: 'D:/Show.mkv', encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
      video,
      encoder,
      mux,
      overrides: {
        original_language: null,
        audio_track_ids: null,
        order: null,
        copies: [],
        tracks: {
          'id:5': {
            exclude: true,
            language: null,
            title: null,
            flags: {},
            action: null,
            bitrate_kbps: null,
            layout: null,
            options: {},
          },
        },
      },
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
  const profile: Profile = {
    id: 'manual',
    name: 'Manual',
    default: true,
    container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }],
    external_subtitles: true,
    track_editor: true,
    track_properties: [],
    defaults: {
      video,
      encoder,
      template: { video, encoder, mux, qpf: false, crop_mode: 'keep', audio: null, subs: null },
    },
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/jobs/names' && request.method() === 'PATCH') {
      job.spec.overrides = request.postDataJSON().overrides
      saves.push(structuredClone(job.spec.overrides))
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [job],
      '/api/jobs/names': job,
      '/api/profiles': [profile],
      '/api/presets': { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] },
      '/api/health': { ok: true, version: 'test' },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config/video-options/x265': { dashes: '--', options: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected subtitle names request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/queue/names')
  await page.getByRole('tab', { name: 'Subtitles', exact: true }).click()
  return { saves, errors }
}

const titles = (o: Overrides | undefined) =>
  Object.fromEntries(Object.entries(o?.tracks ?? {}).map(([k, v]) => [k, v.title]))

test('Name subtitles titles the untitled kept tracks, then all of them, from language and flags', async ({ page }) => {
  const { saves, errors } = await fixture(page)
  const menu = page.getByRole('button', { name: /Name subtitles/ })
  await menu.click()
  await expect(page.getByRole('menuitem', { name: /Name untitled tracks/ })).toContainText('2')
  await page.getByRole('menuitem', { name: /Name untitled tracks/ }).click()
  await expect.poll(() => titles(saves.at(-1))).toEqual({ 'id:2': 'English', 'id:3': 'English (Forced)', 'id:5': null })

  await menu.click()
  await page.getByRole('menuitem', { name: 'Rename all kept tracks' }).click()
  await expect
    .poll(() => titles(saves.at(-1)))
    .toEqual({
      'id:2': 'English',
      'id:3': 'English (Forced)',
      'id:4': 'Spanish (Latin America) (SDH)',
      'id:5': null,
    })
  expect(errors).toEqual([])
})
