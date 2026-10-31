import { test, expect, type Page } from '@playwright/test'
import type { AudioTrack, JobDetail, Overrides, Profile } from '../../src/lib/types.ts'

async function fixture(page: Page, delay: number, correction = 0, title = '', trackEditor = true) {
  const errors: string[] = []
  const saves: Overrides[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const track: AudioTrack = {
    key: 'id:1',
    id: 1,
    index: 0,
    codec: 'eac3',
    layout: '2.0',
    language: 'en',
    title,
    default: true,
    forced: false,
    hearing_impaired: false,
    visual_impaired: false,
    commentary: false,
    original: false,
    atmos: false,
    dtsx: false,
    bitrate_kbps: 224,
    delay_ms: delay,
    format_name: 'E-AC-3',
    detected: {},
    sample_rate: 48000,
    bit_depth: null,
    size_bytes: null,
    duration_ms: 61000,
    copy: 0,
  }
  const job: JobDetail = {
    id: 'delay',
    name: 'Audio delay',
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
    sample_waiting: false,
    sample_error: '',
    audio: [],
    subs: 0,
    issues: [],
    steps: {},
    plan: {
      encode_path: null,
      resolution: '1080p',
      original_language: 'en',
      chapters_path: null,
      audio: [
        {
          source: track,
          action: 'copy',
          out_codec: 'eac3',
          out_layout: '2.0',
          out_atmos: false,
          bitrate_kbps: 224,
          upmix_50: false,
          language: 'en',
          title: '',
          default: true,
          forced: false,
          hearing_impaired: false,
          visual_impaired: false,
          commentary: false,
          original: false,
          options: {},
          sync_ms: correction,
        },
      ],
      subs: [],
      burn: null,
      issues: [],
      profile: 'manual',
    },
    output_name: null,
    color_args: null,
    target: null,
    sample: null,
    compare: { encode: false, sample: false },
    tracks: { video: null, audio: [track], subs: [], has_chapters: false, count: 1 },
    spec: {
      id: 'delay',
      profile: 'manual',
      inputs: { source: 'D:/Show.mkv', encode: null, subtitles: [], chapters: null, encode_state: '', audio: [] },
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
        hdr10plus: false,
        dolby_vision: false,
      },
      mux: { container: 'mkv', extra: '', pgs_zlib: false },
      overrides: {
        original_language: null,
        audio_track_ids: null,
        tracks: correction
          ? {
              'id:1': {
                exclude: null,
                language: null,
                title: null,
                flags: {},
                action: null,
                bitrate_kbps: null,
                layout: null,
                options: {},
                sync_ms: correction,
              },
            }
          : {},
        order: null,
        copies: [],
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
    track_editor: trackEditor,
    track_properties: [],
    defaults: {
      video: job.spec.video,
      encoder: job.spec.encoder,
      template: {
        video: job.spec.video,
        encoder: job.spec.encoder,
        mux: job.spec.mux,
        qpf: false,
        crop_mode: 'keep',
        audio: null,
        subs: null,
      },
    },
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/jobs/delay' && request.method() === 'PATCH') {
      job.spec.overrides = request.postDataJSON().overrides
      saves.push(structuredClone(job.spec.overrides))
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [job],
      '/api/jobs/delay': job,
      '/api/profiles': [profile],
      '/api/presets': { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] },
      '/api/health': { ok: true, version: 'test' },
      '/api/filter-presets': [],
      '/api/config/encoders': [],
      '/api/config/video-options/x265': { dashes: '--', options: [] },
    }
    if (!(path in responses)) throw new Error(`Unexpected audio delay fixture request: ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/queue/delay')
  await page.getByRole('tab', { name: 'Audio', exact: true }).click()
  return { delayInput: page.getByRole('spinbutton', { name: 'Delay (ms)', exact: true }), saves, errors }
}

for (const delay of [24, -24, 0]) {
  test(`Delay shows detected ${delay} ms and edits the total without applying delay twice`, async ({ page }) => {
    const { delayInput, saves, errors } = await fixture(page, delay)
    await expect(delayInput).toHaveValue(String(delay))
    expect(saves).toHaveLength(0)

    await delayInput.fill('50')
    await delayInput.blur()
    await expect.poll(() => saves.length).toBe(1)
    await expect.poll(() => saves.at(-1)?.tracks['id:1']?.sync_ms).toBe(50 - delay)
    await expect(delayInput).toHaveValue('50')

    await delayInput.fill('0')
    await delayInput.blur()
    await expect.poll(() => saves.length).toBe(2)
    await expect.poll(() => saves.at(-1)?.tracks['id:1']?.sync_ms ?? 0).toBe(0 - delay)
    await expect(delayInput).toHaveValue('0')
    await page.reload()
    await page.getByRole('tab', { name: 'Audio', exact: true }).click()
    await expect(delayInput).toHaveValue('0')

    await delayInput.fill('')
    await delayInput.blur()
    await expect.poll(() => saves.length).toBe(3)
    await expect.poll(() => saves.at(-1)?.tracks['id:1']?.sync_ms ?? null).toBeNull()
    await expect(delayInput).toHaveValue(String(delay))
    expect(errors).toEqual([])
  })
}

test('existing saved corrections retain their timing and can return to the detected delay', async ({ page }) => {
  const { delayInput, saves, errors } = await fixture(page, 24, 10)
  await expect(delayInput).toHaveValue('34')
  await delayInput.fill('24')
  await delayInput.blur()
  await expect.poll(() => saves.length).toBe(1)
  await expect.poll(() => saves.at(-1)?.tracks['id:1']?.sync_ms ?? null).toBeNull()
  await expect(delayInput).toHaveValue('24')
  expect(errors).toEqual([])
})

for (const trackEditor of [true, false]) {
  test(`a long track title wraps instead of widening the ${trackEditor ? 'track editor' : 'tracks tab'}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 720 })
    const title = `${'Commentary with the director and cast '.repeat(8)}${'x'.repeat(200)}`
    const { errors } = await fixture(page, 0, 0, title, trackEditor)
    const text = page.getByText(title).first()
    await expect(text).toBeVisible()
    const bounds = await text.boundingBox()
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(1024)
    expect(errors).toEqual([])
  })
}
