<script lang="ts">
  // The Encoder tab's test encode (StaxRip's compressibility check, core/pipeline/sample.py): the job's script
  // and encoder settings on 2 s blocks spread over the video (one in every 100 / percent), first in the index
  // lane (it indexes the source if it has to). Its bitrate gives the whole encode's size, its pace the time;
  // Compare opens its frames against the encoder's input on the Video tab. The percent is kept in the browser.
  import { toast } from 'svelte-sonner'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { saves } from '../lib/saves'
  import { duration } from '../lib/format'
  import { SAMPLE_PERCENTS, type JobDetail } from '../lib/types'
  import FlaskConicalIcon from '@lucide/svelte/icons/flask-conical'
  import SplitIcon from '@lucide/svelte/icons/split'
  import SquareIcon from '@lucide/svelte/icons/square'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import Tip from './Tip.svelte'

  let { job, editable, oncompare }: { job: JobDetail; editable: boolean; oncompare: () => void } = $props()

  const KEY = 'videoforge.samplePercent'
  let percent = $state(readPercent())
  let starting = $state(false)
  const live = $derived(app.jobs.find((j) => j.id === job.id)) // live status and progress
  const status = $derived(live?.status ?? job.status)
  const sampling = $derived(status === 'sampling')
  const waiting = $derived(!!live?.sample_waiting)
  const error = $derived(live?.sample_error ?? job.sample_error)
  const s = $derived(job.sample)
  const twoPass = $derived(job.spec.encoder.rate_control === '2pass')
  // One block in every `cycle`: 2 s of every 40 s at 5%.
  const every = $derived(Math.round(200 / percent))

  function readPercent(): number {
    try {
      const v = Number(localStorage.getItem(KEY))
      return (SAMPLE_PERCENTS as readonly number[]).includes(v) ? v : 5
    } catch {
      return 5 // storage blocked
    }
  }

  function setPercent(v: number) {
    percent = v
    try {
      localStorage.setItem(KEY, String(v))
    } catch {
      /* storage blocked */
    }
  }

  async function run() {
    starting = true
    try {
      await saves.flush()
      const r = await api.sample(job.id, percent)
      if (!r.taken)
        toast.info('No test encode', { description: 'The job is queued, running or being indexed, or not probed yet.' })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      starting = false
    }
  }

  function gb(mb: number): string {
    return mb >= 1000 ? `${(mb / 1000).toFixed(2)} GB` : `${mb.toFixed(0)} MB`
  }
</script>

<section class="space-y-3 rounded-lg border bg-card p-3" aria-label="Test encode">
  <div class="flex flex-wrap items-center gap-2">
    <span class="section-label">Test encode</span>
    {#if s && !s.current && !sampling}<Badge variant="outline" class="border-warning/40 bg-warning/10 text-warning"
        >settings changed since</Badge
      >{/if}
  </div>
  <p class="text-xs text-muted-foreground">
    Encodes {percent}% of the video (2 s of every {every} s) with this script and these settings: the bitrate it gives, the
    whole encode's size and time, and frames to compare with the encoder's input.{twoPass
      ? ' A 2-pass encode is tested as one pass at its bitrate.'
      : ''}
    It runs in the index lane, beside the queue{job.indexed ? '' : ', and indexes the source first'}.
  </p>

  {#if sampling || waiting}
    {@const p = live?.progress}
    <div class="flex items-center gap-3 text-xs text-info">
      <div class="h-1.5 flex-1 overflow-hidden rounded bg-muted">
        <div class="h-full bg-info transition-[width]" style="width:{(p?.overall ?? 0) * 100}%"></div>
      </div>
      <span class="tabular-nums"
        >{#if !sampling}{status === 'indexing' ? 'Indexing first' : 'Waiting in the index lane'}{:else if p}{(
            p.overall * 100
          ).toFixed(0)}%{p.eta != null ? ` · ${duration(p.eta)} left` : ''}{p.fps != null
            ? ` · ${p.fps.toFixed(1)} fps`
            : ''}{:else}Starting…{/if}</span
      >
      <Button variant="outline" size="sm" onclick={() => app.stopSample(job.id)}><SquareIcon />Stop</Button>
    </div>
  {:else}
    <div class="flex items-center gap-2">
      <NativeSelect
        aria-label="How much of the video"
        value={percent}
        onchange={(e) => setPercent(+e.currentTarget.value)}
      >
        {#each SAMPLE_PERCENTS as v (v)}<option value={v}>{v}%</option>{/each}
      </NativeSelect>
      <Tip text={editable ? 'Encode the sample with the job as it is now' : `Not while ${status}`}>
        <Button onclick={run} disabled={!editable || starting || !job.plan}>
          <FlaskConicalIcon />{s ? 'Run again' : 'Run test encode'}
        </Button>
      </Tip>
      {#if s}
        <Tip text="The sample's frames against the encoder's input (Video tab)">
          <Button variant="outline" onclick={oncompare}><SplitIcon />Compare</Button>
        </Tip>
      {/if}
    </div>
  {/if}
  {#if error && !sampling}<p class="text-xs text-destructive">The last test encode failed: {error}</p>{/if}

  {#if s}
    <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
      <dt class="text-muted-foreground">Bitrate</dt>
      <dd class="tabular-nums">{s.kbps != null ? `${Math.round(s.kbps).toLocaleString()} kb/s` : '—'}</dd>
      <dt class="text-muted-foreground">Whole video</dt>
      <dd class="tabular-nums">
        <Tip text="The video stream at the sample's bitrate, without container overhead">
          {s.estimate_mb != null ? `≈ ${gb(s.estimate_mb)}` : '—'}
        </Tip>
      </dd>
      <dt class="text-muted-foreground">Encode time</dt>
      <dd class="tabular-nums">
        <Tip text="At the sample's pace, one pass">
          {s.estimate_seconds != null ? `≈ ${duration(s.estimate_seconds)}` : '—'}{s.encode_fps != null
            ? ` (${s.encode_fps.toFixed(1)} fps)`
            : ''}
        </Tip>
      </dd>
      {#if s.ssimulacra2 != null}
        <dt class="text-muted-foreground">Quality</dt>
        <dd class="flex flex-wrap gap-x-3 tabular-nums">
          <Tip text="SSIMULACRA2 against the encoder's input, the frames' mean">
            SSIMULACRA2 {s.ssimulacra2.toFixed(1)}
          </Tip>
          {#if s.ssimulacra2_p5 != null}
            <Tip class="text-muted-foreground" text="5% of the frames score below it">
              worst 5% {s.ssimulacra2_p5.toFixed(1)}
            </Tip>
          {/if}
          {#if s.xpsnr != null}
            <Tip text="XPSNR of the luma: higher is closer to the encoder's input">XPSNR {s.xpsnr.toFixed(1)} dB</Tip>
          {/if}
          <span class="basis-full text-xs text-muted-foreground">
            SSIMULACRA2: 100 identical, 90 visually lossless, 80 very high, 70 high quality
          </span>
        </dd>
      {/if}
      <dt class="text-muted-foreground">Sample</dt>
      <dd class="tabular-nums">
        {s.frames.toLocaleString()} of {s.total_frames.toLocaleString()} frames ({s.percent}%), {s.encoder}
      </dd>
    </dl>
    <Tip class="block truncate text-xs text-muted-foreground" text={s.file}>
      {new Date(s.finished).toLocaleString()} · {s.file}
    </Tip>
  {/if}
</section>
