<script lang="ts">
  // The queue: jobs on the left (click, Ctrl/Shift-click, drag across rows, Shift+arrows or Ctrl+A to
  // select several), the selected job's editor on the right, or a batch panel when several are selected.
  import EncoderPanel from '../components/EncoderPanel.svelte'
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import CropIcon from '@lucide/svelte/icons/crop'
  import DatabaseCheckIcon from '@lucide/svelte/icons/database-check'
  import DatabaseXIcon from '@lucide/svelte/icons/database-x'
  import DatabaseZapIcon from '@lucide/svelte/icons/database-zap'
  import GaugeIcon from '@lucide/svelte/icons/gauge'
  import LayoutTemplateIcon from '@lucide/svelte/icons/layout-template'
  import ListChecksIcon from '@lucide/svelte/icons/list-checks'
  import ListEndIcon from '@lucide/svelte/icons/list-end'
  import PanelLeftCloseIcon from '@lucide/svelte/icons/panel-left-close'
  import PanelLeftOpenIcon from '@lucide/svelte/icons/panel-left-open'
  import PauseIcon from '@lucide/svelte/icons/pause'
  import PlayIcon from '@lucide/svelte/icons/play'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import SquareIcon from '@lucide/svelte/icons/square'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import * as Card from '$lib/components/ui/card'
  import * as Dialog from '$lib/components/ui/dialog'
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import JobEditor from '../components/JobEditor.svelte'
  import ReuseDialog from '../components/ReuseDialog.svelte'
  import { api } from '../lib/api'
  import { bytes, percent, PRIORITY_LABEL, progressTimes, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { layout } from '../lib/layout.svelte'
  import { app } from '../lib/state.svelte'
  import type { EncoderSettings, JobDetail, Priority, ReuseJob } from '../lib/types'

  let selected = $state<string[]>([])
  let anchor = $state<string | null>(null)

  // The routed job is selected once it's in the list (the prune below would undo it otherwise).
  $effect(() => {
    const id = router.jobId
    if (id && !selected.includes(id) && app.jobs.some(j => j.id === id)) selected = [id]
  })

  // Forget jobs that are gone.
  $effect(() => {
    const ids = new Set(app.jobs.map(j => j.id))
    if (selected.some(id => !ids.has(id))) selected = selected.filter(id => ids.has(id))
  })

  let cursor = $state<string | null>(null) // the moving end of a Shift+arrow range

  function select(ids: string[]) {
    selected = ids
    router.go('queue', ids.length === 1 ? ids[0] : null)
  }

  function between(from: string, to: string): string[] {
    const ids = app.jobs.map(j => j.id)
    const [a, b] = [ids.indexOf(from), ids.indexOf(to)].sort((x, y) => x - y)
    return ids.slice(a, b + 1)
  }

  // Drag across rows (or rail chips) to select them; Ctrl adds them to the selection. The list scrolls
  // while the pointer is near its top or bottom edge.
  let drag: { from: string; base: string[]; moved: boolean; scroller: HTMLElement; x: number; y: number } | null = null
  let dragged = false // the click that ends a drag doesn't select its row alone

  function dragStart(e: PointerEvent, id: string) {
    const scroller = (e.currentTarget as HTMLElement).closest<HTMLElement>('[data-scroller]')
    if (e.button !== 0 || e.shiftKey || !scroller) return
    drag = { from: id, base: e.ctrlKey || e.metaKey ? [...selected] : [], moved: false, scroller, x: e.clientX, y: e.clientY }
    requestAnimationFrame(dragTick)
  }

  function dragTick() {
    if (!drag) return
    const r = drag.scroller.getBoundingClientRect()
    const edge = 32
    if (drag.y < r.top + edge) drag.scroller.scrollTop -= Math.ceil((r.top + edge - drag.y) / 3)
    else if (drag.y > r.bottom - edge) drag.scroller.scrollTop += Math.ceil((drag.y - r.bottom + edge) / 3)
    const x = Math.min(Math.max(drag.x, r.left + 2), r.right - 2)
    const y = Math.min(Math.max(drag.y, r.top + 2), r.bottom - 2)
    const id = document.elementFromPoint(x, y)?.closest('[data-job]')?.getAttribute('data-job')
    if (id && (drag.moved || id !== drag.from)) {
      drag.moved = true
      const range = new Set([...drag.base, ...between(drag.from, id)])
      const ids = app.jobs.map(j => j.id).filter(j => range.has(j))
      if (ids.length !== selected.length || ids.some((j, i) => j !== selected[i])) select(ids)
      anchor = drag.from
      cursor = id
    }
    requestAnimationFrame(dragTick)
  }

  function dragMove(e: PointerEvent) {
    if (drag) [drag.x, drag.y] = [e.clientX, e.clientY]
  }

  function dragEnd() {
    if (drag?.moved) {
      dragged = true
      setTimeout(() => (dragged = false))
    }
    drag = null
  }

  // Up/Down (Home/End) move the selection, with Shift they stretch it from the anchor; Ctrl+A selects all.
  function keys(e: KeyboardEvent) {
    const ids = app.jobs.map(j => j.id)
    if (!ids.length) return
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault()
      select(ids)
      return
    }
    const at = ids.indexOf(cursor ?? anchor ?? selected.at(-1) ?? ids[0])
    const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: ids.length - 1 }[e.key]
    if (to === undefined || e.ctrlKey || e.altKey || e.metaKey) return
    e.preventDefault()
    const id = ids[Math.min(Math.max(to, 0), ids.length - 1)]
    cursor = id
    if (e.shiftKey && anchor) select(between(anchor, id))
    else {
      anchor = id
      select([id])
    }
    const row = (e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-job="${id}"]`)
    row?.focus()
    row?.scrollIntoView({ block: 'nearest' })
  }

  function click(e: MouseEvent, id: string) {
    if (dragged) return
    cursor = id
    if (e.shiftKey && anchor) {
      const ids = app.jobs.map(j => j.id)
      const [a, b] = [ids.indexOf(anchor), ids.indexOf(id)].sort((x, y) => x - y)
      selected = ids.slice(a, b + 1)
    } else if (e.ctrlKey || e.metaKey) {
      selected = selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]
      anchor = id
    } else {
      selected = [id]
      anchor = id
      peek = false
    }
    router.go('queue', selected.length === 1 ? selected[0] : null)
  }

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }

  // Start queue / Run selected: when the jobs have finished files from an earlier run, ask which to reuse.
  let reuseJobs = $state<ReuseJob[]>([])
  let reuseIds = $state<string[] | undefined>()
  let reuseOpen = $state(false)

  async function run(ids?: string[]) {
    const { jobs } = await api.reuse(ids)
    if (!jobs.length) return api.start(ids)
    reuseJobs = jobs
    reuseIds = ids
    reuseOpen = true
  }

  function startReusing(reuse: Record<string, string[]>) {
    reuseOpen = false
    act(() => api.start(reuseIds, reuse))
  }

  async function move(step: number) {
    const ids = app.jobs.map(j => j.id)
    const sel = new Set(selected)
    const order = step < 0 ? ids : [...ids].reverse()
    for (let i = 1; i < order.length; i++) {
      if (sel.has(order[i]) && !sel.has(order[i - 1])) [order[i - 1], order[i]] = [order[i], order[i - 1]]
    }
    await act(() => api.reorder(step < 0 ? order : order.reverse()))
  }

  // workDirs: their <source>_tmp folders go too (one another job in the queue shares is kept)
  let removal = $state<Awaited<ReturnType<typeof api.removalPreview>> | null>(null)
  let removing = $state(false)

  async function confirmRemoval() {
    await act(async () => { removal = await api.removalPreview([...selected]) })
  }

  async function remove(workDirs = false, ids = [...selected]) {
    removing = true
    await act(async () => {
      const r = await api.remove(ids, workDirs)
      if (r.removed.length < ids.length) toast.info('Queued, running or indexing jobs were kept')
      if (!workDirs && r.removed.length) toast.success(`Removed ${r.removed.length} job(s)`, {
        action: { label: 'Undo', onClick: () => act(async () => {
          const restored = await api.restore(r.removed)
          await app.refreshJobs()
          toast.info(`Restored ${restored.restored.length} job(s)`)
        }) },
      })
      const kept = Object.entries(r.kept)
      if (r.deleted.length) toast.info(`Deleted ${r.deleted.length} work folder${r.deleted.length > 1 ? 's' : ''}`)
      if (kept.length) {
        toast.warning(`Kept ${kept.length} work folder${kept.length > 1 ? 's' : ''}`, {
          description: kept.map(([folder, why]) => `${folder}: ${why}`).join('; '),
        })
      }
      selected = []
      router.go('queue')
      removal = null
    })
    removing = false
  }

  // The index lane: each job's work folder, script and source index, one job at a time, nothing else.
  // Jobs already indexed are skipped.
  const unindexed = (ids: string[]) => {
    const want = new Set(ids)
    return app.jobs.filter(j => want.has(j.id) && !j.indexed).map(j => j.id)
  }

  async function index(ids: string[]) {
    const todo = unindexed(ids)
    const done = ids.length - todo.length
    const already = done ? `${done} already indexed.` : ''
    if (!todo.length) {
      toast.info('Nothing to index', { description: already })
      return
    }
    await act(async () => {
      const r = await api.index(todo)
      const left = todo.length - r.taken.length
      const out = left ? `${left} left out (queued, running, already indexing, or reusing an encode).` : ''
      if (!r.taken.length) toast.info('Nothing to index', { description: [already, out].join(' ').trim() })
      else toast.info(`Indexing ${r.taken.length} job${r.taken.length > 1 ? 's' : ''}`, {
        description: [already, out].join(' ').trim() || undefined,
      })
    })
  }
  const indexing = $derived(!!app.queue.indexing || app.queue.index_queued > 0)
  // tools running now (the job's, the index lane's): what Pause and the priority menu reach
  const working = $derived(!!app.queue.current || !!app.queue.indexing)
  const paused = (status: string) => app.queue.paused && (status === 'running' || status === 'indexing')
  // The toolbar's Index: the selected jobs, or every job when none is selected.
  const indexTarget = $derived(selected.length ? selected : app.jobs.map(j => j.id))
  const toIndex = $derived(unindexed(indexTarget).length)
  const batchToIndex = $derived(unindexed(selected).length)

  const single = $derived(selected.length === 1 ? selected[0] : null)

  // A narrow window gives an open job the room: the list is a rail, and opens over the editor (peek)
  // until a job is picked, Esc or a click elsewhere.
  let peek = $state(false)
  let railEl = $state<HTMLElement>()
  let listEl = $state<HTMLElement>()
  const rail = $derived(layout.queueCollapsed || (layout.narrow && single !== null))
  $effect(() => {
    if (!rail) peek = false
  })

  function showList() {
    layout.queueCollapsed = false
    if (layout.narrow && single !== null) peek = true
  }

  function hideList() {
    if (peek) peek = false
    else layout.queueCollapsed = true
  }

  function outside(e: PointerEvent) {
    const t = e.target as Node
    if (peek && !listEl?.contains(t) && !railEl?.contains(t)) peek = false
  }

  const runnable = $derived(app.jobs.some(j => ['ready', 'warn', 'queued'].includes(j.status)))

  // --- batch panel ---
  let batchSource = $state<JobDetail | null>(null)
  $effect(() => {
    if (selected.length > 1) api.job(selected[0]).then(j => (batchSource = j))
    else batchSource = null
  })

  async function applyEncoder(encoder: EncoderSettings) {
    if (!batchSource) return
    batchSource.spec.encoder = encoder
    await act(async () => {
      const r = await api.apply(selected, { encoder })
      toast.success(`Encoder applied to ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
    })
  }

  // A template (by name) for the whole batch, from the first job's profile's choices.
  let batchTemplate = $state('')
  const batchTemplates = $derived(batchSource ? app.presetChoices('template', batchSource.profile) : [])
  const picked = $derived(batchTemplates.find(c => c.name === batchTemplate) ?? batchTemplates[0])
  const batchContainers = $derived(app.profiles.find(p => p.id === batchSource?.profile)?.containers ?? [])

  async function applyTemplate() {
    if (!picked) return
    const name = picked.name
    await act(async () => {
      const r = await api.apply(selected, { template: $state.snapshot(picked.data) })
      toast.success(`Template ${name} applied to ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
      batchSource = await api.job(selected[0])
    })
  }

  async function applyContainer(container: string) {
    if (!batchSource) return
    batchSource.spec.mux.container = container
    await act(async () => {
      const r = await api.apply(selected, { container })
      const label = batchContainers.find(c => c.id === container)?.label ?? container
      toast.success(`${label} for ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
    })
  }

  async function applyCrop() {
    if (!batchSource) return
    const crop = batchSource.spec.video.crop
    await act(async () => {
      const jobs = await Promise.all(selected.map(id => api.job(id)))
      for (const j of jobs) if (j.spec.inputs.encode === null) await api.update(j.id, { video: { ...j.spec.video, crop } })
      toast.success(`Crop ${crop.left}/${crop.top}/${crop.right}/${crop.bottom} applied to ${jobs.length} job(s)`)
    })
  }
</script>

<svelte:window
  onpointerdown={outside}
  onpointermove={dragMove}
  onpointerup={dragEnd}
  onpointercancel={dragEnd}
  onkeydown={e => {
    if (peek && e.key === 'Escape') {
      peek = false
      e.stopPropagation()
    }
  }}
/>

<div class="relative flex h-full">
  {#if rail}
    <!-- The list as a rail: one chip per job (its place, coloured by status). -->
    <section bind:this={railEl} class="flex w-14 shrink-0 flex-col items-center border-r border-border">
      <Button
        variant="ghost"
        size="icon"
        class="my-2"
        onclick={() => (peek ? (peek = false) : showList())}
        title={layout.narrow && single !== null ? 'Show the queue list (over the editor: the window is narrow)' : 'Show the queue list'}
        aria-label="Show the queue list"
        aria-expanded={peek}
      >
        <PanelLeftOpenIcon />
      </Button>
      <!-- svelte-ignore a11y_no_static_element_interactions (the arrow keys of the chips inside) -->
      <div data-scroller class="flex min-h-0 w-full flex-1 flex-col items-center gap-1 overflow-auto border-t border-border py-2 select-none" onkeydown={keys}>
        {#each app.jobs as job, i (job.id)}
          <button
            data-job={job.id}
            class="relative flex h-9 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border text-xs
              {selected.includes(job.id) ? 'border-primary bg-primary/15' : 'hover:bg-accent'}
              {STATUS_TONE[job.status]}"
            onpointerdown={e => dragStart(e, job.id)}
            onclick={e => click(e, job.id)}
            title="{job.name}: {STATUS_LABEL[job.status]}{job.issue ? ` (${job.issue})` : ''}"
          >
            {i + 1}
            {#if (job.status === 'running' || job.status === 'indexing') && job.progress}
              <span class="absolute inset-x-0 bottom-0 h-1 bg-muted">
                <span class="block h-full bg-info" style="width:{job.progress.overall * 100}%"></span>
              </span>
            {/if}
          </button>
        {/each}
      </div>
    </section>
    {#if peek}{@render list('absolute inset-y-0 left-14 z-30 w-[28rem] max-w-[calc(100%-3.5rem)] bg-background shadow-xl')}{/if}
  {:else}
    {@render list('w-[28rem] shrink-0')}
  {/if}

{#snippet list(cls: string)}
  <section bind:this={listEl} class="flex flex-col border-r border-border {cls}" aria-label="Queue list">
    <div class="flex flex-wrap items-center gap-1 border-b border-border p-2">
      <Button variant="ghost" size="icon" onclick={hideList} title={peek ? 'Hide the list (Esc)' : 'Collapse the list, for more room'}>
        <PanelLeftCloseIcon />
      </Button>
      {#if app.queue.running}
        <Button variant="outline" onclick={() => act(api.stop)} title="Finish the current job, then stop">
          <ListEndIcon />{app.queue.stop_after_current ? 'Stopping…' : 'Stop after current'}
        </Button>
        <Button variant="outline" onclick={() => act(api.cancel)} title="Cancel the running job"><SquareIcon />Cancel</Button>
      {:else}
        <Button disabled={!runnable} onclick={() => act(() => run())} title="Run every ready job in order">
          <PlayIcon />Start queue
        </Button>
      {/if}
      {#if working || app.queue.paused}
        {#if app.queue.paused}
          <Button onclick={() => act(api.resume)} title="Go on with the paused tools"><PlayIcon />Resume</Button>
        {:else}
          <Button variant="outline" onclick={() => act(api.pause)}
            title="Suspend the running job's tools and the index lane's (they use no CPU until resumed)">
            <PauseIcon />Pause
          </Button>
        {/if}
        <DropdownMenu.Root>
          <DropdownMenu.Trigger disabled={!working}
            title="Process priority of the running tools, for the rest of their run (Settings has the default)">
            {#snippet child({ props })}
              <Button {...props} variant="ghost" size="icon" aria-label="Process priority"><GaugeIcon /></Button>
            {/snippet}
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="start" class="w-48">
            <DropdownMenu.Label>Priority, this run</DropdownMenu.Label>
            <DropdownMenu.RadioGroup value={app.queue.priority ?? ''}
              onValueChange={v => act(() => api.priority((v || null) as Priority | null))}>
              <DropdownMenu.RadioItem value="">As in Settings</DropdownMenu.RadioItem>
              {#each Object.entries(PRIORITY_LABEL) as [value, label] (value)}
                <DropdownMenu.RadioItem {value}>{label}</DropdownMenu.RadioItem>
              {/each}
            </DropdownMenu.RadioGroup>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      {/if}
      <Button variant="outline" disabled={!selected.length} onclick={() => act(() => run(selected))} title="Queue the selected jobs and start">
        <PlayIcon />Run selected
      </Button>
      {#if indexing}
        <Button variant="outline" onclick={() => act(() => app.stopIndexing())} title="Stop indexing: cancel the job being indexed and the ones waiting">
          <DatabaseXIcon />Stop indexing
        </Button>
      {/if}
      <span class="flex-1"></span>
      <Button variant="ghost" size="icon" disabled={!app.jobs.length} onclick={() => select(app.jobs.map(j => j.id))}
        title="Select all (Ctrl+A)" aria-label="Select all"><ListChecksIcon /></Button>
      <Button variant="ghost" size="icon" disabled={!toIndex} onclick={() => index(indexTarget)}
        title="Index {selected.length ? 'the selected jobs' : 'every job'} not indexed yet ({toIndex}): one at a time, each gets its work folder, script and source index, and nothing else, so its video opens at once (runs next to the queue)"
        aria-label={selected.length ? 'Index the selected jobs' : 'Index every job not indexed yet'}><DatabaseZapIcon /></Button>
      <Button variant="ghost" size="icon" disabled={!selected.length} onclick={() => move(-1)} title="Move up"><ArrowUpIcon /></Button>
      <Button variant="ghost" size="icon" disabled={!selected.length} onclick={() => move(1)} title="Move down"><ArrowDownIcon /></Button>
      <Button variant="ghost" size="icon" disabled={!selected.length} onclick={() => act(() => api.reprobe(selected))} title="Probe again">
        <RefreshCwIcon />
      </Button>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger disabled={!selected.length} title="Remove">
          {#snippet child({ props })}
            <Button {...props} variant="ghost" size="icon" class="hover:text-destructive" aria-label="Remove"><Trash2Icon /></Button>
          {/snippet}
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="end" class="w-auto">
          <DropdownMenu.Item onSelect={() => remove()}>Remove from the queue</DropdownMenu.Item>
          <DropdownMenu.Item onSelect={confirmRemoval} title="Review the work folders before deleting their intermediate files">
            Remove and delete work folders
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    </div>

    <!-- svelte-ignore a11y_no_static_element_interactions (the arrow keys of the rows inside) -->
    <div data-scroller class="min-h-0 flex-1 overflow-auto select-none" onkeydown={keys}>
      {#each app.jobs as job (job.id)}
        <button
          data-job={job.id}
          class="block w-full border-b border-border/60 px-3 py-2 text-left
            {selected.includes(job.id) ? 'bg-primary/15' : 'hover:bg-accent'}"
          onpointerdown={e => dragStart(e, job.id)}
          onclick={e => click(e, job.id)}
        >
          <div class="flex items-center gap-2">
            <span class="truncate font-medium" title={job.source}>{job.name}</span>
            {#if paused(job.status)}
              <span class="ml-auto shrink-0 text-xs text-warning">Paused</span>
            {:else}
              <span class="ml-auto shrink-0 text-xs {STATUS_TONE[job.status]}">{STATUS_LABEL[job.status]}</span>
            {/if}
          </div>
          <div class="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{job.encoder}</span>
            {#if job.custom_script}
              <span>· custom script</span>
            {:else if job.crop && (job.crop.top || job.crop.bottom || job.crop.left || job.crop.right)}
              <span>· crop {job.crop.left}/{job.crop.top}/{job.crop.right}/{job.crop.bottom}</span>
            {/if}
            <span>· {job.audio.length} audio · {job.subs} subs</span>
            {#if job.indexed}
              <span class="ml-auto flex shrink-0 items-center" title="Indexed: the video opens at once"><DatabaseCheckIcon class="size-3.5" /></span>
            {/if}
          </div>
          {#if (job.status === 'running' || job.status === 'indexing') && job.progress}
            <div class="mt-1.5 flex items-center gap-2 text-xs text-info">
              <div class="h-1 flex-1 overflow-hidden rounded bg-muted">
                <div class="h-full bg-info" style="width:{job.progress.overall * 100}%"></div>
              </div>
              {percent(job.progress.overall)}
            </div>
            <div class="flex gap-2 text-xs text-muted-foreground">
              <span class="truncate">{job.progress.step}</span>
              <span class="ml-auto shrink-0 tabular-nums" title="Encoder speed · time since the run started · the job's time left (a guess from its pace so far)"
                >{progressTimes(job.progress)}</span
              >
            </div>
          {:else if job.issue}
            <div class="mt-0.5 truncate text-xs {['blocked', 'error', 'failed', 'invalid'].includes(job.status) ? 'text-destructive' : 'text-warning'}">
              {job.issue}
            </div>
          {/if}
          {#if job.index_held && job.status === 'index-queued'}
            <div class="mt-0.5 truncate text-xs text-muted-foreground" title="Settings, Batch indexing">
              Waits: an encode is reading this disk
            </div>
          {/if}
          {#if job.index_error && job.status !== 'indexing'}
            <div class="mt-0.5 truncate text-xs text-warning" title={job.index_error}>Index failed: {job.index_error}</div>
          {/if}
        </button>
      {:else}
        <div class="p-6 text-center text-muted-foreground">
          No jobs yet. <Button variant="link" class="h-auto p-0" onclick={() => router.go('new')}>Add some</Button>.
        </div>
      {/each}
    </div>
  </section>
{/snippet}

  <section class="min-w-0 flex-1 overflow-auto">
    {#if single}
      {#key single}<JobEditor jobId={single} />{/key}
    {:else if selected.length > 1}
      <div class="max-w-3xl space-y-6 p-6">
        <h2 class="text-lg font-semibold">{selected.length} jobs selected</h2>
        <p class="text-sm text-muted-foreground">
          Settings here apply to every selected job (queued or running ones are skipped). Starting values are the first
          job's. Audio and subtitle choices stay per job unless the template sets them.
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <Button variant="outline" disabled={!batchToIndex} onclick={() => index(selected)}>
            <DatabaseZapIcon />{batchToIndex ? `Index ${batchToIndex} job${batchToIndex > 1 ? 's' : ''}` : 'All indexed'}
          </Button>
          <span class="text-sm text-muted-foreground">
            One at a time: the work folder, script and source index, nothing else. Their video then opens at once, and the
            encode reuses the index.{batchToIndex && batchToIndex < selected.length ? ` ${selected.length - batchToIndex} already indexed.` : ''}
          </span>
        </div>
        {#if batchSource}
          <Card.Root class="gap-2 p-4">
            <div class="flex flex-wrap items-center gap-3">
              <span class="text-sm">Template</span>
              <NativeSelect aria-label="Template for the selected jobs" value={picked?.name ?? ''} onchange={e => (batchTemplate = e.currentTarget.value)}>
                {#each batchTemplates as c (`${c.builtin}:${c.name}`)}<option value={c.name}>{c.name}</option>{/each}
              </NativeSelect>
              <Button class="ml-auto" onclick={applyTemplate} disabled={!picked}><LayoutTemplateIcon />Apply to {selected.length} jobs</Button>
            </div>
            <p class="text-xs text-muted-foreground">
              Sets video, encoder, container, AutoQPF{picked?.data.audio ? ', audio' : ''}{picked?.data.crop_mode === 'auto'
                ? '; the crop is detected for each job'
                : picked?.data.crop_mode === 'fixed'
                  ? `; crop ${picked.data.video.crop.left}/${picked.data.video.crop.top}/${picked.data.video.crop.right}/${picked.data.video.crop.bottom} on every job`
                  : '; each job keeps its crop'}. Save templates from a job's Template menu.
            </p>
          </Card.Root>
          {#if batchContainers.length > 1}
            <Card.Root class="flex-row flex-wrap items-center gap-3 p-4">
              <span class="text-sm">Container</span>
              <ToggleGroup.Root
                type="single"
                variant="outline"
                spacing={1}
                class="w-fit max-w-full flex-wrap"
                value={batchSource.spec.mux.container || batchContainers[0].id}
                onValueChange={v => v && applyContainer(v)}
              >
                {#each batchContainers as c (c.id)}
                  <ToggleGroup.Item value={c.id} class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{c.label}</ToggleGroup.Item>
                {/each}
              </ToggleGroup.Root>
              <span class="text-xs text-muted-foreground">Each job keeps its extra muxer arguments.</span>
            </Card.Root>
          {/if}
          <Card.Root class="p-4">
            <EncoderPanel profile={batchSource.profile} value={batchSource.spec.encoder} onchange={applyEncoder} />
          </Card.Root>
          <Card.Root class="flex-row items-center gap-3 p-4">
            <span class="text-sm">
              Crop from {batchSource.name}: {batchSource.spec.video.crop.left}/{batchSource.spec.video.crop.top}/{batchSource
                .spec.video.crop.right}/{batchSource.spec.video.crop.bottom}
            </span>
            <Button variant="outline" class="ml-auto" onclick={applyCrop}><CropIcon />Apply this crop to all</Button>
          </Card.Root>
        {/if}
      </div>
    {:else}
      <div class="flex h-full items-center justify-center text-muted-foreground">Select a job to edit it.</div>
    {/if}
  </section>
</div>

<ReuseDialog bind:open={reuseOpen} jobs={reuseJobs} onstart={startReusing} />

<Dialog.Root open={removal !== null} onOpenChange={open => { if (!open && !removing) removal = null }}>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>Remove jobs and delete working files?</Dialog.Title>
      <Dialog.Description>Records and logs are archived first. Indexes, scripts and intermediate encodes are permanently deleted; a rerun must recreate them. Finished output files are kept.</Dialog.Description>
    </Dialog.Header>
    <div class="max-h-64 space-y-3 overflow-auto text-sm">
      {#each removal?.folders ?? [] as folder (folder.id)}
        <div><code class="break-all">{folder.path}</code><div class="text-muted-foreground">{folder.bytes === null ? 'Size unavailable' : bytes(folder.bytes)}{folder.error ? ` · ${folder.error}` : ''}</div></div>
      {/each}
    </div>
    <Dialog.Footer>
      <Button variant="outline" disabled={removing} onclick={() => removal = null}>Cancel</Button>
      <Button variant="destructive" disabled={removing} onclick={() => remove(true, removal?.folders.map(f => f.id) ?? [])}>{removing ? 'Removing…' : 'Remove and delete'}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
