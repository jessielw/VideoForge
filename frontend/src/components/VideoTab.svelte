<script lang="ts">
  // The job's VapourSynth processing: preview (source with the crop drawn, or the output),
  // crop (auto-crop, mod 2), source filter, resize, extra filter lines, and the script editor
  // (Run saves an edited body as the job's custom script, then shows its info and frames or the error).
  // Every save hands us a new `job` object, so effects key on derived values (jobId, scriptKey)
  // that only change when the content does; otherwise each save would remount the preview.
  import { untrack } from 'svelte'
  import { api } from '../lib/api'
  import { layout } from '../lib/layout.svelte'
  import { videoView } from '../lib/videoView.svelte'
  import { clipLength } from '../lib/format'
  import type { ClipInfo, Crop, JobDetail, SourceFilter, VideoSettings } from '../lib/types'
  import FramePreview from './FramePreview.svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
  import MaximizeIcon from '@lucide/svelte/icons/maximize'
  import MinimizeIcon from '@lucide/svelte/icons/minimize'
  import PlayIcon from '@lucide/svelte/icons/play'
  import WandSparklesIcon from '@lucide/svelte/icons/wand-sparkles'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as Tabs from '$lib/components/ui/tabs'
  import { Textarea } from '$lib/components/ui/textarea'
  import PresetMenu from './PresetMenu.svelte'
  import ScriptEditor from './ScriptEditor.svelte'

  let {
    job,
    save,
    editable,
  }: { job: JobDetail; save: (v: VideoSettings) => Promise<void>; editable: boolean } = $props()

  type View = 'source' | 'output' | 'script'
  // View, frame, zoom, scroll and the script editor's text, kept per job (JobEditor remounts this per job).
  const vv = videoView(untrack(() => job.id))
  const stage = $derived(vv.view === 'source' ? 'source' : 'output')
  let info = $state<Record<string, ClipInfo | null>>({ source: null, output: null })
  let infoError = $state('')
  let version = $state(0)
  let detecting = $state(false)
  // The editable copy; the effect below resets it when the job changes on the server.
  let video = $state<VideoSettings>(untrack(() => structuredClone($state.snapshot(job.spec.video)) as VideoSettings))
  let saving = $state(false)
  // The script editor (in vv): the server's parts, the edited body, and the last Run's result.
  let running = $state(false)
  let refreshSeq = 0
  let refreshedKey = ''
  let adoptNext = false
  const dirty = $derived(!!vv.parts && vv.body !== vv.parts.body.join('\n'))
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
    // A script view left with a good run shows its output again at once (the rerun refreshes it).
    const ran = untrack(() => vv.checked)
    info = { source: null, output: ran?.ok ? ran.info : null }
    loadInfo('source')
  })

  $effect(() => {
    if (vv.view === 'output') {
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
      vv.parts = p
      if (!keep) vv.body = p.body.join('\n')
      const c = await api.checkScript(id).catch(e => ({ ok: false as const, error: String(e.message ?? e), line: null }))
      if (seq !== refreshSeq) return
      vv.checked = c
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
    if (vv.view === 'script') {
      const key = scriptKey
      untrack(() => key !== refreshedKey && refresh())
    }
  })

  async function run() {
    const before = refreshSeq
    if (dirty && editable) {
      clearTimeout(timer)
      video.custom = vv.body
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
    if (vv.parts) vv.body = vv.parts.body.join('\n') // not dirty, so the reload takes the generated body
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
    if (vv.view !== 'script') return null
    if (running) return { text: 'Running the script…', tone: 'muted' as const }
    if (vv.checked && !vv.checked.ok)
      return { text: `The script failed${vv.checked.line ? ` (line ${vv.checked.line})` : ''}: this is the last good frame.`, tone: 'bad' as const }
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

<div class="flex min-h-0 gap-4 {layout.videoExpanded ? 'fixed inset-0 z-40 bg-background p-4' : 'h-full'}">
  <div class="flex min-w-0 flex-1 flex-col gap-2">
    <div class="flex items-center gap-2">
      <Tabs.Root value={vv.view} onValueChange={v => (vv.view = v as View)}>
        <Tabs.List>
          {#each VIEWS as v (v.id)}<Tabs.Trigger value={v.id} class="px-3">{v.label}</Tabs.Trigger>{/each}
        </Tabs.List>
      </Tabs.Root>
      {#if saving}<span class="text-xs text-muted-foreground">saving…</span>{/if}
      {#if infoError && vv.view !== 'script'}<span class="truncate text-xs text-destructive" title={infoError}>{infoError}</span>{/if}
      <Button
        variant="ghost"
        class="ml-auto"
        onclick={() => (layout.videoExpanded = !layout.videoExpanded)}
        title={layout.videoExpanded ? 'Back to the page (Esc)' : 'Fill the window with the video editor'}
      >
        {#if layout.videoExpanded}<MinimizeIcon />Restore{:else}<MaximizeIcon />Expand{/if}
      </Button>
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
        bind:frame={vv.frame}
        bind:zoom={vv.zoom}
        bind:edges={vv.edges}
        bind:scroll={vv.scroll}
        {notice}
      />
    {:else if vv.view === 'script'}
      <div class="flex flex-1 items-center justify-center border text-muted-foreground">
        {running ? 'Running the script (the first run indexes the source)…' : 'No frames: the script failed.'}
      </div>
    {:else}
      <div class="flex flex-1 items-center justify-center border text-muted-foreground">
        {infoError ? 'No preview' : 'Opening the source (the first time indexes it, which can take minutes on a large remux)…'}
      </div>
    {/if}
  </div>

  {#if vv.view === 'script'}
    <section class="flex w-[45%] shrink-0 flex-col gap-2">
      <div class="flex items-center gap-2">
        <Button onclick={run} disabled={running || saving} title="Save the body and run the script (Ctrl+Enter)">
          <PlayIcon />{running ? 'Running…' : dirty && editable ? 'Save & run' : 'Run'}
        </Button>
        {#if vv.parts?.custom}
          <Button variant="outline" onclick={useGenerated} disabled={!editable || running}
            title="Drop the custom body: crop, resize and filters make the script again">Back to generated</Button>
        {/if}
        <span class="ml-auto text-xs text-muted-foreground">
          {#if !editable}read-only while {job.status}{:else if dirty}edited, not saved{:else if vv.parts?.custom}custom body{:else}generated from crop, resize and filters (editing makes it custom){/if}
        </span>
      </div>
      {#if vv.parts}
        <ScriptEditor
          head={vv.parts.head}
          tail={vv.parts.tail}
          bind:body={vv.body}
          errorLine={vv.checked && !vv.checked.ok ? vv.checked.line : null}
          disabled={!editable}
          onrun={run}
        />
      {:else}
        <div class="flex flex-1 items-center justify-center rounded-lg border text-muted-foreground">Loading the script…</div>
      {/if}
      {#if vv.checked && !vv.checked.ok}
        <pre class="max-h-40 shrink-0 overflow-auto rounded-lg border border-destructive/50 bg-destructive/10 p-2 text-xs whitespace-pre-wrap text-destructive">{vv.checked.line ? `Line ${vv.checked.line}: ` : ''}{vv.checked.error}</pre>
      {:else if vv.checked?.ok}
        {@const i = vv.checked.info}
        <div class="flex shrink-0 flex-wrap gap-x-4 gap-y-1 rounded-lg border bg-card px-3 py-2 text-xs">
          <span class="text-success"><CheckIcon class="mr-1 inline size-3.5 align-[-2px]" />Runs</span>
          <span><span class="text-muted-foreground">Frames</span> {i.frames}</span>
          <span><span class="text-muted-foreground">Size</span> {i.width}×{i.height}</span>
          <span><span class="text-muted-foreground">Format</span> {i.format}</span>
          <span><span class="text-muted-foreground">FPS</span> {+i.fps.toFixed(3)} ({i.fps_num}/{i.fps_den})</span>
          <span><span class="text-muted-foreground">Length</span> {clipLength(i.frames, i.fps_num, i.fps_den)}</span>
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
            <span class="section-label">Crop</span>
            <span class="text-xs text-muted-foreground">{outW}×{outH}</span>
          </div>
          <!-- Label, box, label, box: the labels get their own columns, so every box is the same width. -->
          <div class="grid grid-cols-[auto_minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-sm">
            {#each SIDES as side (side)}
              <label class="text-muted-foreground capitalize" for="crop-{side}">{side}</label>
              <Input
                id="crop-{side}"
                class="w-full"
                type="number"
                step="2"
                min="0"
                value={video.crop[side]}
                onchange={e => setCrop(side, +(e.target as HTMLInputElement).value)}
              />
            {/each}
          </div>
          <div class="flex gap-2">
            <Button variant="outline" class="flex-1" onclick={autoCrop} disabled={detecting}>
              <WandSparklesIcon />{detecting ? 'Detecting…' : 'Auto-crop'}
            </Button>
            <Button
              variant="outline"
              onclick={() => {
                video.crop = { left: 0, top: 0, right: 0, bottom: 0 }
                commit(0)
              }}>Reset</Button
            >
          </div>
          {#if outW % 4 || outH % 4}
            <p class="text-xs text-warning">The output isn't mod 4 ({outW}×{outH}).</p>
          {/if}
        </section>

        <section class="space-y-2">
          <span class="section-label">Source filter</span>
          <NativeSelect
            class="w-full"
            aria-label="Source filter"
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
          </NativeSelect>
        </section>

        <section class="space-y-2">
          <label class="flex items-center gap-2">
            <Checkbox
              checked={!!video.resize}
              onCheckedChange={on => {
                video.resize = on ? { width: outW, height: outH, kernel: 'Spline36' } : null
                commit()
              }}
            />
            <span class="section-label">Resize</span>
          </label>
          {#if video.resize}
            <div class="flex items-center gap-2">
              <Input class="w-20" type="number" step="2" aria-label="Width" bind:value={video.resize.width} onchange={() => commit()} />
              ×
              <Input class="w-20" type="number" step="2" aria-label="Height" bind:value={video.resize.height} onchange={() => commit()} />
              <NativeSelect class="min-w-0 flex-1" aria-label="Kernel" bind:value={video.resize.kernel} onchange={() => commit()}>
                {#each ['Spline36', 'Spline64', 'Lanczos', 'Bicubic', 'Bilinear', 'Point'] as k (k)}<option value={k}>{k}</option>{/each}
              </NativeSelect>
            </div>
          {/if}
        </section>

        <section class="space-y-2">
          <span class="section-label">Filters (VapourSynth lines on <code>clip</code>)</span>
          <Textarea
            class="h-24 w-full font-mono text-xs"
            placeholder="clip = core.std.Levels(clip, ...)"
            bind:value={video.filters}
            onchange={() => commit(0)}
            disabled={video.custom !== null}
          />
          {#if video.custom !== null}
            <p class="text-xs text-warning">
              A custom script body is in use, so crop, resize and filters don't apply.
              <button class="underline underline-offset-2" onclick={() => (vv.view = 'script')}>Edit it</button> ·
              <button class="underline underline-offset-2" onclick={useGenerated}>Back to generated</button>
            </p>
          {:else}
            <Button variant="ghost" size="sm" onclick={() => (vv.view = 'script')}>Edit the whole script…</Button>
          {/if}
        </section>
      </fieldset>
    </aside>
  {/if}
</div>
