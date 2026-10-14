<script lang="ts">
  // The job's VapourSynth processing: preview (source with the crop drawn, or the output),
  // crop (auto-crop, mod 2), source filter, resize, extra filter lines, and the script editor
  // (Run saves an edited body as the job's custom script, then shows its info and frames or the error).
  // Every save hands us a new `job` object, so effects key on derived values (jobId, scriptKey)
  // that only change when the content does; otherwise each save would remount the preview.
  import { untrack } from 'svelte'
  import { api } from '../lib/api'
  import { layout } from '../lib/layout.svelte'
  import { clipLength } from '../lib/format'
  import type { ClipInfo, Crop, JobDetail, ScriptCheck, ScriptParts, SourceFilter, VideoSettings } from '../lib/types'
  import FramePreview from './FramePreview.svelte'
  import Icon from './Icon.svelte'
  import PresetMenu from './PresetMenu.svelte'
  import ScriptEditor from './ScriptEditor.svelte'

  let {
    job,
    save,
    editable,
  }: { job: JobDetail; save: (v: VideoSettings) => Promise<void>; editable: boolean } = $props()

  type View = 'source' | 'output' | 'script'
  let view = $state<View>('source')
  const stage = $derived(view === 'source' ? 'source' : 'output')
  let frame = $state(0)
  let info = $state<Record<string, ClipInfo | null>>({ source: null, output: null })
  let infoError = $state('')
  let version = $state(0)
  let detecting = $state(false)
  // The editable copy; the effect below resets it when the job changes on the server.
  let video = $state<VideoSettings>(untrack(() => structuredClone($state.snapshot(job.spec.video)) as VideoSettings))
  let saving = $state(false)
  // The script editor: the server's parts, the edited body, and the last Run's result.
  let parts = $state<ScriptParts | null>(null)
  let body = $state('')
  let checked = $state<ScriptCheck | null>(null)
  let running = $state(false)
  let refreshSeq = 0
  let refreshedKey = ''
  let adoptNext = false
  const dirty = $derived(!!parts && body !== parts.body.join('\n'))
  const jobId = $derived(job.id)
  const scriptKey = $derived(job.id + JSON.stringify(job.spec.video) + job.spec.encoder.depth)

  // Expanded is for this tab only: leaving it (another tab, job or page) puts the layout back.
  $effect(() => () => (layout.videoExpanded = false))

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
  // resets `info` would depend on it and loop. A failure keeps the last good info, so the
  // preview keeps its frame (under the error) instead of unmounting.
  async function loadInfo(st: 'source' | 'output') {
    const id = jobId
    let value: ClipInfo | null = null
    try {
      value = await api.clipInfo(id, st)
      infoError = ''
    } catch (e) {
      infoError = e instanceof Error ? e.message : String(e)
    }
    if (id === jobId) info = { ...info, [st]: value ?? info[st] }
  }

  $effect(() => {
    void jobId
    info = { source: null, output: null }
    checked = null
    loadInfo('source')
  })

  $effect(() => {
    if (view === 'output') {
      void version
      loadInfo('output')
    }
  })

  // Reload the script and run it. After a Run's save the server's body is taken even over local edits.
  // A failed run keeps the last good output info and frame (no version bump), so the preview stays
  // where it was. Called from an effect: nothing it writes is read before the first await.
  async function refresh() {
    const id = jobId
    const adopt = adoptNext
    adoptNext = false
    refreshedKey = scriptKey
    const seq = ++refreshSeq
    running = true
    try {
      const p = await api.script(id).catch(() => null)
      if (seq !== refreshSeq || !p) return
      const keep = dirty && !adopt
      parts = p
      if (!keep) body = p.body.join('\n')
      const c = await api.checkScript(id).catch(e => ({ ok: false as const, error: String(e.message ?? e), line: null }))
      if (seq !== refreshSeq) return
      checked = c
      if (c.ok) {
        info = { ...info, output: c.info }
        version++
      }
    } finally {
      if (seq === refreshSeq) running = false
    }
  }

  // Script view: run whenever the script's inputs change (once per change, not per job event).
  $effect(() => {
    if (view === 'script') {
      const key = scriptKey
      untrack(() => key !== refreshedKey && refresh())
    }
  })

  async function run() {
    const before = refreshSeq
    if (dirty && editable) {
      clearTimeout(timer)
      video.custom = body
      adoptNext = true
      saving = true
      try {
        await save($state.snapshot(video) as VideoSettings)
      } finally {
        saving = false
      }
    }
    // The save's new job usually starts the run through the effect already. If the save
    // failed, run what the server has but keep the edits.
    if (refreshSeq === before) {
      adoptNext = job.spec.video.custom === video.custom
      await refresh()
    }
  }

  function useGenerated() {
    video.custom = null
    if (parts) body = parts.body.join('\n') // not dirty, so the reload takes the generated body
    commit(0)
  }

  let timer: ReturnType<typeof setTimeout> | undefined
  function commit(delay = 350) {
    clearTimeout(timer)
    timer = setTimeout(async () => {
      saving = true
      try {
        await save($state.snapshot(video) as VideoSettings)
        version++
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
      video.crop = await api.autocrop(jobId, 20)
      commit(0)
    } finally {
      detecting = false
    }
  }

  const current = $derived(info[stage])
  const notice = $derived.by(() => {
    if (view !== 'script') return null
    if (running) return { text: 'Running the script…', tone: 'muted' as const }
    if (checked && !checked.ok)
      return { text: `The script failed${checked.line ? ` (line ${checked.line})` : ''}: this is the last good frame.`, tone: 'bad' as const }
    return null
  })
  const src = $derived(info.source)
  const outW = $derived(src ? src.width - video.crop.left - video.crop.right : 0)
  const outH = $derived(src ? src.height - video.crop.top - video.crop.bottom : 0)
  const SIDES: (keyof Crop)[] = ['left', 'top', 'right', 'bottom']
  const VIEWS: { id: View; label: string }[] = [
    { id: 'source', label: 'Source + crop' },
    { id: 'output', label: 'Output' },
    { id: 'script', label: 'Script' },
  ]
</script>

<svelte:window onkeydown={e => e.key === 'Escape' && !e.defaultPrevented && layout.videoExpanded && (layout.videoExpanded = false)} />

<div class="flex min-h-0 gap-4 {layout.videoExpanded ? 'fixed inset-0 z-40 bg-bg p-4' : 'h-full'}">
  <div class="flex min-w-0 flex-1 flex-col gap-2">
    <div class="flex items-center gap-2">
      <div class="flex rounded-md border border-line p-0.5">
        {#each VIEWS as v (v.id)}
          <button
            class="rounded px-3 py-1 text-sm {view === v.id ? 'bg-raised text-accent' : 'text-muted'}"
            onclick={() => (view = v.id)}>{v.label}</button
          >
        {/each}
      </div>
      {#if saving}<span class="text-xs text-muted">saving…</span>{/if}
      {#if infoError && view !== 'script'}<span class="truncate text-xs text-bad" title={infoError}>{infoError}</span>{/if}
      <button
        class="btn-ghost ml-auto"
        onclick={() => (layout.videoExpanded = !layout.videoExpanded)}
        title={layout.videoExpanded ? 'Back to the page (Esc)' : 'Fill the window with the video editor'}
      >
        <Icon name={layout.videoExpanded ? 'shrink' : 'expand'} />{layout.videoExpanded ? 'Restore' : 'Expand'}
      </button>
    </div>
    {#if current}
      <FramePreview
        {jobId}
        {stage}
        frames={current.frames}
        fps={current.fps}
        width={current.width}
        height={current.height}
        {version}
        crop={stage === 'source' ? video.crop : null}
        bind:frame
        {notice}
      />
    {:else if view === 'script'}
      <div class="flex flex-1 items-center justify-center border border-line text-muted">
        {running ? 'Running the script (the first run indexes the source)…' : 'No frames: the script failed.'}
      </div>
    {:else}
      <div class="flex flex-1 items-center justify-center border border-line text-muted">
        {infoError ? 'No preview' : 'Opening the source (the first time indexes it, which can take minutes on a large remux)…'}
      </div>
    {/if}
  </div>

  {#if view === 'script'}
    <section class="flex w-[45%] shrink-0 flex-col gap-2">
      <div class="flex items-center gap-2">
        <button class="btn-primary" onclick={run} disabled={running || saving} title="Save the body and run the script (Ctrl+Enter)">
          <Icon name="play" />{running ? 'Running…' : dirty && editable ? 'Save & run' : 'Run'}
        </button>
        {#if parts?.custom}
          <button class="btn" onclick={useGenerated} disabled={!editable || running}
            title="Drop the custom body: crop, resize and filters make the script again">Back to generated</button>
        {/if}
        <span class="ml-auto text-xs text-muted">
          {#if !editable}read-only while {job.status}{:else if dirty}edited, not saved{:else if parts?.custom}custom body{:else}generated from crop, resize and filters (editing makes it custom){/if}
        </span>
      </div>
      {#if parts}
        <ScriptEditor
          head={parts.head}
          tail={parts.tail}
          bind:body
          errorLine={checked && !checked.ok ? checked.line : null}
          disabled={!editable}
          onrun={run}
        />
      {:else}
        <div class="flex flex-1 items-center justify-center rounded-md border border-line text-muted">Loading the script…</div>
      {/if}
      {#if checked && !checked.ok}
        <pre class="max-h-40 shrink-0 overflow-auto rounded-md border border-bad/50 bg-bad/10 p-2 text-xs whitespace-pre-wrap text-bad">{checked.line ? `Line ${checked.line}: ` : ''}{checked.error}</pre>
      {:else if checked?.ok}
        {@const i = checked.info}
        <div class="flex shrink-0 flex-wrap gap-x-4 gap-y-1 rounded-md border border-line px-3 py-2 text-xs">
          <span class="text-ok"><Icon name="check" size={13} class="mr-1 inline" />Runs</span>
          <span><span class="text-muted">Frames</span> {i.frames}</span>
          <span><span class="text-muted">Size</span> {i.width}×{i.height}</span>
          <span><span class="text-muted">Format</span> {i.format}</span>
          <span><span class="text-muted">FPS</span> {+i.fps.toFixed(3)} ({i.fps_num}/{i.fps_den})</span>
          <span><span class="text-muted">Length</span> {clipLength(i.frames, i.fps_num, i.fps_den)}</span>
        </div>
      {/if}
    </section>
  {:else}
    <aside class="w-72 shrink-0 space-y-5 overflow-auto pr-1">
      <PresetMenu
        kind="video"
        profile={job.profile}
        current={video}
        disabled={!editable}
        apply={data => {
          video = { ...data, crop: video.crop }
          commit(0)
        }}
      />
      <fieldset disabled={!editable} class="space-y-5">
        <section class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="label">Crop</span>
            <span class="text-xs text-muted">{outW}×{outH}</span>
          </div>
          <!-- Label, box, label, box: the labels get their own columns, so every box is the same width. -->
          <div class="grid grid-cols-[auto_minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-sm">
            {#each SIDES as side (side)}
              <label class="text-muted capitalize" for="crop-{side}">{side}</label>
              <input
                id="crop-{side}"
                class="field w-full"
                type="number"
                step="2"
                min="0"
                value={video.crop[side]}
                onchange={e => setCrop(side, +(e.target as HTMLInputElement).value)}
              />
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
          {#if video.custom !== null}
            <p class="text-xs text-warn">
              A custom script body is in use, so crop, resize and filters don't apply.
              <button class="underline" onclick={() => (view = 'script')}>Edit it</button> ·
              <button class="underline" onclick={useGenerated}>Back to generated</button>
            </p>
          {:else}
            <button class="btn-ghost text-xs" onclick={() => (view = 'script')}>Edit the whole script…</button>
          {/if}
        </section>
      </fieldset>
    </aside>
  {/if}
</div>
