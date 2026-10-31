<script lang="ts">
  // The queue: jobs on the left (click, Ctrl/Shift-click, drag across rows, Shift+arrows or Ctrl+A to
  // select several), the selected job's editor on the right, or a batch panel when several are selected.
  import EncoderPanel from '../components/EncoderPanel.svelte'
  import { tick, onDestroy } from 'svelte'
  import { Input } from '$lib/components/ui/input'
  import { matchingJobs, queuePage, queueRange, queueable, QUEUE_PAGE_SIZE } from '../lib/queueView'
  import { saves } from '../lib/saves'
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left'
  import CopyPlusIcon from '@lucide/svelte/icons/copy-plus'
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
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Card from '$lib/components/ui/card'
  import * as Dialog from '$lib/components/ui/dialog'
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import JobEditor from '../components/JobEditor.svelte'
  import ReuseDialog from '../components/ReuseDialog.svelte'
  import Tip from '../components/Tip.svelte'
  import { api } from '../lib/api'
  import { bytes, percent, PRIORITY_LABEL, progressTimes, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { layout } from '../lib/layout.svelte'
  import { app } from '../lib/state.svelte'
  import type { EncoderSettings, JobDetail, Priority, ReuseJob, Status } from '../lib/types'

  let selected = $state<string[]>([])
  let anchor = $state<string | null>(null)
  let query = $state('')
  let status = $state<Status | ''>('')
  let page = $state(0)
  const searched = $derived(matchingJobs(app.jobs, query))
  const counts = $derived.by(() => {
    const result = new Map<Status, number>()
    for (const job of searched) result.set(job.status, (result.get(job.status) ?? 0) + 1)
    return result
  })
  const matching = $derived(status ? searched.filter((job) => job.status === status) : searched)
  const matchingIds = $derived(matching.map((job) => job.id))
  const matchingSet = $derived(new Set(matchingIds))
  const selectedSet = $derived(new Set(selected))
  const hiddenSelected = $derived(selected.filter((id) => !matchingSet.has(id)).length)
  const currentPage = $derived(queuePage(matching.length, page))
  const pageJobs = $derived(matching.slice(currentPage * QUEUE_PAGE_SIZE, (currentPage + 1) * QUEUE_PAGE_SIZE))
  const tabStop = $derived(
    pageJobs.find((job) => job.id === cursor)?.id ??
      pageJobs.find((job) => selectedSet.has(job.id))?.id ??
      pageJobs[0]?.id,
  )
  const waitingSelected = $derived(
    app.jobs.filter((job) => selectedSet.has(job.id) && job.status === 'queued').map((job) => job.id),
  )
  const queueableSelected = $derived(
    app.jobs.filter((job) => selectedSet.has(job.id) && queueable(job.status)).map((job) => job.id),
  )

  function filterChanged() {
    page = 0
    anchor = null
    cursor = null
    dragEnd()
    listEl?.querySelector('[data-scroller]')?.scrollTo(0, 0)
  }

  function clearFilters() {
    query = ''
    status = ''
    filterChanged()
  }

  async function changePage(next: number) {
    page = queuePage(matching.length, next)
    await tick()
    const scroller = (peek || !rail ? listEl : railEl)?.querySelector<HTMLElement>('[data-scroller]')
    scroller?.scrollTo(0, 0)
    scroller?.querySelector<HTMLElement>('[data-job]')?.focus()
  }

  async function focusJob(id: string) {
    await tick()
    const surface = peek || !rail ? listEl : railEl
    const row = Array.from(surface?.querySelectorAll<HTMLElement>('[data-job]') ?? []).find(
      (row) => row.dataset.job === id,
    )
    row?.focus()
    row?.scrollIntoView({ block: 'nearest' })
  }

  async function clearSelection() {
    select([])
    await tick()
    if (rail) railEl?.querySelector<HTMLElement>('button')?.focus()
    else listEl?.querySelector<HTMLInputElement>('input[type="search"]')?.focus()
  }

  function selectMatching() {
    select(matchingIds)
    if (matchingIds.length === 1) void focusJob(matchingIds[0])
  }

  async function unqueue(ids = [...waitingSelected]) {
    await api.dequeue(ids)
    await app.refreshJobs()
    if (ids.length > 1)
      toast.success(`Unqueued ${ids.length} jobs`, {
        description: 'Their settings can be edited again; the queue leaves them out.',
      })
  }

  // Queued: locked (read-only), and the queue runs it, even one already running. Edits still saving go first.
  async function queue(ids = [...queueableSelected]) {
    await saves.flush()
    const { enqueued } = await api.enqueue(ids)
    await app.refreshJobs()
    if (enqueued.length < ids.length) {
      toast.warning(`Queued ${enqueued.length} of ${ids.length} jobs`, {
        description: 'The others are still being probed or indexed, or are blocked.',
      })
    } else if (ids.length > 1)
      toast.success(`Queued ${ids.length} jobs`, { description: 'Locked until they run; Start queue runs them.' })
  }

  // The routed job is selected once it's in the list (the prune below would undo it otherwise).
  $effect(() => {
    const id = router.jobId
    if (id && !selected.includes(id) && app.jobs.some((j) => j.id === id)) {
      selected = [id]
      query = ''
      status = ''
      page = Math.floor(app.jobs.findIndex((j) => j.id === id) / QUEUE_PAGE_SIZE)
    }
  })

  // Forget jobs that are gone.
  $effect(() => {
    const ids = new Set(app.jobs.map((j) => j.id))
    if (selected.some((id) => !ids.has(id))) selected = selected.filter((id) => ids.has(id))
  })

  // A live status change can remove the focused row from the current filter.
  $effect.pre(() => {
    const ids = matchingSet
    const focused = document.activeElement as HTMLElement | null
    if (
      focused?.dataset.job &&
      !ids.has(focused.dataset.job) &&
      (listEl?.contains(focused) || railEl?.contains(focused))
    ) {
      tick().then(() => {
        const surface = peek || !rail ? listEl : railEl
        const target =
          surface?.querySelector<HTMLElement>('[data-job][tabindex="0"]') ??
          surface?.querySelector<HTMLElement>('input[type="search"], button')
        target?.focus()
      })
    }
  })

  let cursor = $state<string | null>(null) // the moving end of a Shift+arrow range

  function select(ids: string[]) {
    selected = ids
    router.go('queue', ids.length === 1 ? ids[0] : null)
  }

  function between(from: string, to: string): string[] {
    return queueRange(matchingIds, from, to)
  }

  // Drag across rows (or rail chips) to select them; Ctrl adds them to the selection. The list scrolls
  // while the pointer is near its top or bottom edge.
  let drag: { from: string; base: string[]; moved: boolean; scroller: HTMLElement; x: number; y: number } | null = null
  let dragged = false // the click that ends a drag doesn't select its row alone

  function dragStart(e: PointerEvent, id: string) {
    const scroller = (e.currentTarget as HTMLElement).closest<HTMLElement>('[data-scroller]')
    if (e.button !== 0 || e.shiftKey || !scroller) return
    drag = {
      from: id,
      base: e.ctrlKey || e.metaKey ? [...selected] : [],
      moved: false,
      scroller,
      x: e.clientX,
      y: e.clientY,
    }
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
      const ids = app.jobs.filter((j) => range.has(j.id)).map((j) => j.id)
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
  onDestroy(dragEnd)

  // Up/Down (Home/End) move the selection, with Shift they stretch it from the anchor; Ctrl+A selects all.
  async function keys(e: KeyboardEvent) {
    const ids = matchingIds
    if (!ids.length) return
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault()
      select(ids)
      return
    }
    const target = (e.target as HTMLElement).closest<HTMLElement>('[data-job]')?.dataset.job
    if (!target) return
    const at = Math.max(0, ids.indexOf(target))
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
    page = Math.floor(ids.indexOf(id) / QUEUE_PAGE_SIZE)
    await focusJob(id)
  }

  function click(e: MouseEvent, id: string) {
    if (dragged) return
    cursor = id
    if (e.shiftKey && anchor) {
      selected = between(anchor, id)
    } else if (e.ctrlKey || e.metaKey) {
      selected = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
      anchor = id
    } else {
      selected = [id]
      anchor = id
      peek = false
    }
    router.go('queue', selected.length === 1 ? selected[0] : null)
    void focusJob(id)
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
  let starting = $state(false)
  let saveError = $state('')
  $effect(() =>
    saves.subscribe((error) => {
      saveError = error
    }),
  )

  async function run(ids?: string[]) {
    if (starting) return
    starting = true
    try {
      await saves.flush()
      const { jobs } = await api.reuse(ids)
      if (!jobs.length) return await api.start(ids)
      reuseJobs = jobs
      reuseIds = ids
      reuseOpen = true
    } finally {
      starting = false
    }
  }

  function startReusing(reuse: Record<string, string[]>) {
    reuseOpen = false
    act(async () => {
      await saves.flush()
      await api.start(reuseIds, reuse)
    })
  }

  async function move(step: number) {
    const ids = app.jobs.map((j) => j.id)
    const sel = new Set(selected)
    const order = step < 0 ? ids : [...ids].reverse()
    for (let i = 1; i < order.length; i++) {
      if (sel.has(order[i]) && !sel.has(order[i - 1])) [order[i - 1], order[i]] = [order[i], order[i - 1]]
    }
    await act(() => api.reorder(step < 0 ? order : order.reverse()))
  }

  // A copy of each selected job right after it (same source and settings, a label of its own), for a second
  // output with a few settings changed; the copy's run reuses what the two share. The copies end up selected.
  async function duplicate() {
    await act(async () => {
      await saves.flush()
      const { added } = await api.duplicate([...selected])
      await app.refreshJobs()
      select(added)
      if (added.length === 1) void focusJob(added[0])
      toast.success(added.length === 1 ? 'Job duplicated' : `Duplicated ${added.length} jobs`, {
        description: 'Each copy has a label of its own (Output tab), so it writes its own file.',
      })
    })
  }

  // workDirs: their <source>_tmp folders go too (one another job in the queue shares is kept)
  let removal = $state<Awaited<ReturnType<typeof api.removalPreview>> | null>(null)
  let removing = $state(false)

  async function confirmRemoval() {
    await act(async () => {
      removal = await api.removalPreview([...selected])
    })
  }

  async function remove(workDirs = false, ids = [...selected]) {
    removing = true
    await act(async () => {
      const r = await api.remove(ids, workDirs)
      if (r.removed.length < ids.length) toast.info('Queued, running or indexing jobs were kept')
      if (!workDirs && r.removed.length)
        toast.success(`Removed ${r.removed.length} job(s)`, {
          action: {
            label: 'Undo',
            onClick: () =>
              act(async () => {
                const restored = await api.restore(r.removed)
                await app.refreshJobs()
                toast.info(`Restored ${restored.restored.length} job(s)`)
              }),
          },
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
    return app.jobs.filter((j) => want.has(j.id) && !j.indexed).map((j) => j.id)
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
      await saves.flush()
      const r = await api.index(todo)
      const left = todo.length - r.taken.length
      const out = left ? `${left} left out (queued, running, already indexing, or reusing an encode).` : ''
      if (!r.taken.length) toast.info('Nothing to index', { description: [already, out].join(' ').trim() })
      else
        toast.info(`Indexing ${r.taken.length} job${r.taken.length > 1 ? 's' : ''}`, {
          description: [already, out].join(' ').trim() || undefined,
        })
    })
  }
  const indexing = $derived(!!app.queue.indexing || !!app.queue.sampling || app.queue.index_queued > 0)
  // tools running now (the job's, the index lane's, a test encode there): what Pause and the priority menu reach
  const working = $derived(!!app.queue.current || !!app.queue.indexing || !!app.queue.sampling)
  const LIVE = ['running', 'indexing', 'sampling'] // statuses with progress
  const paused = (status: string) => app.queue.paused && LIVE.includes(status)
  // The toolbar's Index: the selected jobs, or every job when none is selected.
  const indexTarget = $derived(selected.length ? selected : app.jobs.map((j) => j.id))
  const toIndex = $derived(unindexed(indexTarget).length)
  const batchToIndex = $derived(unindexed(selected).length)

  const single = $derived(selected.length === 1 ? selected[0] : null)

  // A narrow window gives an open job the room: the list is a rail, and opens over the editor (peek)
  // until a job is picked, Esc or a click elsewhere. A phone shows one or the other: the list, or the
  // job with a bar back to the list (no rail, and the list opens over the whole page).
  let peek = $state(false)
  let railEl = $state<HTMLElement>()
  let listEl = $state<HTMLElement>()
  const rail = $derived(layout.small ? single !== null : layout.queueCollapsed || (layout.narrow && single !== null))
  $effect(() => {
    if (!rail) peek = false
  })

  function showList() {
    layout.queueCollapsed = false
    if (layout.narrow && single !== null) peek = true
    tick().then(() => listEl?.querySelector<HTMLInputElement>('input[type="search"]')?.focus())
  }

  function hideList() {
    if (peek) peek = false
    else layout.queueCollapsed = true
    tick().then(() => railEl?.querySelector<HTMLElement>('button')?.focus())
  }

  function outside(e: PointerEvent) {
    const t = e.target as Node
    if (peek && !listEl?.contains(t) && !railEl?.contains(t)) peek = false
  }

  const startJobs = $derived(app.jobs.filter((j) => j.status === 'queued'))

  // --- batch panel ---
  let batchSource = $state<JobDetail | null>(null)
  $effect(() => {
    let current = true
    batchSource = null
    if (selected.length > 1)
      api
        .job(selected[0])
        .then((j) => {
          if (current) batchSource = j
        })
        .catch((e) => {
          if (current) toast.error(e.message)
        })
    return () => {
      current = false
    }
  })

  async function applyEncoder(encoder: EncoderSettings) {
    if (!batchSource) return
    batchSource.spec.encoder = encoder
    await act(async () => {
      const r = await api.apply(selected, { encoder })
      toast.success(
        `Encoder applied to ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''),
      )
    })
  }

  // A template (by name) for the whole batch, from the first job's profile's choices.
  let batchTemplate = $state('')
  const batchTemplates = $derived(batchSource ? app.presetChoices('template', batchSource.profile) : [])
  const picked = $derived(batchTemplates.find((c) => c.name === batchTemplate) ?? batchTemplates[0])
  const batchContainers = $derived(app.profiles.find((p) => p.id === batchSource?.profile)?.containers ?? [])

  async function applyTemplate() {
    if (!picked) return
    const name = picked.name
    const ids = [...selected]
    await act(async () => {
      const r = await api.apply(ids, { template: $state.snapshot(picked.data) })
      toast.success(
        `Template ${name} applied to ${r.updated.length} job(s)` +
          (r.skipped.length ? `, ${r.skipped.length} busy` : ''),
      )
      const fresh = await api.job(ids[0])
      if (selected.length > 1 && selected[0] === ids[0]) batchSource = fresh
    })
  }

  async function applyContainer(container: string) {
    if (!batchSource) return
    batchSource.spec.mux.container = container
    await act(async () => {
      const r = await api.apply(selected, { container })
      const label = batchContainers.find((c) => c.id === container)?.label ?? container
      toast.success(`${label} for ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
    })
  }

  async function applyCrop() {
    if (!batchSource) return
    const crop = batchSource.spec.video.crop
    const ids = [...selected]
    await act(async () => {
      await saves.flush()
      const r = await api.applyCrop(ids, crop)
      const reasons = Object.entries({ ...r.skipped, ...r.failed })
        .map(([id, reason]) => `${app.jobName(id)}: ${reason}`)
        .join('\n')
      const message = `Crop: ${r.updated.length} updated, ${Object.keys(r.skipped).length} skipped, ${Object.keys(r.failed).length} failed`
      if (Object.keys(r.failed).length) toast.error(message, { description: reasons })
      else if (Object.keys(r.skipped).length) toast.warning(message, { description: reasons })
      else toast.success(message)
    })
  }
</script>

<svelte:window
  onpointerdown={outside}
  onpointermove={dragMove}
  onpointerup={dragEnd}
  onpointercancel={dragEnd}
  onkeydown={(e) => {
    if (peek && e.key === 'Escape') {
      hideList()
      e.stopPropagation()
    }
  }}
/>

<div class="relative flex h-full">
  {#if rail && layout.small}
    {#if peek}{@render list('absolute inset-0 z-30 w-full bg-background')}{/if}
  {:else if rail}
    <!-- The list as a rail: one chip per job (its place, coloured by status). -->
    <section
      bind:this={railEl}
      class="flex w-14 shrink-0 flex-col items-center border-r border-border"
      aria-label="Queue rail"
      inert={peek}
    >
      <Tip
        side="right"
        class="my-2"
        text={layout.narrow && single !== null
          ? 'Show the queue list (over the editor: the window is narrow)'
          : 'Show the queue list'}
      >
        <Button variant="ghost" size="icon" onclick={showList} aria-label="Show the queue list" aria-expanded={peek}>
          <PanelLeftOpenIcon />
        </Button>
      </Tip>
      <Tip
        side="right"
        class="pb-1 text-[10px] text-muted-foreground"
        text={`${matching.length} matching jobs of ${app.jobs.length}`}>{matching.length}</Tip
      >
      <div
        data-scroller
        role="group"
        aria-label="Matching jobs"
        class="flex min-h-0 w-full flex-1 flex-col items-center gap-1 overflow-auto border-t border-border py-2 select-none"
      >
        {#each pageJobs as job, i (job.id)}
          <Tip
            side="right"
            class="shrink-0"
            text="{job.name}{job.label ? ` (${job.label})` : ''}: {STATUS_LABEL[job.status]}{job.issue
              ? ` (${job.issue})`
              : ''}"
          >
            <button
              data-job={job.id}
              aria-label={`${job.name}${job.label ? ` (${job.label})` : ''}: ${STATUS_LABEL[job.status]}`}
              aria-pressed={selectedSet.has(job.id)}
              tabindex={job.id === tabStop ? 0 : -1}
              onfocus={() => (cursor = job.id)}
              onkeydown={keys}
              class="relative flex h-9 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border text-xs focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring
              {selectedSet.has(job.id) ? 'border-primary bg-card' : 'hover:bg-accent'}
              {STATUS_TONE[job.status]}"
              onpointerdown={(e) => dragStart(e, job.id)}
              onclick={(e) => click(e, job.id)}
            >
              {currentPage * QUEUE_PAGE_SIZE + i + 1}
              {#if LIVE.includes(job.status) && job.progress}
                <span class="absolute inset-x-0 bottom-0 h-1 bg-muted">
                  <span class="block h-full bg-info" style="width:{job.progress.overall * 100}%"></span>
                </span>
              {/if}
            </button>
          </Tip>
        {/each}
      </div>
      {#if matching.length > QUEUE_PAGE_SIZE}
        <Button
          variant="ghost"
          size="icon"
          disabled={currentPage === 0}
          aria-label="Previous queue page"
          onclick={() => changePage(currentPage - 1)}><ArrowUpIcon /></Button
        >
        <Button
          variant="ghost"
          size="icon"
          disabled={(currentPage + 1) * QUEUE_PAGE_SIZE >= matching.length}
          aria-label="Next queue page"
          onclick={() => changePage(currentPage + 1)}><ArrowDownIcon /></Button
        >
      {/if}
    </section>
    {#if peek}{@render list(
        'absolute inset-y-0 left-14 z-30 w-[28rem] max-w-[calc(100%-3.5rem)] bg-background shadow-xl',
      )}{/if}
  {:else}
    {@render list('w-[28rem] max-w-full shrink-0 max-sm:w-full')}
  {/if}

  {#snippet list(cls: string)}
    <section
      bind:this={listEl}
      class="flex min-w-0 flex-col overflow-y-auto border-r border-border {cls}"
      aria-label="Queue list"
    >
      <div class="flex shrink-0 flex-wrap items-center gap-1 border-b border-border p-2">
        <Tip
          class={peek ? '' : 'max-sm:hidden'}
          text={peek ? 'Hide the list (Esc)' : 'Collapse the list, for more room'}
        >
          <Button
            variant="ghost"
            size="icon"
            onclick={hideList}
            aria-label={peek ? 'Hide the queue list' : 'Collapse the queue list'}
          >
            <PanelLeftCloseIcon />
          </Button>
        </Tip>
        {#if app.queue.running}
          <Tip text="Finish the current job, then stop">
            <Button variant="outline" onclick={() => act(api.stop)}>
              <ListEndIcon />{app.queue.stop_after_current ? 'Stopping…' : 'Stop after current'}
            </Button>
          </Tip>
          <Tip text="Cancel the running job">
            <Button variant="outline" onclick={() => act(api.cancel)}><SquareIcon />Cancel</Button>
          </Tip>
        {:else}
          <Tip
            text={startJobs.length
              ? `Run the ${startJobs.length} queued jobs, in queue order`
              : 'Nothing is queued: tick the jobs to run (or Queue a selection)'}
          >
            <Button disabled={starting || !startJobs.length} onclick={() => act(() => run())}>
              <PlayIcon />Start queue ({startJobs.length})
            </Button>
          </Tip>
        {/if}
        {#if working || app.queue.paused}
          {#if app.queue.paused}
            <Tip text="Go on with the paused tools">
              <Button onclick={() => act(api.resume)}><PlayIcon /><span class="max-sm:sr-only">Resume</span></Button>
            </Tip>
          {:else}
            <Tip text="Suspend the running job's tools and the index lane's (they use no CPU until resumed)">
              <Button variant="outline" onclick={() => act(api.pause)}>
                <PauseIcon /><span class="max-sm:sr-only">Pause</span>
              </Button>
            </Tip>
          {/if}
          <DropdownMenu.Root>
            <Tip text="Process priority of the running tools, for the rest of their run (Settings has the default)">
              <DropdownMenu.Trigger disabled={!working}>
                {#snippet child({ props })}
                  <Button {...props} variant="ghost" size="icon" aria-label="Process priority"><GaugeIcon /></Button>
                {/snippet}
              </DropdownMenu.Trigger>
            </Tip>
            <DropdownMenu.Content align="start" class="w-48">
              <DropdownMenu.Label>Priority, this run</DropdownMenu.Label>
              <DropdownMenu.RadioGroup
                value={app.queue.priority ?? ''}
                onValueChange={(v) => act(() => api.priority((v || null) as Priority | null))}
              >
                <DropdownMenu.RadioItem value="">As in Settings</DropdownMenu.RadioItem>
                {#each Object.entries(PRIORITY_LABEL) as [value, label] (value)}
                  <DropdownMenu.RadioItem {value}>{label}</DropdownMenu.RadioItem>
                {/each}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        {/if}
        <Tip class={selected.length ? '' : 'max-sm:hidden'} text="Queue the selected jobs and start">
          <Button variant="outline" disabled={starting || !selected.length} onclick={() => act(() => run(selected))}>
            <PlayIcon />Run selected ({selected.length})
          </Button>
        </Tip>
        {#if queueableSelected.length}
          <Tip text="Queue the selected jobs: locked until they run, and the queue runs them (a running queue too)">
            <Button variant="outline" onclick={() => act(() => queue())}>Queue ({queueableSelected.length})</Button>
          </Tip>
        {/if}
        {#if waitingSelected.length}
          <Tip text="Take the selected jobs out of the run, to edit them; their settings and files stay">
            <Button variant="outline" onclick={() => act(() => unqueue())}>Unqueue ({waitingSelected.length})</Button>
          </Tip>
        {/if}
        {#if indexing}
          <Tip text="Stop indexing: cancel the job being indexed (or test encoded) and the ones waiting">
            <Button variant="outline" onclick={() => act(() => app.stopIndexing())}>
              <DatabaseXIcon /><span class="max-sm:sr-only">Stop indexing</span>
            </Button>
          </Tip>
        {/if}
        <span class="flex-1"></span>
        <Tip text={`Select all ${matching.length} matching jobs across pages (Ctrl+A in the list)`}>
          <Button
            variant="ghost"
            size="icon"
            disabled={!matching.length}
            onclick={selectMatching}
            aria-label="Select matching jobs"><ListChecksIcon /></Button
          >
        </Tip>
        <Tip
          text="Index {selected.length
            ? 'the selected jobs'
            : 'every job'} not indexed yet ({toIndex}): one at a time, each gets its work folder, script and source index, and nothing else, so its video opens at once (runs next to the queue)"
        >
          <Button
            variant="ghost"
            size="icon"
            disabled={!toIndex}
            onclick={() => index(indexTarget)}
            aria-label={selected.length ? 'Index the selected jobs' : 'Index every job not indexed yet'}
            ><DatabaseZapIcon /></Button
          >
        </Tip>
        <Tip text="Move up in the full queue">
          <Button
            variant="ghost"
            size="icon"
            disabled={!selected.length}
            onclick={() => move(-1)}
            aria-label="Move selected jobs up"><ArrowUpIcon /></Button
          >
        </Tip>
        <Tip text="Move down in the full queue">
          <Button
            variant="ghost"
            size="icon"
            disabled={!selected.length}
            onclick={() => move(1)}
            aria-label="Move selected jobs down"><ArrowDownIcon /></Button
          >
        </Tip>
        <Tip
          text="Duplicate: a copy of each selected job right after it, with a label of its own, to change a few settings for a second output"
        >
          <Button
            variant="ghost"
            size="icon"
            disabled={!selected.length}
            onclick={duplicate}
            aria-label="Duplicate selected jobs"><CopyPlusIcon /></Button
          >
        </Tip>
        <Tip text="Probe again">
          <Button
            variant="ghost"
            size="icon"
            disabled={!selected.length}
            onclick={() => act(() => api.reprobe(selected))}
            aria-label="Probe selected jobs again"
          >
            <RefreshCwIcon />
          </Button>
        </Tip>
        <DropdownMenu.Root>
          <Tip text="Remove">
            <DropdownMenu.Trigger disabled={!selected.length}>
              {#snippet child({ props })}
                <Button {...props} variant="ghost" size="icon" class="hover:text-destructive" aria-label="Remove"
                  ><Trash2Icon /></Button
                >
              {/snippet}
            </DropdownMenu.Trigger>
          </Tip>
          <DropdownMenu.Content align="end" class="w-auto">
            <DropdownMenu.Item onSelect={() => remove()}>Remove from the queue</DropdownMenu.Item>
            <Tip class="block" side="left" text="Review the work folders before deleting their intermediate files">
              <DropdownMenu.Item onSelect={confirmRemoval}>Remove and delete work folders</DropdownMenu.Item>
            </Tip>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>

      <div class="shrink-0 space-y-2 border-b border-border p-2">
        <Input
          type="search"
          aria-label="Search jobs by name or source path"
          placeholder="Search name or source path"
          value={query}
          oninput={(e) => {
            query = e.currentTarget.value
            filterChanged()
          }}
        />
        <div class="flex flex-wrap items-center gap-2">
          <NativeSelect
            aria-label="Filter jobs by status"
            value={status}
            onchange={(e) => {
              status = e.currentTarget.value as Status | ''
              filterChanged()
            }}
          >
            <option value="">All statuses ({searched.length})</option>
            {#each Object.entries(STATUS_LABEL) as [value, label] (value)}
              <option {value}>{label} ({counts.get(value as Status) ?? 0})</option>
            {/each}
          </NativeSelect>
          {#if query || status}<Button variant="ghost" size="sm" onclick={clearFilters}>Clear filters</Button>{/if}
        </div>
        <p role="status" class="text-xs text-muted-foreground">
          {matching.length} of {app.jobs.length} jobs match. {selected.length} selected{hiddenSelected
            ? ` (${hiddenSelected} hidden by filters)`
            : ''}.
        </p>
        {#if selected.length}<Button variant="outline" size="sm" onclick={clearSelection}>Clear selection</Button>{/if}
        <p class="text-xs text-muted-foreground">
          Ticked jobs are queued: locked, and the queue runs them. Selected actions include selections on other pages
          and hidden by filters. Index uses {selected.length
            ? `${selected.length} selected jobs`
            : `all ${app.jobs.length} jobs`}.
        </p>
        <p id="queue-keys" class="text-xs text-muted-foreground pointer-coarse:hidden">
          Arrows/Home/End navigate; Shift extends selection; Ctrl/Cmd+A selects matching jobs across pages.
        </p>
      </div>

      {#if saveError}
        <div role="alert" class="space-y-2 border-b p-3 text-sm text-destructive">
          <p>Changes are not saved: {saveError}. Start is blocked until resolved.</p>
          <Button size="sm" onclick={() => act(() => saves.retry())}>Retry saves</Button>
          <Button size="sm" variant="outline" onclick={() => saves.discard()}>Discard unsaved changes</Button>
        </div>
      {/if}
      <div
        data-scroller
        role="group"
        aria-label="Matching jobs"
        aria-describedby="queue-keys"
        class="min-h-24 flex-1 overflow-auto select-none"
      >
        {#each pageJobs as job (job.id)}
          {@const queued = job.status === 'queued' || job.status === 'running'}
          <div
            class="flex border-b border-border/60 {selectedSet.has(job.id)
              ? 'bg-card shadow-[inset_3px_0_0_var(--primary)]'
              : 'hover:bg-accent'}"
          >
            <div class="flex shrink-0 items-start pt-2.5 pl-3">
              <!-- Out of the tab order (the list is one stop): the keyboard queues a selection with Queue (N). -->
              <Tip
                text={job.status === 'running'
                  ? 'Running'
                  : queued
                    ? 'Queued: locked, the queue runs it (untick to edit)'
                    : queueable(job.status)
                      ? 'Tick to queue: locks it, and the queue runs it'
                      : `Can't be queued while ${STATUS_LABEL[job.status].toLowerCase()}`}
              >
                <Checkbox
                  checked={queued}
                  disabled={job.status === 'running' || (!queued && !queueable(job.status))}
                  onCheckedChange={(on) => act(() => (on ? queue([job.id]) : unqueue([job.id])))}
                  tabindex={-1}
                  aria-label={`Queued: ${job.name}${job.label ? ` (${job.label})` : ''}`}
                />
              </Tip>
            </div>
            <button
              data-job={job.id}
              aria-pressed={selectedSet.has(job.id)}
              tabindex={job.id === tabStop ? 0 : -1}
              onfocus={() => (cursor = job.id)}
              onkeydown={keys}
              class="block min-w-0 flex-1 py-2 pr-3 pl-2.5 text-left focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
              onpointerdown={(e) => dragStart(e, job.id)}
              onclick={(e) => click(e, job.id)}
            >
              <div class="flex items-center gap-2">
                <Tip class="block truncate font-medium" text={job.source}>{job.name}</Tip>
                {#if job.label}<Tip class="shrink-0" text="Label"
                    ><Badge variant="outline" class="px-1.5 py-0 text-xs font-normal">{job.label}</Badge></Tip
                  >{/if}
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
                  <Tip class="ml-auto shrink-0 items-center" text="Indexed: the video opens at once"
                    ><DatabaseCheckIcon class="size-3.5" /></Tip
                  >
                {/if}
              </div>
              {#if LIVE.includes(job.status) && job.progress}
                <div class="mt-1.5 flex items-center gap-2 text-xs text-info">
                  <div class="h-1 flex-1 overflow-hidden rounded bg-muted">
                    <div class="h-full bg-info" style="width:{job.progress.overall * 100}%"></div>
                  </div>
                  {percent(job.progress.overall)}
                </div>
                <div class="flex gap-2 text-xs text-muted-foreground">
                  <span class="truncate">{job.progress.step}</span>
                  <Tip
                    class="ml-auto shrink-0 tabular-nums"
                    text="Encoder speed · time since the run started · the job's time left (a guess from its pace so far)"
                    >{progressTimes(job.progress)}</Tip
                  >
                </div>
              {:else if job.issue}
                <div
                  class="mt-0.5 truncate text-xs {['blocked', 'error', 'failed', 'invalid'].includes(job.status)
                    ? 'text-destructive'
                    : 'text-warning'}"
                >
                  {job.issue}
                </div>
              {/if}
              {#if job.index_held && job.status === 'index-queued'}
                <Tip class="mt-0.5 block truncate text-xs text-muted-foreground" text="Settings, Batch indexing">
                  Waits: an encode is reading this disk
                </Tip>
              {/if}
              {#if job.index_error && job.status !== 'indexing'}
                <Tip class="mt-0.5 block truncate text-xs text-warning" text={job.index_error}>
                  Index failed: {job.index_error}
                </Tip>
              {/if}
            </button>
          </div>
        {:else}
          <div class="p-6 text-center text-muted-foreground">
            {#if app.jobs.length}
              No jobs match these filters. <Button variant="link" class="h-auto p-0" onclick={clearFilters}
                >Clear filters</Button
              >.
            {:else}
              No jobs yet. <Button variant="link" class="h-auto p-0" onclick={() => router.go('new')}>Add some</Button>.
            {/if}
          </div>
        {/each}
      </div>
      <div class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t p-2 text-xs">
        <span
          >Showing {matching.length ? currentPage * QUEUE_PAGE_SIZE + 1 : 0}–{Math.min(
            (currentPage + 1) * QUEUE_PAGE_SIZE,
            matching.length,
          )} of {matching.length}</span
        >
        <div class="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            disabled={currentPage === 0}
            aria-label="Previous queue page"
            onclick={() => changePage(currentPage - 1)}>Previous</Button
          >
          <Button
            variant="outline"
            size="sm"
            disabled={(currentPage + 1) * QUEUE_PAGE_SIZE >= matching.length}
            aria-label="Next queue page"
            onclick={() => changePage(currentPage + 1)}>Next</Button
          >
        </div>
      </div>
    </section>
  {/snippet}

  <section
    class="flex min-w-0 flex-1 flex-col {layout.small && !rail ? 'hidden' : ''}"
    inert={peek}
    aria-label="Job settings"
  >
    {#if layout.small && rail}
      <div class="shrink-0 border-b border-border px-1 py-1">
        <Button variant="ghost" size="sm" onclick={showList} aria-label="Show the queue list" aria-expanded={peek}>
          <ChevronLeftIcon />Queue list
        </Button>
      </div>
    {/if}
    <div class="min-h-0 flex-1 overflow-auto">
      {#if single}
        {#key single}<JobEditor jobId={single} />{/key}
      {:else if selected.length > 1}
        <div class="max-w-3xl space-y-6 p-6">
          <h2 class="text-lg font-semibold">{selected.length} jobs selected</h2>
          <p class="text-sm text-muted-foreground">
            Settings here apply to every selected job (queued or running ones are skipped). Starting values are the
            first job's. Audio and subtitle choices stay per job unless the template sets them.
          </p>
          <div class="flex flex-wrap items-center gap-3">
            <Button variant="outline" disabled={!batchToIndex} onclick={() => index(selected)}>
              <DatabaseZapIcon />{batchToIndex
                ? `Index ${batchToIndex} job${batchToIndex > 1 ? 's' : ''}`
                : 'All indexed'}
            </Button>
            <span class="text-sm text-muted-foreground">
              One at a time: the work folder, script and source index, nothing else. Their video then opens at once, and
              the encode reuses the index.{batchToIndex && batchToIndex < selected.length
                ? ` ${selected.length - batchToIndex} already indexed.`
                : ''}
            </span>
          </div>
          {#if batchSource}
            <Card.Root class="gap-2 p-4">
              <div class="flex flex-wrap items-center gap-3">
                <span class="text-sm">Template</span>
                <NativeSelect
                  aria-label="Template for the selected jobs"
                  value={picked?.name ?? ''}
                  onchange={(e) => (batchTemplate = e.currentTarget.value)}
                >
                  {#each batchTemplates as c (`${c.builtin}:${c.name}`)}<option value={c.name}>{c.name}</option>{/each}
                </NativeSelect>
                <Button class="ml-auto" onclick={applyTemplate} disabled={!picked}
                  ><LayoutTemplateIcon />Apply to {selected.length} jobs</Button
                >
              </div>
              <p class="text-xs text-muted-foreground">
                Sets video, encoder, container, AutoQPF{picked?.data.audio ? ', audio' : ''}{picked?.data.crop_mode ===
                'auto'
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
                  onValueChange={(v) => v && applyContainer(v)}
                >
                  {#each batchContainers as c (c.id)}
                    <ToggleGroup.Item
                      value={c.id}
                      class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                      >{c.label}</ToggleGroup.Item
                    >
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
                Crop from {batchSource.name}: {batchSource.spec.video.crop.left}/{batchSource.spec.video.crop
                  .top}/{batchSource.spec.video.crop.right}/{batchSource.spec.video.crop.bottom}
              </span>
              <Button variant="outline" class="ml-auto" onclick={applyCrop}><CropIcon />Apply this crop to all</Button>
            </Card.Root>
          {/if}
        </div>
      {:else}
        <div class="flex h-full items-center justify-center text-muted-foreground">Select a job to edit it.</div>
      {/if}
    </div>
  </section>
</div>

<ReuseDialog bind:open={reuseOpen} jobs={reuseJobs} onstart={startReusing} />

<Dialog.Root
  open={removal !== null}
  onOpenChange={(open) => {
    if (!open && !removing) removal = null
  }}
>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>Remove jobs and delete working files?</Dialog.Title>
      <Dialog.Description
        >Records and logs are archived first. Indexes, scripts and intermediate encodes are permanently deleted; a rerun
        must recreate them. Finished output files are kept.</Dialog.Description
      >
    </Dialog.Header>
    <div class="max-h-64 space-y-3 overflow-auto text-sm">
      {#each removal?.folders ?? [] as folder (folder.id)}
        <div>
          <code class="break-all">{folder.path}</code>
          <div class="text-muted-foreground">
            {folder.bytes === null ? 'Size unavailable' : bytes(folder.bytes)}{folder.error ? ` · ${folder.error}` : ''}
          </div>
        </div>
      {/each}
    </div>
    <Dialog.Footer>
      <Button variant="outline" disabled={removing} onclick={() => (removal = null)}>Cancel</Button>
      <Button
        variant="destructive"
        disabled={removing}
        onclick={() => remove(true, removal?.folders.map((f) => f.id) ?? [])}
        >{removing ? 'Removing…' : 'Remove and delete'}</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
