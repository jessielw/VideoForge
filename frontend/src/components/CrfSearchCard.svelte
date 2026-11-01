<script lang="ts">
  // The Encoder tab's CRF search (core/pipeline/crfsearch.py): the test encode (SampleCard) at several CRFs, each
  // scored against the encoder's input, for the highest CRF whose score still reaches a target. It runs in the
  // index lane like the test encode; each try shows as it ends, and Use puts the CRF found on the job. The metric,
  // its targets and the percent are kept in the browser.
  import { toast } from 'svelte-sonner'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { saves } from '../lib/saves'
  import { duration } from '../lib/format'
  import { SAMPLE_PERCENTS, type JobDetail, type SearchMetric } from '../lib/types'
  import CheckIcon from '@lucide/svelte/icons/check'
  import CrosshairIcon from '@lucide/svelte/icons/crosshair'
  import SquareIcon from '@lucide/svelte/icons/square'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import Tip from './Tip.svelte'

  let { job, editable, onapply }: { job: JobDetail; editable: boolean; onapply: (crf: number) => void } = $props()

  const METRICS: { value: SearchMetric; label: string; unit: string; fallback: number }[] = [
    { value: 'ssimulacra2', label: 'SSIMULACRA2', unit: '', fallback: 80 },
    { value: 'ssimulacra2_p5', label: 'SSIMULACRA2, worst 5%', unit: '', fallback: 70 },
    { value: 'xpsnr', label: 'XPSNR', unit: ' dB', fallback: 42 },
  ]
  const KEY = 'videoforge.crfSearch' // { metric, percent, targets: { [metric]: number } }
  const MAX_TRIES = 8 // crfsearch.MAX_TRIES

  type Saved = { metric: SearchMetric; percent: number; targets: Partial<Record<SearchMetric, number>> }
  const saved = readSaved()
  let metric = $state<SearchMetric>(saved.metric)
  let percent = $state(saved.percent)
  let targets = $state(saved.targets)
  let starting = $state(false)

  const info = $derived(METRICS.find((m) => m.value === metric) ?? METRICS[0])
  const target = $derived(targets[metric] ?? info.fallback)
  const live = $derived(app.jobs.find((j) => j.id === job.id)) // live status and progress
  const status = $derived(live?.status ?? job.status)
  const mine = $derived(!!live?.searching) // the lane's test encode for the job is this search
  const searching = $derived(status === 'sampling' && mine)
  const waiting = $derived(!!live?.sample_waiting && mine)
  const error = $derived(live?.search_error ?? job.search_error)
  const r = $derived(job.search)
  const crfMode = $derived(job.spec.encoder.rate_control === 'crf')
  const rInfo = $derived(r ? (METRICS.find((m) => m.value === r.metric) ?? METRICS[0]) : null)
  const tries = $derived(r ? [...r.tries].sort((a, b) => a.crf - b.crf) : [])

  function readSaved(): Saved {
    const fallback: Saved = { metric: 'ssimulacra2', percent: 2, targets: {} }
    try {
      const v = JSON.parse(localStorage.getItem(KEY) ?? 'null')
      if (!v || typeof v !== 'object') return fallback
      return {
        metric: METRICS.some((m) => m.value === v.metric) ? v.metric : fallback.metric,
        percent: (SAMPLE_PERCENTS as readonly number[]).includes(v.percent) ? v.percent : fallback.percent,
        targets: v.targets && typeof v.targets === 'object' ? v.targets : {},
      }
    } catch {
      return fallback // storage blocked, or not ours
    }
  }

  function keep() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ metric, percent, targets }))
    } catch {
      /* storage blocked */
    }
  }

  function setTarget(v: number) {
    if (!Number.isFinite(v)) return
    targets = { ...targets, [metric]: v }
    keep()
  }

  async function run() {
    starting = true
    try {
      await saves.flush()
      const res = await api.search(job.id, percent, metric, target)
      if (!res.taken)
        toast.info('No CRF search', { description: 'The job is queued, running or being indexed, or not probed yet.' })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      starting = false
    }
  }

  function score(v: number | null, unit = ''): string {
    return v == null ? '—' : `${v.toFixed(1)}${unit}`
  }

  function size(mb: number | null): string {
    if (mb == null) return '—'
    return mb >= 1000 ? `${(mb / 1000).toFixed(2)} GB` : `${mb.toFixed(0)} MB`
  }

  function passes(t: { ssimulacra2: number; ssimulacra2_p5: number; xpsnr: number | null }): boolean {
    if (!r) return false
    const v = t[r.metric]
    return v != null && v >= r.target
  }
</script>

