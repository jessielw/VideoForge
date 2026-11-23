<script lang="ts">
  // The queue: jobs on the left (click, Ctrl/Shift-click, drag across rows, Shift+arrows or Ctrl+A to
  // select several), the selected job's editor on the right, or a batch panel when several are selected.
  import EncoderPanel from '../components/EncoderPanel.svelte'
  import FileBrowser from '../components/FileBrowser.svelte'
  import OutputFolderMenu from '../components/OutputFolderMenu.svelte'
  import PathSlot from '../components/PathSlot.svelte'
  import { tick, onDestroy } from 'svelte'
  import { Input } from '$lib/components/ui/input'
  import {
    defaultGroupName,
    dropTarget,
    matchingJobs,
    moveSelection,
    queuePage,
    queueRange,
    queueRows,
    queueSlots,
    queueable,
    slotPage,
    sharedFacts,
    QUEUE_PAGE_SIZE,
    movedQueue,
    sameQueue,
    type Dragged,
    type Drop,
    type QueueRow,
  } from '../lib/queueView'
  import { saves } from '../lib/saves'
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import CircleXIcon from '@lucide/svelte/icons/circle-x'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left'
  import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
  import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
  import FolderPlusIcon from '@lucide/svelte/icons/folder-plus'
  import GripVerticalIcon from '@lucide/svelte/icons/grip-vertical'
  import CopyPlusIcon from '@lucide/svelte/icons/copy-plus'
  import CropIcon from '@lucide/svelte/icons/crop'
  import DatabaseCheckIcon from '@lucide/svelte/icons/database-check'
  import DatabaseXIcon from '@lucide/svelte/icons/database-x'
  import DatabaseZapIcon from '@lucide/svelte/icons/database-zap'
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import GaugeIcon from '@lucide/svelte/icons/gauge'
  import LayoutTemplateIcon from '@lucide/svelte/icons/layout-template'
  import ListChecksIcon from '@lucide/svelte/icons/list-checks'
  import ListEndIcon from '@lucide/svelte/icons/list-end'
  import LockIcon from '@lucide/svelte/icons/lock'
  import PanelLeftCloseIcon from '@lucide/svelte/icons/panel-left-close'
  import PanelLeftOpenIcon from '@lucide/svelte/icons/panel-left-open'
  import PauseIcon from '@lucide/svelte/icons/pause'
  import PlayIcon from '@lucide/svelte/icons/play'
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
  import IssueCounts from '../components/IssueCounts.svelte'
  import JobEditor from '../components/JobEditor.svelte'
  import Kbd from '../components/Kbd.svelte'
  import ReuseDialog from '../components/ReuseDialog.svelte'
  import Tip from '../components/Tip.svelte'
  import { api } from '../lib/api'
  import { pastedPaths, pathDrop } from '../lib/dropPaths.svelte'
  import {
    bytes,
    issueCounts,
    jobFacts,
    percent,
    plural,
    PRIORITY_LABEL,
    progressTimes,
    STATUS_LABEL,
    STATUS_TONE,
    type Fact,
  } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { layout } from '../lib/layout.svelte'
  import { reuseQuestion } from '../lib/reuse.svelte'
  import { app } from '../lib/state.svelte'
  import type { EncoderSettings, JobDetail, JobSummary, Priority, Status } from '../lib/types'

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

  // Queue groups (a batch shown together, e.g. a season): which are collapsed is this browser's.
  const COLLAPSED_KEY = 'videoforge.queue.collapsed'
  let collapsed = $state(
    new Set<string>(
      (() => {
        try {
          const saved = JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? '[]')
          return Array.isArray(saved) ? saved.filter((g) => typeof g === 'string') : []
        } catch {
          return []
        }
      })(),
    ),
  )
  function setCollapsed(group: string, shut: boolean) {
    const next = new Set([...collapsed].filter((g) => app.jobs.some((j) => j.group === g)))
    if (shut) next.add(group)
    else next.delete(group)
    collapsed = next
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
    } catch {
      // private window or blocked storage: it's only remembered until the page reloads
    }
  }

  // A page is QUEUE_PAGE_SIZE slots: a matching job each, a collapsed group one for all its jobs.
  const slots = $derived(queueSlots(matching, collapsed))
  const currentPage = $derived(queuePage(slots.length, page))
  const lastPage = $derived((currentPage + 1) * QUEUE_PAGE_SIZE >= slots.length)
  const rows = $derived(queueRows(slots, currentPage, app.jobs))
  const pageJobs = $derived(rows.flatMap((r) => (r.kind === 'job' ? [r.job] : [])))
  const visibleIds = $derived(slots.flatMap((s) => (s.kind === 'job' ? [s.job.id] : []))) // what arrows go through
  const place = $derived(new Map(matchingIds.map((id, i) => [id, i + 1]))) // a rail chip's number
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
    page = queuePage(slots.length, next)
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
      toast.success(`Unqueued ${plural(ids.length, 'job')}`, {
        description: 'You can edit them again, and the queue skips them.',
      })
  }

  // Queued: locked (read-only), and the queue runs it, even one already running. Edits still saving go first.
  // A running queue takes it at once, so the reuse question is asked here, not on Start.
  async function queue(ids = [...queueableSelected]) {
    await saves.flush()
    const reuse = await reuseQuestion.ask(ids, 'queue')
    if (!reuse) return
    const { enqueued } = await api.enqueue(ids, reuse)
    await app.refreshJobs()
    if (enqueued.length < ids.length) {
      toast.warning(`Queued ${enqueued.length} of ${plural(ids.length, 'job')}`, {
        description:
          "The others can't be queued while VideoForge reads their tracks, indexes them, detects their crop or runs a test encode or CRF search, or while they're blocked.",
      })
    } else if (ids.length > 1)
      toast.success(`Queued ${ids.length} jobs`, {
        description:
          "You can't edit them while they're queued. Start queue runs them, or a running queue picks them up in their turn.",
      })
  }

  // The routed job is selected once it's in the list (the prune below would undo it otherwise).
  $effect(() => {
    const id = router.jobId
    const job = id ? app.jobs.find((j) => j.id === id) : undefined
    if (id && job && !selected.includes(id)) {
      selected = [id]
      query = ''
      status = ''
      if (job.group && collapsed.has(job.group)) setCollapsed(job.group, false) // its row shows
      page = Math.max(0, slotPage(queueSlots(app.jobs, collapsed), id))
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
    if (!matchingIds.length) return
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault()
      select(matchingIds)
      return
    }
    const ids = visibleIds // not a collapsed group's (Shift still takes them, from the matching jobs)
    if (!ids.length) return
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
    page = Math.max(0, slotPage(slots, id))
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
      const reuse = await reuseQuestion.ask(ids, 'start')
      if (!reuse) return
      await saves.flush()
      await api.start(ids, Object.keys(reuse).length ? reuse : undefined)
    } finally {
      starting = false
    }
  }

  // A job in a group moves within it (drag its grip to take it out); a whole group selected moves as one.
  async function move(step: -1 | 1) {
    await act(() => api.reorder(moveSelection(app.jobs, new Set(selected), step)))
  }

  // --- queue groups: drag a grip to move jobs (into or out of a group) or a whole group -------------------
  let reordering = $state<{ dragged: Dragged; drop: Drop | null } | null>(null)
  let pointer: { x: number; y: number; scroller: HTMLElement } | null = null

  function gripStart(e: PointerEvent, dragged: Dragged) {
    const scroller = (e.currentTarget as HTMLElement).closest<HTMLElement>('[data-scroller]')
    if (e.button !== 0 || !scroller) return
    e.preventDefault()
    e.stopPropagation()
    pointer = { x: e.clientX, y: e.clientY, scroller }
    reordering = { dragged, drop: null }
    requestAnimationFrame(gripTick)
  }

  // A job's grip moves the selection when the job is in it, else just the job.
  function jobsFor(id: string): Dragged {
    const ids = selectedSet.has(id) ? app.jobs.filter((j) => selectedSet.has(j.id)).map((j) => j.id) : [id]
    return { kind: 'jobs', ids }
  }

  function gripTick() {
    if (!reordering || !pointer) return
    const { scroller } = pointer
    const r = scroller.getBoundingClientRect()
    const edge = 32
    if (pointer.y < r.top + edge) scroller.scrollTop -= Math.ceil((r.top + edge - pointer.y) / 3)
    else if (pointer.y > r.bottom - edge) scroller.scrollTop += Math.ceil((pointer.y - r.bottom + edge) / 3)
    const x = Math.min(Math.max(pointer.x, r.left + 2), r.right - 2)
    const y = Math.min(Math.max(pointer.y, r.top + 2), r.bottom - 2)
    const el = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-row]')
    let index = -1
    let at = 0
    if (el && scroller.contains(el)) {
      index = Number(el.dataset.row)
      const box = el.getBoundingClientRect()
      at = (y - box.top) / Math.max(box.height, 1)
    } else {
      const last = scroller.querySelector<HTMLElement>(`[data-row="${rows.length - 1}"]`)
      if (last && y > last.getBoundingClientRect().bottom)
        [index, at] = lastPage ? [rows.length, 0] : [rows.length - 1, 1]
    }
    const drop = index < 0 ? null : dropTarget(rows, index, at, app.jobs, reordering.dragged)
    // A place that changes nothing gets no line (and the drop does nothing).
    const ids = draggedIds(reordering.dragged)
    reordering.drop = drop && !sameQueue(movedQueue(app.jobs, ids, drop.before, drop.group), app.jobs) ? drop : null
    requestAnimationFrame(gripTick)
  }

  const draggedIds = (dragged: Dragged) =>
    dragged.kind === 'jobs' ? dragged.ids : app.jobs.filter((j) => j.group === dragged.group).map((j) => j.id)
  // A grab cursor wherever the pointer goes while it drags.
  $effect(() => {
    if (!reordering) return
    document.documentElement.classList.add('cursor-grabbing')
    return () => document.documentElement.classList.remove('cursor-grabbing')
  })
  // The rows being dragged, dimmed while they move.
  const moving = $derived(new Set(reordering ? draggedIds(reordering.dragged) : []))

  async function gripEnd(cancel = false) {
    const done = reordering
    reordering = null
    pointer = null
    if (cancel || !done?.drop) return
    const { dragged, drop } = done
    await moveJobs(draggedIds(dragged), drop.before, drop.group)
  }
  onDestroy(() => gripEnd(true))

  async function moveJobs(ids: string[], before: string | null, group: string) {
    await act(async () => {
      await api.move(ids, before, group)
      await app.refreshJobs()
    })
  }

  // The keyboard's way into or out of a group (the header's menu): the selected jobs go to its end, or out
  // of it, just after it.
  const afterGroup = (group: string, moving: string[]) => {
    const last = app.jobs.findLastIndex((j) => j.group === group && !moving.includes(j.id))
    return app.jobs.slice(last + 1).find((j) => !moving.includes(j.id))?.id ?? null
  }
  const moveToGroup = (ids: string[], group: string, into: boolean) =>
    moveJobs(ids, afterGroup(group, ids), into ? group : '')
  const selectedOutside = (group: string) => app.jobs.filter((j) => selectedSet.has(j.id) && j.group !== group)
  const selectedInside = (group: string) => app.jobs.filter((j) => selectedSet.has(j.id) && j.group === group)

  const groupDone = (row: QueueRow & { kind: 'group' }) => row.members.filter((j) => j.status === 'done').length
  const groupFailed = (row: QueueRow & { kind: 'group' }) =>
    row.members.filter((j) => ['failed', 'invalid', 'error'].includes(j.status)).length
  // The header's counts: its jobs (or how many match), then how many are done and failed, when any are.
  const groupCounts = (row: QueueRow & { kind: 'group' }, done: number, failed: number) => {
    const n = row.members.length
    const parts: { text: string; tone: string }[] = []
    if (row.matching.length < n) parts.push({ text: `${row.matching.length} of ${n} match`, tone: '' })
    // The default name is the count, so the count isn't said twice.
    else if (row.name !== `${n} jobs`) parts.push({ text: plural(n, 'job'), tone: '' })
    if (done) parts.push({ text: done === n ? 'all done' : `${done} done`, tone: done === n ? 'text-success' : '' })
    if (failed) parts.push({ text: `${failed} failed`, tone: 'text-destructive' })
    return parts
  }
  // The facts each group's jobs share: its header shows them once, and its rows leave them out.
  const sharedByGroup = $derived.by(() => {
    const members = new Map<string, JobSummary[]>()
    for (const j of app.jobs) if (j.group) members.set(j.group, [...(members.get(j.group) ?? []), j])
    return new Map([...members].map(([group, jobs]) => [group, sharedFacts(jobs.map(jobFacts))]))
  })
  // A collapsed group whose jobs are all selected shows as selected: its rows, which would, are hidden.
  const groupSelected = (row: QueueRow & { kind: 'group' }) =>
    row.collapsed && row.matching.length > 0 && row.matching.every((j) => selectedSet.has(j.id))
  const groupQueued = (row: QueueRow & { kind: 'group' }) =>
    row.members.filter((j) => j.status === 'queued' || j.status === 'running')
  const groupProgress = (row: QueueRow & { kind: 'group' }) => {
    const live = row.members.filter((j) => LIVE.includes(j.status) && j.progress)
    if (!live.length) return null
    return (groupDone(row) + live.reduce((sum, j) => sum + (j.progress?.overall ?? 0), 0)) / row.members.length
  }

  function selectGroup(row: QueueRow & { kind: 'group' }) {
    const ids = row.matching.map((j) => j.id)
    anchor = ids[0] ?? null
    select(ids)
  }

  // Tick: queue every job in it that can be; untick: unqueue the queued ones.
  async function queueGroup(row: QueueRow & { kind: 'group' }, on: boolean) {
    if (on) await queue(row.members.filter((j) => queueable(j.status)).map((j) => j.id))
    else await unqueue(row.members.filter((j) => j.status === 'queued').map((j) => j.id))
  }

  // Group selected (new), or a group's Rename: the name, in a dialog.
  let naming = $state<{ group: string | null; name: string } | null>(null)
  function startGroup() {
    naming = { group: null, name: defaultGroupName(app.jobs.filter((j) => selectedSet.has(j.id)).map((j) => j.source)) }
  }
  async function saveName() {
    const n = naming
    if (!n || !n.name.trim()) return
    await act(async () => {
      if (n.group) await api.renameGroup(n.group, n.name)
      else {
        const { group } = await api.group([...selected], n.name)
        setCollapsed(group, false)
      }
      await app.refreshJobs()
      naming = null
    })
  }
  async function ungroup(group: string) {
    await act(async () => {
      await api.ungroup(group)
      await app.refreshJobs()
    })
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

  // Stop the running job once its video's pass 1 is done (status paused: VideoForge can be closed, and Run goes on
  // with pass 2), or take that back.
  const pausing = $derived(app.jobs.find((j) => j.id === app.queue.current)?.pause_after_pass1 ?? false)
  async function pauseAfterPass1() {
    await act(async () => {
      const { set } = await api.pauseAfterPass1(!pausing)
      if (!set.length) toast.info('Only a 2-pass encode has a pass 1 to stop after')
      await app.refreshJobs()
    })
  }

  // A job's file (its whole setup) goes into its folder in the work folder when it runs; this writes it now.
  async function saveJobFiles() {
    await act(async () => {
      await saves.flush()
      const { saved } = await api.saveJobFiles([...selected])
      const files = Object.values(saved)
      toast.success(files.length === 1 ? 'Job file saved' : `Saved ${files.length} job files`, {
        description: files[0],
      })
    })
  }

  // Jobs added again from job files, exactly as they were (a job file, a job's folder or a <source>_tmp folder).
  let importOpen = $state(false)
  let importPaths = $state<string[]>([])
  let importing = $state(false)
  async function importJobs() {
    const paths = importPaths
    if (!paths.length) return
    importing = true
    await act(async () => {
      const { added, skipped } = await api.importJobs(paths)
      await app.refreshJobs()
      if (added.length) select(added)
      if (added.length) toast.success(added.length === 1 ? 'Job added' : `Added ${added.length} jobs`)
      for (const s of skipped) toast.warning(`Not added: ${s.path}`, { description: s.reason })
      if (added.length && !skipped.length) {
        importOpen = false
        importPaths = []
      }
    })
    importing = false
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
      if (r.removed.length < ids.length)
        toast.info('Jobs that are queued or running, indexing, or running a test encode or CRF search were kept')
      if (!workDirs && r.removed.length)
        toast.success(`Removed ${plural(r.removed.length, 'job')}`, {
          action: {
            label: 'Undo',
            onClick: () =>
              act(async () => {
                const restored = await api.restore(r.removed)
                await app.refreshJobs()
                toast.info(`Restored ${plural(restored.restored.length, 'job')}`)
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
      const out = left
        ? `${left} left out: ${left > 1 ? "they're" : "it's"} queued or running, already indexing or waiting to, running a test encode or CRF search, or using an existing encode.`
        : ''
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
  const DV7_NOTE =
    "Dolby Vision profile 7. Set dovi_tool in Settings › Tools so VideoForge can read whether its enhancement layer is FEL or MEL, which decides how it's encoded."
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
  const rail = $derived(
    layout.small ? single !== null : layout.queueCollapsed || (layout.railNarrow && single !== null),
  )
  $effect(() => {
    if (!rail) peek = false
  })
  $effect(() => {
    layout.jobOpen = single !== null
    return () => (layout.jobOpen = false)
  })

  function showList() {
    layout.queueCollapsed = false
    if (layout.railNarrow && single !== null) peek = true
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
        `Encoder applied to ${plural(r.updated.length, 'job')}` +
          (r.skipped.length ? `, ${r.skipped.length} busy` : ''),
      )
    })
  }

  // A template (by name) for the whole batch, from the first job's rule set's choices.
  let batchTemplate = $state('')
  const batchTemplates = $derived(batchSource ? app.presetChoices('template', batchSource.rule_set) : [])
  const picked = $derived(batchTemplates.find((c) => c.name === batchTemplate) ?? batchTemplates[0])
  const batchContainers = $derived(app.ruleSets.find((p) => p.id === batchSource?.rule_set)?.containers ?? [])

  async function applyTemplate() {
    if (!picked) return
    const name = picked.name
    const ids = [...selected]
    await act(async () => {
      const r = await api.apply(ids, { template: $state.snapshot(picked.data) })
      toast.success(
        `Template ${name} applied to ${plural(r.updated.length, 'job')}` +
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
      toast.success(
        `${label} for ${plural(r.updated.length, 'job')}` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''),
      )
    })
  }

  // One output folder for the whole batch (null clears it).
  let browsingOutput = $state(false)
  async function applyOutput(path: string | null) {
    if (!batchSource) return
    batchSource.spec.output_dir = path
    await act(async () => {
      const r = await api.apply(selected, { output_dir: path })
      toast.success(
        (path
          ? `Output folder set for ${plural(r.updated.length, 'job')}`
          : `Output folder cleared for ${plural(r.updated.length, 'job')}`) +
          (r.skipped.length ? `, ${r.skipped.length} busy` : ''),
      )
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
  onpointermove={(e) => {
    dragMove(e)
    if (pointer) [pointer.x, pointer.y] = [e.clientX, e.clientY]
  }}
  onpointerup={() => {
    dragEnd()
    if (reordering) void gripEnd()
  }}
  onpointercancel={() => {
    dragEnd()
    if (reordering) void gripEnd(true)
  }}
  onkeydown={(e) => {
    if (reordering && e.key === 'Escape') {
      void gripEnd(true)
      e.stopPropagation()
    } else if (peek && e.key === 'Escape') {
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
        text={layout.railNarrow && single !== null
          ? 'Show the queue list over the editor (the window is narrow)'
          : 'Show the queue list'}
      >
        <Button variant="ghost" size="icon" onclick={showList} aria-label="Show the queue list" aria-expanded={peek}>
          <PanelLeftOpenIcon />
        </Button>
      </Tip>
      <Tip
        side="right"
        class="pb-1 text-xs text-muted-foreground"
        text={`${plural(matching.length, 'matching job')} of ${app.jobs.length}`}>{matching.length}</Tip
      >
      <div
        data-scroller
        role="group"
        aria-label="Matching jobs"
        class="flex min-h-0 w-full flex-1 flex-col items-center gap-1 overflow-auto border-t border-border py-2 select-none"
      >
        {#each rows as row, i (row.kind === 'job' ? row.job.id : `group:${row.group}:${i}`)}
          {#if row.kind === 'group'}
            <!-- A group: a line before its jobs; a collapsed one is one chip for all of them. -->
            <Tip
              side="right"
              class="w-full shrink-0 {i ? 'pt-1' : ''}"
              text="{row.name}: {row.members.length} jobs{row.collapsed ? ' (collapsed)' : ''}"
            >
              <div class="mx-auto h-0.5 w-8 rounded bg-primary/40"></div>
            </Tip>
            {#if row.collapsed}
              <Tip side="right" class="shrink-0" text="Select the {row.matching.length} jobs of {row.name}">
                <button
                  aria-label={`${row.name}: ${row.matching.length} jobs, collapsed. Select them.`}
                  tabindex={-1}
                  class="flex h-9 w-10 shrink-0 items-center justify-center rounded-md border border-dashed text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
                  onclick={() => selectGroup(row)}>+{row.matching.length}</button
                >
              </Tip>
            {/if}
          {:else}
            {@const job = row.job}
            <Tip
              side="right"
              class="shrink-0"
              text="{job.name}{job.label ? ` (${job.label})` : ''}: {STATUS_LABEL[job.status]}{job.issue_counts.block ||
              job.issue_counts.warn
                ? ` (${issueCounts(job.issue_counts).join(', ')})`
                : ''}{row.group ? ` · ${job.group_name}` : ''}"
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
                {place.get(job.id)}
                {#if LIVE.includes(job.status) && job.progress}
                  <span class="absolute inset-x-0 bottom-0 h-1 bg-muted">
                    <span class="block h-full bg-info" style="width:{job.progress.overall * 100}%"></span>
                  </span>
                {/if}
              </button>
            </Tip>
          {/if}
          {#if row.group && rows[i + 1]?.group !== row.group && rows[i + 1]?.kind !== 'group' && (row.kind === 'job' || row.collapsed)}
            <!-- ... and a line after its last one (another group's header draws its own) -->
            <div class="mx-auto h-0.5 w-8 shrink-0 rounded bg-primary/40" aria-hidden="true"></div>
          {/if}
        {/each}
      </div>
      {#if slots.length > QUEUE_PAGE_SIZE}
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
          disabled={lastPage}
          aria-label="Next queue page"
          onclick={() => changePage(currentPage + 1)}><ArrowDownIcon /></Button
        >
      {/if}
    </section>
    {#if peek}{@render list(
        'absolute inset-y-0 left-14 z-30 w-[28rem] max-w-[calc(100%-3.5rem)] bg-background shadow-xl',
      )}{/if}
  {:else}
    <!-- With a job open in a narrow window the list shrinks to make room for the editor. -->
    {@render list(
      `${layout.narrow && single !== null ? 'w-[22.6rem]' : 'w-[28rem]'} max-w-full shrink-0 max-sm:w-full`,
    )}
  {/if}

  {#snippet list(cls: string)}
    <section
      bind:this={listEl}
      class="flex min-w-0 flex-col overflow-y-auto border-r border-border {cls}"
      aria-label="Queue list"
    >
      <!-- Three rows. The first never moves: Start queue and Stop after current share one slot, as wide as the
           longer of the two, so Run selected stays under the pointer when a job starts (a double click on it used to
           land on Cancel). The second shows only while something runs, indexes or is paused. The third acts on the
           selection; Queue and Unqueue end it, so one showing up doesn't wrap the first row and move the list. -->
      {#snippet slotLabel(label: string)}
        <!-- each of the slot's labels in one cell, the others hidden: the slot is as wide as the longest -->
        <span class="inline-grid"
          ><span class="col-start-1 row-start-1">{label}</span
          >{#each [`Start queue (${startJobs.length})`, 'Stop after current', 'Stopping…'] as other (other)}<span
              class="invisible col-start-1 row-start-1"
              aria-hidden="true">{other}</span
            >{/each}</span
        >
      {/snippet}
      <div class="shrink-0 space-y-1 border-b border-border p-2">
        <div class="flex flex-wrap items-center gap-1">
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
                <ListEndIcon />{@render slotLabel(app.queue.stop_after_current ? 'Stopping…' : 'Stop after current')}
              </Button>
            </Tip>
          {:else}
            <Tip
              text={startJobs.length
                ? `Run the ${startJobs.length} queued jobs, in queue order`
                : 'Nothing is queued. Tick the jobs to run, or select some and use Queue.'}
            >
              <Button
                variant={app.queue.paused ? 'outline' : 'default'}
                disabled={starting || !startJobs.length}
                onclick={() => act(() => run())}
              >
                <PlayIcon />{@render slotLabel(`Start queue (${startJobs.length})`)}
              </Button>
            </Tip>
          {/if}
          <Tip class={selected.length ? '' : 'max-sm:hidden'} text="Queue the selected jobs and start">
            <Button variant="outline" disabled={starting || !selected.length} onclick={() => act(() => run(selected))}>
              <PlayIcon />Run selected ({selected.length})
            </Button>
          </Tip>
        </div>
        {#if app.queue.running || working || app.queue.paused || indexing}
          <div class="flex flex-wrap items-center gap-1">
            {#if app.queue.running}
              <Tip text="Cancel the running job">
                <Button variant="outline" onclick={() => act(api.cancel)}><SquareIcon />Cancel</Button>
              </Tip>
              {#if app.queue.current}
                <Tip
                  text={pausing
                    ? 'The job stops after pass 1. Click to cancel that.'
                    : "Stops the running job when its video's pass 1 is done. It keeps what it finished, so you can close VideoForge. Running the job again goes on with pass 2."}
                >
                  <Button variant="outline" class={pausing ? 'bg-muted dark:bg-muted' : ''} onclick={pauseAfterPass1}>
                    <PauseIcon />{pausing ? 'Pausing after pass 1' : 'Pause after pass 1'}
                  </Button>
                </Tip>
              {/if}
            {/if}
            {#if working || app.queue.paused}
              {#if app.queue.paused}
                <Tip text="Resumes the paused tools.">
                  <Button onclick={() => act(api.resume)}><PlayIcon /><span class="max-sm:sr-only">Resume</span></Button
                  >
                </Tip>
              {:else}
                <Tip
                  text="Suspends the running job's tools and any background indexing or test encode. They use no CPU until you resume."
                >
                  <Button variant="outline" onclick={() => act(api.pause)}>
                    <PauseIcon /><span class="max-sm:sr-only">Pause</span>
                  </Button>
                </Tip>
              {/if}
              <DropdownMenu.Root>
                <Tip
                  text="Sets the process priority of the running job, and of any indexing or test encode running now, until each one finishes. Later jobs use the default in Settings › Queue & indexing."
                >
                  <DropdownMenu.Trigger disabled={!working}>
                    {#snippet child({ props })}
                      <Button {...props} variant="ghost" size="icon" aria-label="Process priority"><GaugeIcon /></Button
                      >
                    {/snippet}
                  </DropdownMenu.Trigger>
                </Tip>
                <DropdownMenu.Content align="start" class="w-48">
                  <DropdownMenu.Label>Priority until they finish</DropdownMenu.Label>
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
            {#if indexing}
              <Tip text="Cancels the indexing, test encode or CRF search that's running, and the ones waiting.">
                <Button variant="outline" onclick={() => act(() => app.stopIndexing())}>
                  <DatabaseXIcon /><span class="max-sm:sr-only">Stop indexing</span>
                </Button>
              </Tip>
            {/if}
          </div>
        {/if}
        <div class="flex flex-wrap items-center gap-1">
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
            text="Indexes {selected.length
              ? 'the selected jobs'
              : 'every job'} not indexed yet ({toIndex}), so their preview opens without waiting. Jobs are indexed one at a time in the background, beside the queue. Indexing makes only the work folder, the script and the source index."
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
          <Tip text="Move up in the full queue. A job in a group stays in it; a whole group selected moves as one.">
            <Button
              variant="ghost"
              size="icon"
              disabled={!selected.length}
              onclick={() => move(-1)}
              aria-label="Move selected jobs up"><ArrowUpIcon /></Button
            >
          </Tip>
          <Tip text="Move down in the full queue. A job in a group stays in it; a whole group selected moves as one.">
            <Button
              variant="ghost"
              size="icon"
              disabled={!selected.length}
              onclick={() => move(1)}
              aria-label="Move selected jobs down"><ArrowDownIcon /></Button
            >
          </Tip>
          <Tip
            text="Puts the selected jobs in a new group, shown together and collapsible (out of any group they were in). Drag a job's grip to move it into or out of a group."
          >
            <Button
              variant="ghost"
              size="icon"
              disabled={!selected.length}
              onclick={startGroup}
              aria-label="Group the selected jobs"><FolderPlusIcon /></Button
            >
          </Tip>
          <Tip
            text="Makes a copy of each selected job right after it, with its own label. Use it to make a second output with a few settings changed."
          >
            <Button
              variant="ghost"
              size="icon"
              disabled={!selected.length}
              onclick={duplicate}
              aria-label="Duplicate selected jobs"><CopyPlusIcon /></Button
            >
          </Tip>
          <DropdownMenu.Root>
            <Tip text="More actions">
              <DropdownMenu.Trigger>
                {#snippet child({ props })}
                  <Button {...props} variant="ghost" size="icon" aria-label="More actions"><EllipsisIcon /></Button>
                {/snippet}
              </DropdownMenu.Trigger>
            </Tip>
            <DropdownMenu.Content align="end" class="w-auto">
              <Tip
                class="block"
                side="left"
                text="Saves each selected job's whole setup as a job file in its work folder, so you can add it again later. A run saves one too."
              >
                <DropdownMenu.Item disabled={!selected.length} onSelect={saveJobFiles}>Save job files</DropdownMenu.Item
                >
              </Tip>
              <Tip class="block" side="left" text="Adds each job with the settings it was saved with.">
                <DropdownMenu.Item onSelect={() => (importOpen = true)}>Add jobs from job files…</DropdownMenu.Item>
              </Tip>
              <DropdownMenu.Item disabled={!selected.length} onSelect={() => act(() => api.reprobe(selected))}
                >Read tracks again</DropdownMenu.Item
              >
            </DropdownMenu.Content>
          </DropdownMenu.Root>
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
              <DropdownMenu.Item onSelect={() => remove()}>Remove and keep work folders</DropdownMenu.Item>
              <Tip class="block" side="left" text="Shows the work folders and their sizes before deleting them.">
                <DropdownMenu.Item onSelect={confirmRemoval}>Remove and delete work folders</DropdownMenu.Item>
              </Tip>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
          {#if queueableSelected.length}
            <Tip
              text="Queues the selected jobs, so they can't be edited. Start queue runs them, or a running queue picks them up in their turn."
            >
              <Button variant="outline" onclick={() => act(() => queue())}>Queue ({queueableSelected.length})</Button>
            </Tip>
          {/if}
          {#if waitingSelected.length}
            <Tip text="Takes the selected jobs out of the queue so you can edit them. Their settings and files stay.">
              <Button variant="outline" onclick={() => act(() => unqueue())}>Unqueue ({waitingSelected.length})</Button>
            </Tip>
          {/if}
        </div>
      </div>

      <div class="shrink-0 space-y-2 border-b border-border p-2">
        <Input
          type="search"
          aria-label="Search jobs by name, source path, encoder, resolution or HDR format"
          placeholder="Search name, path, encoder or HDR"
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
        <!-- One row of a set height: Clear selection showing up doesn't move the list (a drag-select under the
             pointer would land on the wrong rows). -->
        <div class="flex min-h-8 items-center gap-2">
          <p role="status" class="min-w-0 flex-1 text-xs text-muted-foreground">
            {matching.length} of {app.jobs.length} jobs match. {selected.length} selected{hiddenSelected
              ? ` (${hiddenSelected} hidden by filters)`
              : ''}.
          </p>
          {#if selected.length}<Button variant="outline" size="sm" class="shrink-0" onclick={clearSelection}
              >Clear selection</Button
            >{/if}
        </div>
        <p class="text-xs text-muted-foreground">
          Actions on the selection include jobs on other pages and jobs hidden by filters. Index uses the selected jobs,
          or every job when none is selected.
        </p>
        <!-- Over the column of checkboxes, which queue and lock a job (clicking a row selects it). Each box has its own
             name, and this caption is read as well. -->
        <Tip
          class="w-fit text-xs text-muted-foreground"
          text="A ticked job is queued and locked, so you can't edit it until you untick it. Start queue runs the queued jobs."
          ><span>Queued</span></Tip
        >
        <!-- for screen readers, as the list's description: the Shortcuts dialog shows the keys -->
        <p id="queue-keys" class="sr-only">
          Arrow keys, <Kbd>Home</Kbd> and <Kbd>End</Kbd> move through the list. <Kbd>Shift</Kbd> extends the selection, and
          <Kbd>Ctrl+A</Kbd> or <Kbd>Cmd+A</Kbd> selects matching jobs on every page.
        </p>
      </div>

      {#if saveError}
        <div role="alert" class="space-y-2 border-b p-3 text-sm text-destructive">
          <p>Changes aren't saved: {saveError}. The queue can't start until you retry or discard them.</p>
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
        {#snippet mark(n: number, error: boolean)}
          {#if n}
            {@const words = issueCounts(error ? { block: n, warn: 0 } : { block: 0, warn: n })[0]}
            <Tip class="items-center" text={words}>
              <span role="img" aria-label={words} class="inline-flex items-center gap-0.5 text-muted-foreground">
                {#if error}<CircleXIcon aria-hidden="true" class="size-3.5 text-destructive" />{:else}<TriangleAlertIcon
                    aria-hidden="true"
                    class="size-3.5 text-warning"
                  />{/if}{n}
              </span>
            </Tip>
          {/if}
        {/snippet}
        <!-- One line that ends in an ellipsis at the list's edge. All of it stays in the DOM and in the tip. The
             tags have no tips of their own (a tip inside this one): the Dolby Vision note is in this one. -->
        {#snippet factsLine(facts: Fact[], margin: string)}
          <Tip
            class="readout {margin} block h-5 truncate text-xs leading-5 text-muted-foreground"
            text={facts.flatMap((f) => f.tags ?? f.text).join(' · ') +
              (facts.some((f) => f.tags?.some((n) => n.endsWith('?'))) ? '\n' + DV7_NOTE : '')}
            >{#each facts as fact, n (fact.key)}{#if n && !fact.tags}{' · '}{/if}{#if fact.tags}{#each fact.tags as name (name)}{' '}<Badge
                    variant="outline"
                    class="inline-flex px-1 py-0 align-middle text-xs font-normal {name.endsWith('?')
                      ? 'border-warning/40 text-warning'
                      : ''}">{name}</Badge
                  >{/each}{:else}<span>{fact.text}</span
                >{/if}{/each}{#if facts.some((f) => f.tags?.some((n) => n.endsWith('?')))}<span class="sr-only"
                >{'. ' + DV7_NOTE}</span
              >{/if}</Tip
          >
        {/snippet}
        {#snippet dropLine(i: number)}
          {#if reordering?.drop && reordering.drop.row === i && reordering.drop.edge !== 'inside'}
            <!-- Indented (from the jobs' names): into the group; full width, with its dot at the edge: outside. -->
            <div
              class="pointer-events-none absolute right-1 z-10 h-[3px] rounded-full bg-primary
              before:absolute before:-top-[2.5px] before:-left-1 before:size-2 before:rounded-full before:bg-primary
              {reordering.drop.edge === 'top' ? '-top-[2px]' : '-bottom-[2px]'}
              {reordering.drop.indent ? 'left-12' : 'left-1.5'}"
            ></div>
          {/if}
        {/snippet}
        {#snippet grip(label: string, dragged: () => Dragged)}
          <!-- Pointer only: the keyboard moves jobs with the Up and Down buttons. -->
          <span
            aria-hidden="true"
            title={label}
            class="flex shrink-0 cursor-grab touch-none items-center self-stretch px-1 text-muted-foreground/50 hover:text-foreground active:cursor-grabbing"
            onpointerdown={(e) => gripStart(e, dragged())}><GripVerticalIcon class="size-4" /></span
          >
        {/snippet}
        {#each rows as row, i (row.kind === 'job' ? row.job.id : `group:${row.group}:${i}`)}
          {#if row.kind === 'group'}
            {@const queuedJobs = groupQueued(row)}
            {@const canQueue = row.members.some((j) => queueable(j.status))}
            {@const progress = groupProgress(row)}
            {@const done = groupDone(row)}
            {@const failed = groupFailed(row)}
            {@const outside = selectedOutside(row.group)}
            {@const inside = selectedInside(row.group)}
            {@const shared = sharedByGroup.get(row.group)}
            {@const sharedLine =
              row.members[0] && shared ? jobFacts(row.members[0]).filter((f) => shared.has(f.key)) : []}
            <div
              data-row={i}
              class="relative flex min-h-10 items-center gap-1 border-b border-border/60 pl-2 text-sm
              {groupSelected(row) ? 'bg-card shadow-[inset_3px_0_0_var(--primary)]' : 'bg-muted/40'}
              {reordering?.drop?.row === i && reordering.drop.edge === 'inside' ? 'ring-2 ring-primary ring-inset' : ''}
              {moving.size && row.members.every((j) => moving.has(j.id)) ? 'opacity-50' : ''}"
            >
              {@render dropLine(i)}
              <Tip
                text={queuedJobs.length === row.members.length
                  ? 'All queued. Untick to unqueue the ones not running yet.'
                  : 'Tick to queue every job in the group that can be queued'}
              >
                <Checkbox
                  bind:checked={() => queuedJobs.length === row.members.length, (on) => act(() => queueGroup(row, on))}
                  indeterminate={queuedJobs.length > 0 && queuedJobs.length < row.members.length}
                  disabled={!canQueue && !queuedJobs.some((j) => j.status === 'queued')}
                  tabindex={-1}
                  aria-label={`Queued: every job in ${row.name}`}
                />
              </Tip>
              <Button
                variant="ghost"
                size="icon"
                class="size-7"
                aria-expanded={!row.collapsed}
                aria-label={`${row.collapsed ? 'Expand' : 'Collapse'} ${row.name}`}
                onclick={() => setCollapsed(row.group, !row.collapsed)}
              >
                {#if row.collapsed}<ChevronRightIcon />{:else}<ChevronDownIcon />{/if}
              </Button>
              <button
                class="min-w-0 flex-1 py-1 text-left focus-visible:outline-2 focus-visible:outline-ring"
                tabindex={-1}
                onclick={() => selectGroup(row)}
                aria-label={`${row.name}: select its ${plural(row.matching.length, 'job')}`}
              >
                <span class="flex items-baseline gap-2">
                  <span class="truncate font-medium">{row.name}</span>
                  {#if row.continued}<span class="shrink-0 text-xs text-muted-foreground">(continued)</span>{/if}
                  <span class="readout ml-auto flex shrink-0 gap-1 text-xs text-muted-foreground">
                    {#each groupCounts(row, done, failed) as part, n (part.text)}
                      {#if n}<span aria-hidden="true">·</span>{/if}<span class={part.tone}>{part.text}</span>
                    {/each}
                  </span>
                </span>
                {#if sharedLine.length}{@render factsLine(sharedLine, 'mt-0')}{/if}
              </button>
              {#if progress !== null}
                <!-- On the bottom edge, so a job starting doesn't change the header's height. -->
                <span class="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 bg-border">
                  <span class="block h-full bg-info" style="width:{progress * 100}%"></span>
                </span>
              {/if}
              <DropdownMenu.Root>
                <DropdownMenu.Trigger>
                  {#snippet child({ props })}
                    <Button {...props} variant="ghost" size="icon" class="size-7" aria-label={`${row.name} options`}
                      ><EllipsisIcon /></Button
                    >
                  {/snippet}
                </DropdownMenu.Trigger>
                <DropdownMenu.Content align="end" class="w-auto">
                  <DropdownMenu.Item onSelect={() => selectGroup(row)}>Select its jobs</DropdownMenu.Item>
                  {#if outside.length}
                    <DropdownMenu.Item
                      onSelect={() =>
                        moveToGroup(
                          outside.map((j) => j.id),
                          row.group,
                          true,
                        )}
                      >Move the {outside.length === 1 ? 'selected job' : `${outside.length} selected jobs`} here</DropdownMenu.Item
                    >
                  {/if}
                  {#if inside.length}
                    <DropdownMenu.Item
                      onSelect={() =>
                        moveToGroup(
                          inside.map((j) => j.id),
                          row.group,
                          false,
                        )}
                      >Take the {inside.length === 1 ? 'selected job' : `${inside.length} selected jobs`} out</DropdownMenu.Item
                    >
                  {/if}
                  <DropdownMenu.Separator />
                  <DropdownMenu.Item onSelect={() => (naming = { group: row.group, name: row.name })}
                    >Rename…</DropdownMenu.Item
                  >
                  <Tip class="block" side="left" text="The group goes. Its jobs stay in the queue, where they are.">
                    <DropdownMenu.Item onSelect={() => ungroup(row.group)}>Ungroup</DropdownMenu.Item>
                  </Tip>
                </DropdownMenu.Content>
              </DropdownMenu.Root>
              {@render grip(`Drag to move ${row.name}`, () => ({ kind: 'group', group: row.group }))}
            </div>
          {:else}
            {@const job = row.job}
            {@const queued = job.status === 'queued' || job.status === 'running'}
            {@const shared = sharedByGroup.get(row.group)}
            {@const facts = jobFacts(job).filter((f) => !shared?.has(f.key))}
            <div
              data-row={i}
              class="relative flex border-b border-border/60 {row.group ? 'pl-4' : ''} {selectedSet.has(job.id)
                ? 'bg-card shadow-[inset_3px_0_0_var(--primary)]'
                : 'hover:bg-accent'} {moving.has(job.id) ? 'opacity-50' : ''}"
            >
              {#if row.group}
                <!-- A group's jobs hang from its header's box. -->
                <span class="pointer-events-none absolute inset-y-0 left-4 w-px bg-border" aria-hidden="true"></span>
              {/if}
              {@render dropLine(i)}
              <div class="flex shrink-0 items-start pt-2.5 pl-2">
                <!-- Out of the tab order (the list is one stop): the keyboard queues a selection with Queue (N). -->
                <Tip
                  text={job.status === 'running'
                    ? 'Running'
                    : queued
                      ? 'Queued and locked. Untick it to make changes.'
                      : queueable(job.status)
                        ? "Tick to queue it. It's locked while it's queued."
                        : `Can't be queued while its status is ${STATUS_LABEL[job.status]}`}
                >
                  <Checkbox
                    bind:checked={() => queued, (on) => act(() => (on ? queue([job.id]) : unqueue([job.id])))}
                    disabled={job.status === 'running' || (!queued && !queueable(job.status))}
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
                  <Tip class="block min-w-[15ch] truncate font-medium" text={job.source}>{job.name}</Tip>
                  {#if job.label}<Tip class="min-w-0 shrink" text="Label"
                      ><Badge variant="outline" class="block shrink truncate px-1.5 py-0 text-xs font-normal"
                        >{job.label}</Badge
                      ></Tip
                    >{/if}
                  <div class="ml-auto flex shrink-0 items-center gap-2 text-xs">
                    {#if job.indexed}
                      <Tip class="items-center" text="Indexed, so the preview opens at once"
                        ><DatabaseCheckIcon class="size-3.5" /></Tip
                      >
                    {/if}
                    {#if job.status === 'warn'}
                      <span class="whitespace-nowrap {STATUS_TONE.warn}"
                        >{#if job.issue_counts.warn}<IssueCounts
                            counts={{ block: 0, warn: job.issue_counts.warn }}
                          />{:else}{STATUS_LABEL.warn}{/if}</span
                      >
                    {:else if job.status === 'blocked'}
                      <span class="whitespace-nowrap {STATUS_TONE.blocked}"
                        >{#if job.issue_counts.block}<IssueCounts
                            counts={{ block: job.issue_counts.block, warn: 0 }}
                          />{:else}{STATUS_LABEL.blocked}{/if}</span
                      >
                      {@render mark(job.issue_counts.warn, false)}
                    {:else}
                      {#if paused(job.status)}
                        <span class="text-info">Paused</span>
                      {:else if job.status === 'queued'}
                        <!-- locked: its box is ticked, so its settings can't change until it's unticked -->
                        <span class="flex items-center gap-1 {STATUS_TONE.queued}"
                          ><LockIcon aria-hidden="true" class="size-3" />{STATUS_LABEL.queued}</span
                        >
                      {:else}
                        <span class={STATUS_TONE[job.status]}>{STATUS_LABEL[job.status]}</span>
                      {/if}
                      {@render mark(job.issue_counts.block, true)}
                      {@render mark(job.issue_counts.warn, false)}
                    {/if}
                  </div>
                </div>
                {#if facts.length}{@render factsLine(facts, 'mt-0.5')}{/if}
                {#if shared?.size}
                  <!-- The header shows these once; a screen reader hears each row whole (the header's name is its own). -->
                  {@const common = jobFacts(job).filter((f) => shared.has(f.key))}
                  <span class="sr-only"
                    >{'· ' + common.flatMap((f) => f.tags ?? f.text).join(' · ')}{common.some((f) =>
                      f.tags?.some((n) => n.endsWith('?')),
                    )
                      ? '. ' + DV7_NOTE
                      : ''}</span
                  >
                {/if}
                {#if LIVE.includes(job.status) && job.progress}
                  <div class="readout mt-1.5 flex items-center gap-2 text-xs text-info">
                    <div class="h-1 flex-1 overflow-hidden rounded bg-muted">
                      <div class="h-full bg-info" style="width:{job.progress.overall * 100}%"></div>
                    </div>
                    {percent(job.progress.overall)}
                  </div>
                  <div class="flex gap-2 text-xs text-muted-foreground">
                    <span class="readout truncate">{job.progress.step} · {percent(job.progress.fraction)}</span>
                    <Tip
                      class="readout ml-auto shrink-0"
                      text="Encoder speed · time since the run started · the job's time left (a guess from its pace so far)"
                      >{progressTimes(job.progress)}</Tip
                    >
                  </div>
                {/if}
                {#if job.index_held && job.status === 'index-queued'}
                  <Tip
                    class="mt-0.5 block truncate text-xs text-muted-foreground"
                    text="Indexing waits while an encode reads this disk (Settings › Queue & indexing › Wait while an encode reads the same disk), and always while another job of this source runs."
                  >
                    Waiting for the encode reading this disk
                  </Tip>
                {/if}
                {#if job.index_error && job.status !== 'indexing'}
                  <Tip class="mt-0.5 block truncate text-xs text-warning" text={job.index_error}>
                    Index failed: {job.index_error}
                  </Tip>
                {/if}
              </button>
              {@render grip(
                selectedSet.has(job.id) && selected.length > 1
                  ? `Drag to move the ${selected.length} selected jobs`
                  : 'Drag to move this job, into or out of a group',
                () => jobsFor(job.id),
              )}
            </div>
          {/if}
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
        {#if reordering && lastPage}
          <!-- Below the last row: the end of the queue, out of any group. -->
          <div class="h-10" aria-hidden="true">
            {#if reordering.drop?.row === rows.length}<div class="h-0.5 rounded bg-primary"></div>{/if}
          </div>
        {/if}
      </div>
      <div class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t p-2 text-xs">
        <span
          >Showing {slots.length ? currentPage * QUEUE_PAGE_SIZE + 1 : 0}–{Math.min(
            (currentPage + 1) * QUEUE_PAGE_SIZE,
            slots.length,
          )} of {slots.length}{slots.length !== matching.length ? ` rows (${matching.length} jobs)` : ''}</span
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
            disabled={lastPage}
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
            Changes here apply to every selected job, except jobs that are queued, running, indexing, or running a test
            encode or CRF search. The values shown are the first selected job's. Each job keeps its own audio and
            subtitle choices unless the template sets them.
          </p>
          <div class="flex flex-wrap items-center gap-3">
            <Button variant="outline" disabled={!batchToIndex} onclick={() => index(selected)}>
              <DatabaseZapIcon />{batchToIndex
                ? `Index ${batchToIndex} job${batchToIndex > 1 ? 's' : ''}`
                : 'All indexed'}
            </Button>
            <span class="text-sm text-muted-foreground">
              Makes only each job's work folder, script and source index, one job at a time in the background, beside
              the queue. Their preview then opens at once, and their encode reuses the index.{batchToIndex &&
              batchToIndex < selected.length
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
                <Button variant="outline" class="ml-auto" onclick={applyTemplate} disabled={!picked}
                  ><LayoutTemplateIcon />Apply to {selected.length} jobs</Button
                >
              </div>
              <p class="text-xs text-muted-foreground">
                Sets video, encoder, AutoQPF{picked?.data.audio ? ', audio' : ''}{picked?.data.subs
                  ? ', subtitles'
                  : ''}, and the container with its options{picked?.data.crop_mode === 'auto'
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
                      class="px-4 data-[state=on]:border-primary data-[state=on]:bg-primary/15 data-[state=on]:text-foreground"
                      >{c.label}</ToggleGroup.Item
                    >
                  {/each}
                </ToggleGroup.Root>
                <span class="text-xs text-muted-foreground"
                  >Each job keeps its own extra arguments, and warns when they were typed for the other container.</span
                >
              </Card.Root>
            {/if}
            <Card.Root class="gap-2 p-4">
              <div
                class="-m-1 flex flex-wrap items-center gap-3 rounded-lg p-1 outline-none"
                role="group"
                aria-label="Output folder for the selected jobs (drop or paste a folder)"
                use:pathDrop={{
                  rule: { mode: 'folder', label: 'Output folder' },
                  accept: (paths) => applyOutput(paths[0]),
                }}
              >
                <span class="text-sm">Output folder</span>
                <Input
                  class="min-w-48 flex-1 font-mono text-xs"
                  aria-label="Output folder for the selected jobs"
                  placeholder="Not set"
                  value={batchSource.spec.output_dir ?? ''}
                  onchange={(e) => applyOutput(pastedPaths((e.target as HTMLInputElement).value)[0] || null)}
                />
                <Button variant="outline" onclick={() => (browsingOutput = true)}><FolderOpenIcon />Browse…</Button>
                <OutputFolderMenu onpick={(path) => applyOutput(path)} />
              </div>
              <p class="text-xs text-muted-foreground">
                Every selected job writes its file here. Each job keeps its own output name.
              </p>
            </Card.Root>
            <Card.Root class="p-4">
              <EncoderPanel ruleSet={batchSource.rule_set} value={batchSource.spec.encoder} onchange={applyEncoder} />
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

<ReuseDialog />

{#if browsingOutput && batchSource}
  <FileBrowser
    title="Output folder for {selected.length} jobs"
    mode="folder"
    start={batchSource.spec.output_dir ?? ''}
    onpick={(paths) => {
      browsingOutput = false
      if (paths[0]) applyOutput(paths[0])
    }}
    onclose={() => (browsingOutput = false)}
  />
{/if}

<Dialog.Root
  open={naming !== null}
  onOpenChange={(open) => {
    if (!open) naming = null
  }}
>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>{naming?.group ? 'Rename the group' : `Group ${selected.length} jobs`}</Dialog.Title>
      <Dialog.Description>
        A group's jobs are shown together, and you can collapse it. Drag a job's grip to move it into or out of a group.
        Grouping doesn't change the jobs' settings.
      </Dialog.Description>
    </Dialog.Header>
    {#if naming}
      <form
        class="contents"
        onsubmit={(e) => {
          e.preventDefault()
          void saveName()
        }}
      >
        <Input aria-label="Group name" maxlength={80} bind:value={naming.name} />
        <Dialog.Footer>
          <Button variant="outline" type="button" onclick={() => (naming = null)}>Cancel</Button>
          <Button type="submit" disabled={!naming.name.trim()}>{naming.group ? 'Rename' : 'Group'}</Button>
        </Dialog.Footer>
      </form>
    {/if}
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={importOpen}>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>Add jobs from job files</Dialog.Title>
      <Dialog.Description>
        A <code>videoforge-job.json</code>, a job's folder, or a source's <code>_tmp</code> folder (adds every job in it).
        Each job comes back with the settings it was saved with, and when it runs you can reuse the encodes it finished.
      </Dialog.Description>
    </Dialog.Header>
    <PathSlot
      label="Job files"
      hint="Browse, or paste paths (Explorer: Ctrl+Shift+C)"
      extensions={['.json']}
      bind:paths={importPaths}
    />
    <Dialog.Footer>
      <Button variant="outline" onclick={() => (importOpen = false)}>Close</Button>
      <Button disabled={importing || !importPaths.length} onclick={importJobs}>Add jobs</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root
  open={removal !== null}
  onOpenChange={(open) => {
    if (!open && !removing) removal = null
  }}
>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>Remove the jobs and delete their work folders?</Dialog.Title>
      <Dialog.Description
        >Each job's records and log are copied to the records folder in VideoForge's data folder first. Then the work
        folder is deleted for good, with its index, scripts, encodes and job files. A job added again for the same
        source starts from scratch. Finished files in the output folder are kept.</Dialog.Description
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
