<script lang="ts">
  // The job's VapourSynth processing: preview (source with the crop drawn, or the output),
  // crop (auto-crop, mod 2), source filter, resize, extra filter lines or a custom body.
  import { untrack } from 'svelte'
  import { api } from '../lib/api'
  import type { ClipInfo, Crop, JobDetail, SourceFilter, VideoSettings } from '../lib/types'
  import FramePreview from './FramePreview.svelte'
  import Icon from './Icon.svelte'

  let {
    job,
    save,
    editable,
  }: { job: JobDetail; save: (v: VideoSettings) => Promise<void>; editable: boolean } = $props()

  let stage = $state<'source' | 'output'>('source')
  let frame = $state(0)
  let info = $state<Record<string, ClipInfo | null>>({ source: null, output: null })
  let infoError = $state('')
  let version = $state(0)
  let detecting = $state(false)
  // The editable copy; the effect below resets it when the job changes on the server.
  let video = $state<VideoSettings>(untrack(() => structuredClone($state.snapshot(job.spec.video)) as VideoSettings))
  let script = $state('')
  let showScript = $state(false)
  let saving = $state(false)

  // A new job (or a change made elsewhere) resets the local copy.
  let lastJob = ''
  $effect(() => {
    const key = job.id + JSON.stringify(job.spec.video)
    if (key !== lastJob) {
      lastJob = key
      video = structuredClone($state.snapshot(job.spec.video)) as VideoSettings
    }
  })

  // Called from effects: it must not read `info` before its await, or the effect that
  // resets `info` would depend on it and loop.
  async function loadInfo(st: 'source' | 'output') {
    const id = job.id
    let value: ClipInfo | null = null
    try {
      value = await api.clipInfo(id, st)
      infoError = ''
    } catch (e) {
      infoError = e instanceof Error ? e.message : String(e)
    }
    info = { ...info, [st]: value }
  }

  $effect(() => {
    void job.id
    info = { source: null, output: null }
    loadInfo('source')
  })

  $effect(() => {
    if (stage === 'output') {
      void version
      loadInfo('output')
    }
  })

  let timer: ReturnType<typeof setTimeout> | undefined
  function commit(delay = 350) {
    clearTimeout(timer)
    timer = setTimeout(async () => {
      saving = true
      try {
        await save($state.snapshot(video) as VideoSettings)
        version++
        if (showScript) script = (await api.script(job.id)).script
      } finally {
        saving = false
      }
    }, delay)
  }

  function setCrop(side: keyof Crop, value: number) {
    const v = Math.max(0, Math.round(value / 2) * 2)
    video.crop = { ...video.crop, [side]: v }
    commit()
  }

  async function autoCrop() {
    detecting = true
    try {
      video.crop = await api.autocrop(job.id, 20)
      commit(0)
    } finally {
      detecting = false
    }
  }

  async function toggleScript() {
    showScript = !showScript
    if (showScript) script = (await api.script(job.id)).script
  }

  const current = $derived(info[stage])
  const src = $derived(info.source)
  const outW = $derived(src ? src.width - video.crop.left - video.crop.right : 0)
  const outH = $derived(src ? src.height - video.crop.top - video.crop.bottom : 0)
  const SIDES: (keyof Crop)[] = ['left', 'top', 'right', 'bottom']
</script>