<section class="space-y-3 rounded-lg border bg-card p-3" aria-label="CRF search">
  <div class="flex flex-wrap items-center gap-2">
    <span class="section-label">CRF search</span>
    {#if r && !r.current && !searching}<Badge variant="outline" class="border-warning/40 bg-warning/10 text-warning"
        >settings changed since</Badge
      >{/if}
  </div>
  <p class="text-xs text-muted-foreground">
    Encodes the test encode's sample at several CRFs and scores each against the encoder's input, for the highest CRF
    that still reaches the target: up to {MAX_TRIES} tries, starting at the job's CRF. CRFs it tried before are reused.
  </p>

  {#if !crfMode}
    <p class="text-xs text-muted-foreground">Set the rate control to CRF to search for one.</p>
  {:else if searching || waiting}
    {@const p = live?.progress}
    <div class="flex items-center gap-3 text-xs text-info">
      <div class="h-1.5 flex-1 overflow-hidden rounded bg-muted">
        <div class="h-full bg-info transition-[width]" style="width:{(p?.overall ?? 0) * 100}%"></div>
      </div>
      <span class="tabular-nums"
        >{#if !searching}{status === 'indexing'
            ? 'Indexing first'
            : 'Waiting in the index lane'}{:else if p}{p.step}{p.fps != null
            ? ` · ${p.fps.toFixed(1)} fps`
            : ''}{p.left != null ? ` · at most ${duration(p.left)} left` : ''}{:else}Starting…{/if}</span
      >
      <Button variant="outline" size="sm" onclick={() => app.stopSample(job.id)}><SquareIcon />Stop</Button>
    </div>
  {:else}
    <div class="flex flex-wrap items-center gap-2">
      <NativeSelect
        aria-label="Score to reach"
        value={metric}
        onchange={(e) => {
          metric = e.currentTarget.value as SearchMetric
          keep()
        }}
      >
        {#each METRICS as m (m.value)}<option value={m.value}>{m.label}</option>{/each}
      </NativeSelect>
      <span class="text-sm text-muted-foreground">≥</span>
      <Input
        class="w-20"
        type="number"
        aria-label="Target score"
        step="0.5"
        value={target}
        onchange={(e) => setTarget(+e.currentTarget.value)}
      />
      <NativeSelect
        aria-label="How much of the video"
        value={percent}
        onchange={(e) => {
          percent = +e.currentTarget.value
          keep()
        }}
      >
        {#each SAMPLE_PERCENTS as v (v)}<option value={v}>{v}%</option>{/each}
      </NativeSelect>
      <Tip text={editable ? 'Search with the job as it is now' : `Not while ${status}`}>
        <Button onclick={run} disabled={!editable || starting || !job.plan}>
          <CrosshairIcon />{r ? 'Search again' : 'Search'}
        </Button>
      </Tip>
    </div>
    <p class="text-xs text-muted-foreground">
      SSIMULACRA2: 90 visually lossless, 80 very high, 70 high quality. XPSNR: higher is closer to the input.
    </p>
  {/if}
  {#if error && !searching}<p class="text-xs text-destructive">The last CRF search failed: {error}</p>{/if}

  {#if r && rInfo}
    {@const goal = `${rInfo.label} ${r.target}${rInfo.unit}`}
    {#if r.done}
      <div class="flex flex-wrap items-center gap-2 text-sm">
        {#if r.crf != null}
          <span>
            <strong class="tabular-nums">CRF {r.crf}</strong> is the highest that reaches {goal}{r.exact
              ? ''
              : r.tries.length >= MAX_TRIES
                ? ` (after ${MAX_TRIES} tries; one between it and the next failure may reach it too)`
                : " (the encoder's highest CRF)"}.
          </span>
          {#if job.spec.encoder.crf === r.crf}
            <Badge variant="outline">the job's CRF</Badge>
          {:else}
            <Tip text={editable ? `Set the job's CRF to ${r.crf}` : `Not while ${status}`}>
              <Button size="sm" variant="outline" disabled={!editable} onclick={() => r.crf != null && onapply(r.crf)}>
                <CheckIcon />Use CRF {r.crf}
              </Button>
            </Tip>
          {/if}
        {:else}
          <span>No CRF tried reaches {goal}, not even CRF {tries[0]?.crf}.</span>
        {/if}
      </div>
    {:else if !searching && !waiting}
      <p class="text-xs text-muted-foreground">Stopped after {r.tries.length} tries, for {goal}.</p>
    {/if}
    {#if tries.length}
      <div class="overflow-x-auto">
        <table class="w-full text-sm tabular-nums">
          <thead class="text-xs text-muted-foreground">
            <tr class="text-left">
              <th class="py-1 pr-3 font-normal">CRF</th>
              <th class="py-1 pr-3 font-normal">Bitrate</th>
              <th class="py-1 pr-3 font-normal">
                <Tip text="The video stream at the sample's bitrate, without container overhead">Whole video</Tip>
              </th>
              <th class="py-1 pr-3 font-normal">SSIMULACRA2</th>
              <th class="py-1 pr-3 font-normal">worst 5%</th>
              <th class="py-1 font-normal">XPSNR</th>
            </tr>
          </thead>
          <tbody>
            {#each tries as t (t.crf)}
              <tr class={t.crf === r.crf ? 'font-medium text-primary' : passes(t) ? '' : 'text-muted-foreground'}>
                <td class="py-0.5 pr-3">
                  <Tip text={passes(t) ? `Reaches ${goal}` : `Below ${goal}`}>
                    {t.crf}{passes(t) ? ' ✓' : ''}
                  </Tip>
                </td>
                <td class="py-0.5 pr-3">{t.kbps != null ? `${Math.round(t.kbps).toLocaleString()} kb/s` : '—'}</td>
                <td class="py-0.5 pr-3">{size(t.estimate_mb)}</td>
                <td class="py-0.5 pr-3">{score(t.ssimulacra2)}</td>
                <td class="py-0.5 pr-3">{score(t.ssimulacra2_p5)}</td>
                <td class="py-0.5">{score(t.xpsnr, ' dB')}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="text-xs text-muted-foreground">
        {r.frames.toLocaleString()} of {r.total_frames.toLocaleString()} frames ({r.percent}%), {r.encoder}, from CRF {r.start}
        · {new Date(r.started).toLocaleString()}
      </p>
    {/if}
  {/if}
</section>
