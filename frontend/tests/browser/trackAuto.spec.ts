import { test, expect, type Page } from '@playwright/test'
import type { AudioEncodeInfo, AudioTrack, JobDetail, Overrides, Profile, SubTrack } from '../../src/lib/types.ts'

// A profile with its own rules (track_editor + picks_tracks): the editor starts from each track's auto values.
const sub = (id: number, language: string, title: string, format: string, auto: SubTrack['auto']): SubTrack => ({
  key: `id:${id}`,
  id,
  index: id,
  format,
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
  auto,
})

async function fixture(page: Page) {
  const errors: string[] = []
  const saves: Overrides[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const audio: AudioTrack = {
    key: 'id:1',
    id: 1,
    index: 0,
    codec: 'truehd',
    layout: '7.1',
    language: 'en',
    title: 'Surround 7.1',
    default: true,
    forced: false,
    hearing_impaired: false,
    visual_impaired: false,
    commentary: false,
    original: false,
    atmos: false,
    dtsx: false,
    bitrate_kbps: null,
    delay_ms: 0,
    format_name: 'TrueHD',
    detected: {},
    sample_rate: 48000,
    bit_depth: 24,
    size_bytes: null,
    duration_ms: null,
    copy: 0,
    auto: { kept: true, title: 'DDP 5.1', language: 'en', action: 'ddp', layout: '5.1', bitrate_kbps: 640 },
  }
  const subs = [
    sub(2, 'en-US', 'English', 'srt', { kept: true, title: 'English (SRT)', language: 'en' }),
    sub(3, 'fr', '', 'pgs', { kept: false }), // the rules leave it out
  ]
  const ddp: AudioEncodeInfo = {
    id: 'ddp',
    label: 'DDP',
    codec: 'eac3',
    layouts: ['2.0', '5.1'],
    bitrates: { 2: 256, 6: 640 },
    bitrate_choices: [],
    bitrate_range: [32, 1024],
    per_channel_max: null,
    vbr_default: false,
    default_max: null,
    missing: [],
    options: [],
  }
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
    id: 'auto',
    name: 'Rules',
    label: '',
    source: 'D:/Film.mkv',
    profile: 'group',
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
    subs: 1,
    issues: [],
    steps: {},
    plan: {
      encode_path: null,
      resolution: '1080p',
      original_language: 'en',
      chapters_path: null,
      audio: [
        {
          source: audio,
          action: 'ddp',
          out_codec: 'eac3',
          out_layout: '5.1',
          out_atmos: false,
          bitrate_kbps: 640,
          upmix_50: false,
          language: 'en',
          title: 'DDP 5.1',
          default: true,
          forced: false,
          hearing_impaired: false,
          commentary: false,
          original: false,
          visual_impaired: false,
          options: {},
          sync_ms: 0,
        },
      ],
      subs: [
        {
          source: subs[0],
          slot: 'en_srt',
          language: 'en',
          title: 'English (SRT)',
          default: false,
          forced: false,
          hearing_impaired: false,
          visual_impaired: false,
          commentary: false,
          original: false,
        },
      ],
      burn: null,
      issues: [],
      profile: 'group',
    },
    output_name: null,
    color_args: null,
    target: null,
    tracks: { video: null, audio: [audio], subs, has_chapters: false, count: 3 },
    spec: {
      id: 'auto',
      profile: 'group',
      inputs: { source: 'D:/Film.mkv', encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
      video,
      encoder,
      mux,
      overrides: { original_language: 'en', audio_track_ids: null, order: null, copies: [], tracks: {} },
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
    id: 'group',
    name: 'Group',
    default: true,
    container: 'mkv',
    containers: [{ id: 'mkv', label: 'MKV', extension: '.mkv', tool: 'mkvmerge' }],
    external_subtitles: true,
    track_editor: true,
    picks_tracks: true,
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
    if (path === '/api/jobs/auto' && request.method() === 'PATCH') {
      job.spec.overrides = request.postDataJSON().overrides
      saves.push(structuredClone(job.spec.overrides))
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [job],
      '/api/jobs/auto': job,
      '/api/profiles': [profile],
      '/api/presets': { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] },
      '/api/health': { ok: true, version: 'test' },
      '/api/filter-presets': [],
      '/api/config/encoders': [ddp],
      '/api/config/video-options/x265': { dashes: '--', options: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected track auto request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/queue/auto')
  return { saves, errors }
}

test("the editor shows the profile's picks and saves only what differs from them", async ({ page }) => {
  const { saves, errors } = await fixture(page)
  await page.getByRole('tab', { name: 'Subtitles', exact: true }).click()
  const rows = page.getByRole('listitem')
  await expect(rows.nth(0).getByRole('textbox', { name: 'Title' })).toHaveValue('English (SRT)')
  await expect(rows.nth(1).getByRole('checkbox', { name: 'In the output' })).not.toBeChecked()
  await expect(page.getByText('1 of 2 in the output')).toBeVisible()

  await rows.nth(1).getByRole('checkbox', { name: 'In the output' }).click() // keep what the rules left out
  await expect.poll(() => saves.at(-1)?.tracks['id:3']?.exclude).toBe(false)
  expect(saves.at(-1)?.order).toBeNull() // no move: the profile still orders the tracks

  const title = rows.nth(0).getByRole('textbox', { name: 'Title' })
  await title.fill('English')
  await title.press('Enter')
  await expect.poll(() => saves.at(-1)?.tracks['id:2']?.title).toBe('English')
  await title.fill('English (SRT)') // back to the rules' title: no override
  await title.press('Enter')
  await expect.poll(() => saves.at(-1)?.tracks['id:2']).toBeUndefined()

  await page.getByRole('tab', { name: 'Audio', exact: true }).click()
  const action = page.getByRole('combobox', { name: 'Copy or encode' })
  await expect(action).toHaveValue('ddp')
  await action.selectOption('copy')
  await expect.poll(() => saves.at(-1)?.tracks['id:1']?.action).toBe('copy')
  await action.selectOption('ddp')
  await expect.poll(() => saves.at(-1)?.tracks['id:1']).toBeUndefined()
  expect(errors).toEqual([])
})