<div class="flex h-full min-h-0 gap-4">
  <div class="flex min-w-0 flex-1 flex-col gap-2">
    <div class="flex items-center gap-2">
      <div class="flex rounded-md border border-line p-0.5">
        {#each ['source', 'output'] as st (st)}
          <button
            class="rounded px-3 py-1 text-sm {stage === st ? 'bg-raised text-accent' : 'text-muted'}"
            onclick={() => (stage = st as 'source' | 'output')}
            >{st === 'source' ? 'Source + crop' : 'Output'}</button
          >
        {/each}
      </div>
      {#if saving}<span class="text-xs text-muted">saving…</span>{/if}
      {#if infoError}<span class="truncate text-xs text-bad" title={infoError}>{infoError}</span>{/if}
    </div>
    {#if current}
      <FramePreview
        jobId={job.id}
        {stage}
        frames={current.frames}
        fps={current.fps}
        width={current.width}
        height={current.height}
        {version}
        crop={stage === 'source' ? video.crop : null}
        bind:frame
      />
    {:else}
      <div class="flex flex-1 items-center justify-center rounded-md border border-line text-muted">
        {infoError ? 'No preview' : 'Opening the source (the first time indexes it, which can take minutes on a large remux)…'}
      </div>
    {/if}
  </div>

  <aside class="w-72 shrink-0 space-y-5 overflow-auto pr-1">
    <fieldset disabled={!editable} class="space-y-5">
      <section class="space-y-2">
        <div class="flex items-center justify-between">
          <span class="label">Crop</span>
          <span class="text-xs text-muted">{outW}×{outH}</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          {#each SIDES as side (side)}
            <label class="flex items-center gap-2 text-sm">
              <span class="w-12 text-muted capitalize">{side}</span>
              <input
                class="field w-full"
                type="number"
                step="2"
                min="0"
                value={video.crop[side]}
                onchange={e => setCrop(side, +(e.target as HTMLInputElement).value)}
              />
            </label>
          {/each}
        </div>
        <div class="flex gap-2">
          <button class="btn flex-1" onclick={autoCrop} disabled={detecting}>
            <Icon name="wand" />{detecting ? 'Detecting…' : 'Auto-crop'}
          </button>
          <button
            class="btn"
            onclick={() => {
              video.crop = { left: 0, top: 0, right: 0, bottom: 0 }
              commit(0)
            }}>Reset</button
          >
        </div>
        {#if outW % 4 || outH % 4}
          <p class="text-xs text-warn">The output isn't mod 4 ({outW}×{outH}).</p>
        {/if}
      </section>

      <section class="space-y-2">
        <span class="label">Source filter</span>
        <select
          class="field w-full"
          value={video.source_filter}
          onchange={e => {
            video.source_filter = (e.target as HTMLSelectElement).value as SourceFilter
            info = { source: null, output: null }
            commit(0)
            setTimeout(() => loadInfo('source'), 400)
          }}
        >
          <option value="bestsource">BestSource (exact seeking)</option>
          <option value="lsmash">L-SMASH Works</option>
          <option value="ffms2">FFMS2</option>
        </select>
      </section>

      <section class="space-y-2">
        <label class="flex items-center gap-2">
          <input
            type="checkbox"
            checked={!!video.resize}
            onchange={e => {
              video.resize = (e.target as HTMLInputElement).checked ? { width: outW, height: outH, kernel: 'Spline36' } : null
              commit()
            }}
          />
          <span class="label">Resize</span>
        </label>
        {#if video.resize}
          <div class="flex items-center gap-2">
            <input class="field w-20" type="number" step="2" bind:value={video.resize.width} onchange={() => commit()} />
            ×
            <input class="field w-20" type="number" step="2" bind:value={video.resize.height} onchange={() => commit()} />
            <select class="field flex-1" bind:value={video.resize.kernel} onchange={() => commit()}>
              {#each ['Spline36', 'Spline64', 'Lanczos', 'Bicubic', 'Bilinear', 'Point'] as k (k)}<option value={k}>{k}</option>{/each}
            </select>
          </div>
        {/if}
      </section>

      <section class="space-y-2">
        <span class="label">Filters (VapourSynth lines on <code>clip</code>)</span>
        <textarea
          class="field h-24 w-full font-mono text-xs"
          placeholder="clip = core.std.Levels(clip, ...)"
          bind:value={video.filters}
          onchange={() => commit(0)}
          disabled={video.custom !== null}
        ></textarea>
        <label class="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={video.custom !== null}
            onchange={e => {
              const c = video.crop
              video.custom = (e.target as HTMLInputElement).checked
                ? `clip = src\nclip = core.std.Crop(clip, left=${c.left}, right=${c.right}, top=${c.top}, bottom=${c.bottom})\n${video.filters}`.trim()
                : null
              commit(0)
            }}
          />
          Custom script body (replaces crop, resize and filters)
        </label>
        {#if video.custom !== null}
          <textarea class="field h-40 w-full font-mono text-xs" bind:value={video.custom} onchange={() => commit(0)}></textarea>
        {/if}
      </section>
    </fieldset>

    <section class="space-y-2">
      <button class="btn-ghost text-xs" onclick={toggleScript}>{showScript ? 'Hide' : 'Show'} the generated script</button>
      {#if showScript}
        <pre class="overflow-auto rounded-md border border-line bg-black/40 p-2 text-[11px] leading-snug">{script}</pre>
      {/if}
    </section>
  </aside>
</div>
