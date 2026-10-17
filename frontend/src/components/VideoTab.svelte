<script lang="ts">
  // The job's VapourSynth processing: one preview, of the script's output (as in VapourSynth Editor),
  // and a side panel: Settings (crop, auto-crop, source filter, resize, the filter chain) or Script
  // (Run saves an edited body as the job's custom script, then shows its info and frames or the error).
  // With Settings the Crop toggle shows the crop lines: the output, less a resize after the crop, with
  // the cropped-off margins stacked back on, so the lines are on real pixels and the picture between
  // them is what the encode gets (a FillBorders after the crop included).
  // Auto refresh (on by default, kept in the browser): each saved change renders the frame again. Off,
  // as in VapourSynth Editor, changes still save at once but the frame waits for F5 or Refresh (or a
  // step to another frame, which is rendered as saved); the crop lines still follow at once. F5 never
  // reloads the page here, so it can't lose unsaved script edits; in the Script panel it runs the script.
  // Every save hands us a new `job` object, so effects key on derived values (jobId, scriptKey)
  // that only change when the content does; otherwise each save would remount the preview.
  // Opening a job never indexes its source: until it's indexed the preview is an index panel (Index
  // now puts the job first in the queue's index lane, one job at a time; it's locked meanwhile).
  import { untrack } from 'svelte'
  import { toast } from 'svelte-sonner'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { layout } from '../lib/layout.svelte'
  import { videoView } from '../lib/videoView.svelte'
  import { clipLength } from '../lib/format'
  import { fitted, resizeInput, type Geometry } from '../lib/resize'
  import { SOURCE_FILTERS, type ClipInfo, type Crop, type JobDetail, type SourceFilter, type VideoSettings } from '../lib/types'
  import FramePreview from './FramePreview.svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
  import CropIcon from '@lucide/svelte/icons/crop'
  import DatabaseZapIcon from '@lucide/svelte/icons/database-zap'
  import SquareIcon from '@lucide/svelte/icons/square'
  import MaximizeIcon from '@lucide/svelte/icons/maximize'
  import MinimizeIcon from '@lucide/svelte/icons/minimize'
  import PlayIcon from '@lucide/svelte/icons/play'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import WandSparklesIcon from '@lucide/svelte/icons/wand-sparkles'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as Tabs from '$lib/components/ui/tabs'
  import { Toggle } from '$lib/components/ui/toggle'
  import FilterChain from './FilterChain.svelte'
  import PresetMenu from './PresetMenu.svelte'
  import ResizeEditor from './ResizeEditor.svelte'
  import ScriptEditor from './ScriptEditor.svelte'

  let {
    job,
    save,
    editable,
  }: { job: JobDetail; save: (v: VideoSettings) => Promise<void>; editable: boolean } = $props()

  // Preview, panel, frame, zoom, scroll and the script editor's text, kept per job (JobEditor remounts this per job).
  const vv = videoView(untrack(() => job.id))
  type Stage = 'crop' | 'output'
  const scripting = $derived(vv.panel === 'script') // the preview shows the script's runs
  // A custom body has no crop step to draw: the crop lines are for the generated chain.
  const canCrop = $derived(vv.panel === 'settings' && job.spec.video.custom === null)
  const stage = $derived<Stage>(canCrop && vv.cropView ? 'crop' : 'output')
  let info = $state<Record<Stage, ClipInfo | null>>({ crop: null, output: null })
  let infoError = $state('')
  let version = $state(0)
  let auto = $state(readAuto()) // a save renders the frame again; off, it waits for F5 / Refresh
  let stale = $state(false) // saved changes the frame doesn't show yet (auto off)
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
  // A value, not job: every save brings a new job object, and an effect reading through it reruns each time.
  const sourceFilter = $derived(job.spec.video.source_filter)
  const scriptKey = $derived(job.id + JSON.stringify(job.spec.video) + job.spec.encoder.depth)
  // The source's index is there (for the job's source filter): only then is the clip opened.
  const ready = $derived(job.indexed)
  const live = $derived(app.jobs.find(j => j.id === job.id)) // live status and progress
  const indexStatus = $derived(live?.status ?? job.status)

  async function indexNow() {
    try {
      const r = await api.index([jobId], true)
      if (!r.taken.length) toast.info('Not indexed', { description: 'A queued or running job is indexed by its run.' })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }

  // Expanded is for this tab only: leaving it (another tab, job or page) puts the layout back.
  $effect(() => () => (layout.videoExpanded = false))

  // A new job (or a change made elsewhere) resets the local copy. Not while an edit waits to be
  // saved: a save landing mid-wheel would put back the crop it sent, and the next save would keep it.
  let lastJob = ''
  let lastId = ''
  let queued = false
  $effect(() => {
    const key = job.id + JSON.stringify(job.spec.video)
    if (key !== lastJob) {
      lastJob = key
      if (queued && job.id === lastId) return
      lastId = job.id
      video = structuredClone($state.snapshot(job.spec.video)) as VideoSettings
    }
  })

  // Called from effects: it must not read `info` before its await, or the effect that
  // resets `info` would depend on it and loop. A failure keeps the last good info, so the
  // preview keeps its frame (under the error) instead of unmounting.
  async function loadInfo(st: Stage) {
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
    void sourceFilter // another filter: its own clip (and index)
    if (!ready) return
    // A script view left with a good run shows its output again at once (the rerun refreshes it).
    const ran = untrack(() => vv.checked)
    info = { crop: null, output: ran?.ok ? ran.info : null }
  })

  // Settings: the shown stage's info, again after each save. The script panel runs the script itself
  // (refresh), which brings the output info with it.
  $effect(() => {
    if (ready && vv.panel === 'settings') {
      void version
      void sourceFilter
      loadInfo(stage)
    }
  })

  // Reload the script and run it. After a Run's save the server's body is taken even over local edits.
  // A failed run keeps the last good output info and frame (no version bump), so the preview stays
  // where it was. Called from an effect: nothing it writes is read before the first await.
  async function refresh() {
    const id = jobId
    const adopt = adoptNext
    adoptNext = false
    refreshedKey = scriptKey + ready
    const seq = ++refreshSeq
    running = true
    try {
      const p = await api.script(id).catch(() => null)
      if (seq !== refreshSeq || !p) return
      const keep = dirty && !adopt
      vv.parts = p
      if (!keep) vv.body = p.body.join('\n')
      if (!ready) return // shown, not run: running opens the source
      const c = await api.checkScript(id).catch(e => ({ ok: false as const, error: String(e.message ?? e), line: null }))
      if (seq !== refreshSeq) return
      vv.checked = c
      if (c.ok) {
        info = { ...info, output: c.info }
        stale = false
        version++
      }
    } finally {
      if (seq === refreshSeq) running = false
    }
  }

  // Script panel: run whenever the script's inputs change (once per change, not per job event).
  $effect(() => {
    if (vv.panel === 'script') {
      const key = scriptKey + ready
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
    // A keep-AR resize follows the crop at once (the server fits it the same way on save).
    if (video.resize) video.resize = fitted(video.resize, resizeIn)
    queued = true
    timer = setTimeout(async () => {
      queued = false
      saving = true
      try {
        await save($state.snapshot(video) as VideoSettings)
        if (auto) version++
        else stale = true
      } finally {
        saving = false
      }
    }, delay)
  }

  // Render the frame (and its info) again with the saved settings.
  function refreshPreview() {
    stale = false
    version++
  }

  // A step to another frame (or the crop lines switched) renders it as saved: that is the refresh.
  $effect(() => {
    void vv.frame
    void stage
    untrack(() => stale && refreshPreview())
  })

  function readAuto(): boolean {
    try {
      return localStorage.getItem('videoforge.autoRefresh') !== '0'
    } catch {
      return true // storage blocked
    }
  }

  function setAuto(on: boolean) {
    auto = on
    try {
      localStorage.setItem('videoforge.autoRefresh', on ? '1' : '0')
    } catch {
      /* storage blocked */
    }
    if (on && stale) refreshPreview()
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && !e.defaultPrevented && layout.videoExpanded) layout.videoExpanded = false
    else if (e.key === 'F5' && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault()
      if (!scripting) refreshPreview()
      else if (!running && !saving && ready) run()
    }
  }

  // Crop edits from the side panel show the lines (the picture only shows them in the crop view).
  function setCrop(side: keyof Crop, value: number) {
    const v = Math.max(0, Math.round(value / 2) * 2)
    video.crop = { ...video.crop, [side]: v }
    vv.cropView = true
    commit()
  }

  async function autoCrop() {
    detecting = true
    try {
      video.crop = await api.autocrop(jobId, 20)
      vv.cropView = true
      commit(0)
    } finally {
      detecting = false
    }
  }

  function openScript() {
    vv.panel = 'script'
  }

  // The other stage's info until this one's comes: switching the crop lines keeps the preview up.
  const current = $derived(info[stage] ?? info[stage === 'crop' ? 'output' : 'crop'])
  const notice = $derived.by(() => {
    if (!scripting) return stale ? { text: 'Changed: F5 or Refresh to see it on this frame', tone: 'muted' as const } : null
    if (running) return { text: 'Running the script…', tone: 'muted' as const }
    if (vv.checked && !vv.checked.ok)
      return { text: `The script failed${vv.checked.line ? ` (line ${vv.checked.line})` : ''}: this is the last good frame.`, tone: 'bad' as const }
    return null
  })
  // The probed source (its pixel aspect too), and the picture going into the resize step.
  const source = $derived.by<Geometry | null>(() => {
    const v = job.tracks?.video
    return v && v.width > 0 && v.height > 0 ? { width: v.width, height: v.height, sarNum: v.sar_num ?? 1, sarDen: v.sar_den ?? 1 } : null
  })
  const resizeIn = $derived(source ? resizeInput(video, source) : null)
  // The uncropped frame's size: the crop view's, the probed source's, else the output's plus the saved crop (without a resize).
  const src = $derived.by(() => {
    if (info.crop) return info.crop
    if (source) return source
    const o = info.output
    const c = job.spec.video.crop
    return o && !job.spec.video.resize ? { width: o.width + c.left + c.right, height: o.height + c.top + c.bottom } : null
  })
  const outW = $derived(src ? src.width - video.crop.left - video.crop.right : 0)
  const outH = $derived(src ? src.height - video.crop.top - video.crop.bottom : 0)
  const SIDES: (keyof Crop)[] = ['left', 'top', 'right', 'bottom']
</script>

<svelte:window {onkeydown} />

<div class="flex min-h-0 gap-4 {layout.videoExpanded ? 'fixed inset-0 z-40 bg-background p-4' : 'h-full'}">
  <div class="flex min-w-0 flex-1 flex-col gap-2">
    <div class="flex h-9 items-center gap-2">
      {#if saving}<span class="text-xs text-muted-foreground">saving…</span>{/if}
      {#if infoError && !scripting}<span class="truncate text-xs text-destructive" title={infoError}>{infoError}</span>{/if}
      <Button
        variant="ghost"
        class="ml-auto"
        onclick={() => (layout.videoExpanded = !layout.videoExpanded)}
        title={layout.videoExpanded ? 'Back to the page (Esc)' : 'Fill the window with the video editor'}
      >
        {#if layout.videoExpanded}<MinimizeIcon />Restore{:else}<MaximizeIcon />Expand{/if}
      </Button>
    </div>
    {#if !ready}
      <div class="flex flex-1 flex-col items-center justify-center gap-4 rounded-lg border p-6 text-center" aria-label="Index">
        {#if indexStatus === 'indexing'}
          {@const p = live?.progress}
          <div class="text-base font-medium">Indexing the source…</div>
          <div class="flex w-full max-w-md items-center gap-3 text-sm text-info">
            <div class="h-2 flex-1 overflow-hidden rounded bg-muted">
              <div class="h-full bg-info transition-[width]" style="width:{(p?.fraction ?? 0) * 100}%"></div>
            </div>
            <span class="w-14 text-right tabular-nums">{p ? `${(p.fraction * 100).toFixed(0)}%` : '…'}</span>
          </div>
          <p class="max-w-md text-sm text-muted-foreground">The job is locked until it's done; the preview opens by itself after.</p>
          <Button variant="outline" onclick={() => api.stopIndex([jobId])}><SquareIcon />Stop</Button>
        {:else if indexStatus === 'index-queued'}
          <div class="text-base font-medium">Waiting to be indexed</div>
          <p class="max-w-md text-sm text-muted-foreground">
            {#if live?.index_held}
              An encode is reading this source's disk: it waits until that's done (Settings, Batch indexing). Index this one
              next doesn't wait.
            {:else}
              Sources are indexed one at a time. The preview opens by itself after.
            {/if}
          </p>
          <div class="flex gap-2">
            <Button onclick={indexNow}><DatabaseZapIcon />Index this one next</Button>
            <Button variant="outline" onclick={() => api.stopIndex([jobId])}>Don't index</Button>
          </div>
        {:else}
          <div class="text-base font-medium">The source isn't indexed yet</div>
          <p class="max-w-md text-sm text-muted-foreground">
            The preview, auto-crop and the script's Run need the source's index ({SOURCE_FILTERS.find(f => f.id === job.spec.video.source_filter)?.label}).
            Indexing reads the whole file once (minutes on a large remux), one source at a time; the job is locked while it runs.
            Crop, resize and filters can be set meanwhile.
          </p>
          {#if live?.index_error}<p class="max-w-md text-sm text-destructive">The last index failed: {live.index_error}</p>{/if}
          <Button onclick={indexNow} disabled={!editable}><DatabaseZapIcon />Index now</Button>
        {/if}
      </div>
    {:else if current}
      <FramePreview
        {jobId}
        {stage}
        frames={current.frames}
        fps={current.fps}
        width={current.width}
        height={current.height}
        {version}
        crop={stage === 'crop' ? video.crop : null}
        bind:frame={vv.frame}
        bind:zoom={vv.zoom}
        bind:edges={vv.edges}
        bind:scroll={vv.scroll}
        {notice}
        oncrop={editable && stage === 'crop'
          ? c => {
              video.crop = c
              commit()
            }
          : undefined}
      >
        {#snippet tools()}
          {#if vv.panel === 'settings'}
            <Toggle
              pressed={stage === 'crop'}
              disabled={!canCrop}
              onPressedChange={on => (vv.cropView = on)}
              class="data-[state=on]:bg-primary/15 data-[state=on]:text-primary"
              title={canCrop
                ? 'Crop lines: the output with the cropped-off margins shown (a resize after the crop is left out). Off: the output as encoded'
                : 'A custom script body is in use: it has no crop step to show'}
            >
              <CropIcon />Crop
            </Toggle>
            <Toggle
              pressed={auto}
              onPressedChange={setAuto}
              class="data-[state=on]:bg-primary/15 data-[state=on]:text-primary"
              title="Auto refresh: each change renders the frame again. Off: the frame waits for F5 or Refresh"
            >
              Auto
            </Toggle>
            {#if !auto}
              <Button variant={stale ? 'default' : 'ghost'} onclick={refreshPreview} title="Render the frame with the saved settings (F5)">
                <RefreshCwIcon />Refresh
              </Button>
            {/if}
          {/if}
        {/snippet}
      </FramePreview>
    {:else if scripting}
      <div class="flex flex-1 items-center justify-center border text-muted-foreground">
        {running ? 'Running the script…' : 'No frames: the script failed.'}
      </div>
    {:else}
      <div class="flex flex-1 items-center justify-center border text-muted-foreground">
        {infoError ? 'No preview' : 'Opening the source…'}
      </div>
    {/if}
  </div>

  <div class="flex shrink-0 flex-col gap-2 {vv.panel === 'script' ? 'w-[45%]' : 'w-72'}">
    <Tabs.Root value={vv.panel} onValueChange={v => (v === 'script' ? openScript() : (vv.panel = 'settings'))}>
      <Tabs.List aria-label="Side panel">
        <Tabs.Trigger value="settings" class="px-3">Settings</Tabs.Trigger>
        <Tabs.Trigger value="script" class="px-3">Script</Tabs.Trigger>
      </Tabs.List>
    </Tabs.Root>
  {#if vv.panel === 'script'}
    <section class="flex min-h-0 flex-1 flex-col gap-2">
      <div class="flex items-center gap-2">
        <Button onclick={run} disabled={running || saving || !ready} title={ready ? 'Save the body and run the script (Ctrl+Enter)' : 'Index the source first (the preview side)'}>
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
    <aside class="min-h-0 flex-1 space-y-5 overflow-x-hidden overflow-y-auto pr-1">
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
      <!-- min-w-0: a fieldset is as wide as its widest content by default, which ran past the panel. -->
      <fieldset disabled={!editable} class="min-w-0 space-y-5">
        <section class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="section-label">Crop</span>
            <span class="text-xs text-muted-foreground">{src ? `${outW}×${outH}` : ""}</span>
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
            <Button variant="outline" class="flex-1" onclick={autoCrop} disabled={detecting || !ready} title={ready ? undefined : 'Index the source first'}>
              <WandSparklesIcon />{detecting ? 'Detecting…' : 'Auto-crop'}
            </Button>
            <Button
              variant="outline"
              onclick={() => {
                video.crop = { left: 0, top: 0, right: 0, bottom: 0 }
                vv.cropView = true
                commit(0)
              }}>Reset</Button
            >
          </div>
        </section>

        <section class="space-y-2">
          <span class="section-label">Source filter</span>
          <NativeSelect
            class="w-full"
            aria-label="Source filter"
            value={video.source_filter}
            onchange={e => {
              video.source_filter = (e.target as HTMLSelectElement).value as SourceFilter
              info = { crop: null, output: null }
              commit(0) // the saved job brings the new filter (and whether it's indexed): the preview follows
            }}
          >
            {#each SOURCE_FILTERS as f (f.id)}<option value={f.id} title={f.title}>{f.label}</option>{/each}
          </NativeSelect>
        </section>

        <ResizeEditor bind:resize={video.resize} input={video.custom === null ? resizeIn : null} onchange={() => commit()} />

        <section class="space-y-2">
          <FilterChain bind:filters={video.filters} crop={video.crop} resize={video.resize} disabled={video.custom !== null} onchange={() => commit(0)} />
          {#if video.custom !== null}
            <p class="text-xs text-warning">
              A custom script body is in use, so crop, resize and filters don't apply.
              <button class="underline underline-offset-2" onclick={openScript}>Edit it</button> ·
              <button class="underline underline-offset-2" onclick={useGenerated}>Back to generated</button>
            </p>
          {:else}
            <Button variant="ghost" size="sm" onclick={openScript}>Edit the whole script…</Button>
          {/if}
        </section>
      </fieldset>
    </aside>
  {/if}
  </div>
</div>
