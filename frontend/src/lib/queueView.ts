import type { JobSummary, Status } from './types'

export const QUEUE_PAGE_SIZE = 100

/** Preserve queue order; every search word must occur in the name, label or source path, or in the row's format:
 * its encoder ("x265 CRF 18"), resolution ("3840x2160") and HDR tags ("HDR10"). */
export function matchingJobs(jobs: JobSummary[], query: string, status: Status | '' = ''): JobSummary[] {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return jobs.filter((job) => {
    if (status && job.status !== status) return false
    if (!words.length) return true
    const f = job.source_facts
    const text = [job.name, job.label, job.source, job.encoder, f?.resolution, ...(f?.hdr ?? [])]
      .join('\n')
      .toLocaleLowerCase()
    return words.every((word) => text.includes(word))
  })
}

export function queueRange(ids: string[], from: string, to: string): string[] {
  const a = ids.indexOf(from)
  const b = ids.indexOf(to)
  // An anchor can disappear when the filter or a live status changes.
  if (b < 0) return []
  if (a < 0) return [to]
  return ids.slice(Math.min(a, b), Math.max(a, b) + 1)
}

export function queuePage(count: number, requested: number): number {
  return Math.max(0, Math.min(requested, Math.ceil(count / QUEUE_PAGE_SIZE) - 1))
}

// --- queue groups: a batch of jobs shown together (e.g. a season) ---------------------------------------
// The server keeps a group's jobs next to each other in the queue order, so they are one run in any list.

type Grouped = Pick<JobSummary, 'id' | 'group'>

/** What a list page counts: a job's row, or a collapsed group (its header stands for its jobs). */
export type QueueSlot =
  { kind: 'job'; job: JobSummary; group: string } | { kind: 'collapsed'; group: string; matching: JobSummary[] }

/** A rendered row: a group's header (before its first job on the page), or a job's. */
export type QueueRow =
  | {
      kind: 'group'
      group: string
      name: string
      members: JobSummary[] // every job in the group, filters or not
      matching: JobSummary[] // those the search and status filter show
      collapsed: boolean
      continued: boolean // its jobs started on an earlier page
    }
  | { kind: 'job'; job: JobSummary; group: string }

/** The list's slots: a matching job each, but a collapsed group's matching jobs are one slot. */
export function queueSlots(matching: JobSummary[], collapsed: ReadonlySet<string>): QueueSlot[] {
  const slots: QueueSlot[] = []
  for (const job of matching) {
    const group = job.group ?? ''
    const last = slots.at(-1)
    if (group && collapsed.has(group)) {
      if (last?.kind === 'collapsed' && last.group === group) last.matching.push(job)
      else slots.push({ kind: 'collapsed', group, matching: [job] })
    } else slots.push({ kind: 'job', job, group })
  }
  return slots
}

/** One page of slots as rows: a header goes before each group's first slot on the page. */
export function queueRows(slots: QueueSlot[], page: number, all: JobSummary[]): QueueRow[] {
  const start = page * QUEUE_PAGE_SIZE
  const members = new Map<string, JobSummary[]>()
  for (const job of all) if (job.group) members.set(job.group, [...(members.get(job.group) ?? []), job])
  const matching = new Map<string, JobSummary[]>()
  for (const s of slots) {
    if (!s.group) continue
    const list = matching.get(s.group) ?? []
    if (s.kind === 'job') list.push(s.job)
    else list.push(...s.matching)
    matching.set(s.group, list)
  }
  const rows: QueueRow[] = []
  let previous = start > 0 ? slots[start - 1]?.group : ''
  for (const s of slots.slice(start, start + QUEUE_PAGE_SIZE)) {
    if (s.group && (rows.length === 0 || previous !== s.group || s.kind === 'collapsed')) {
      const all = members.get(s.group) ?? []
      rows.push({
        kind: 'group',
        group: s.group,
        name: all[0]?.group_name || 'Group',
        members: all,
        matching: matching.get(s.group) ?? [],
        collapsed: s.kind === 'collapsed',
        continued: rows.length === 0 && previous === s.group,
      })
    }
    if (s.kind === 'job') rows.push(s)
    previous = s.group
  }
  return rows
}

/** The page a job's slot is on (-1 when it isn't in the list). */
export function slotPage(slots: QueueSlot[], id: string): number {
  const at = slots.findIndex((s) => (s.kind === 'job' ? s.job.id === id : s.matching.some((j) => j.id === id)))
  return at < 0 ? -1 : Math.floor(at / QUEUE_PAGE_SIZE)
}

/** Where a drop goes: just before `before` (null: at the end) in group `group` ('' none), and the line to draw. */
export interface Drop {
  before: string | null
  group: string
  row: number // the row the line is drawn on (rows.length: below the last)
  edge: 'top' | 'bottom' | 'inside'
  indent: boolean // the line is inside a group
}

/** What is being dragged: jobs (they take the group of where they land), or a whole group. */
export type Dragged = { kind: 'jobs'; ids: string[] } | { kind: 'group'; group: string }

/**
 * The drop for the pointer over row `index`, `y` of the way down it (0 top, 1 bottom); index === rows.length
 * is the space below the last row. `order` is the whole queue (the place after a row is before the job after
 * it there, even one the filters hide). Null: nowhere to go (a group onto itself).
 */
export function dropTarget(
  rows: QueueRow[],
  index: number,
  y: number,
  order: Grouped[],
  dragged: Dragged,
): Drop | null {
  const after = (id: string) => order[order.findIndex((j) => j.id === id) + 1]?.id ?? null
  const first = (group: string) => order.find((j) => j.group === group)?.id ?? null
  const afterGroup = (group: string) => {
    const last = order.findLastIndex((j) => j.group === group)
    return order[last + 1]?.id ?? null
  }
  let drop: Drop
  const row = rows[index]
  if (!row) drop = { before: null, group: '', row: rows.length, edge: 'top', indent: false }
  else if (row.kind === 'job') {
    drop =
      y < 0.5
        ? { before: row.job.id, group: row.group, row: index, edge: 'top', indent: !!row.group }
        : { before: after(row.job.id), group: row.group, row: index, edge: 'bottom', indent: !!row.group }
  } else if (row.collapsed) {
    if (y < 1 / 3) drop = { before: first(row.group), group: '', row: index, edge: 'top', indent: false }
    else if (y < 2 / 3)
      drop = { before: afterGroup(row.group), group: row.group, row: index, edge: 'inside', indent: true }
    else drop = { before: afterGroup(row.group), group: '', row: index, edge: 'bottom', indent: false }
  } else if (row.continued || y >= 0.5) {
    const next = rows[index + 1]
    const before = next?.kind === 'job' ? next.job.id : first(row.group)
    drop = { before, group: row.group, row: index, edge: 'bottom', indent: true }
  } else drop = { before: first(row.group), group: '', row: index, edge: 'top', indent: false }

  if (dragged.kind === 'jobs' || drop.group === '')
    return dragged.kind === 'group' ? { ...drop, group: dragged.group } : drop
  // A group can't go inside another: before or after that one, whichever half of it the pointer is in.
  if (drop.group === dragged.group) return null
  const inside = rows.filter((r) => r.kind === 'job' && r.group === drop.group)
  const header = rows.findIndex((r) => r.kind === 'group' && r.group === drop.group)
  const lastRow = rows.findLastIndex((r) => r.group === drop.group)
  const upper = row?.kind === 'group' ? drop.edge !== 'inside' : inside.indexOf(row as QueueRow) < inside.length / 2
  return upper
    ? { before: first(drop.group), group: dragged.group, row: Math.max(header, 0), edge: 'top', indent: false }
    : { before: afterGroup(drop.group), group: dragged.group, row: lastRow, edge: 'bottom', indent: false }
}

/** The queue after a move, as the server makes it (JobQueue.move); with sameQueue, tells a drop that changes nothing. */
export function movedQueue(order: Grouped[], ids: string[], before: string | null, group: string): Grouped[] {
  const wanted = new Set(ids)
  if (before !== null && wanted.has(before)) {
    const from = order.findIndex((j) => j.id === before)
    before = order.slice(from).find((j) => !wanted.has(j.id))?.id ?? null
  }
  const moving = order.filter((j) => wanted.has(j.id)).map((j) => ({ id: j.id, group: group || null }))
  const rest = order.filter((j) => !wanted.has(j.id))
  const found = before === null ? -1 : rest.findIndex((j) => j.id === before)
  const at = found < 0 ? rest.length : found
  return [...rest.slice(0, at), ...moving, ...rest.slice(at)]
}

export function sameQueue(a: Grouped[], b: Grouped[]): boolean {
  return a.length === b.length && a.every((j, i) => j.id === b[i].id && (j.group || null) === (b[i].group || null))
}

/**
 * The queue order after Up (-1) or Down (1) on the selection: a job in a group moves only within it (dragging
 * takes a job out); an ungrouped job, or a group all selected, moves past the next job or group as a block.
 */
export function moveSelection(order: Grouped[], selected: ReadonlySet<string>, step: -1 | 1): string[] {
  const bubble = <T>(items: T[], picked: (item: T) => boolean): T[] => {
    const list = step < 0 ? [...items] : [...items].reverse()
    for (let i = 1; i < list.length; i++)
      if (picked(list[i]) && !picked(list[i - 1])) [list[i - 1], list[i]] = [list[i], list[i - 1]]
    return step < 0 ? list : list.reverse()
  }
  const units: { group: string; ids: string[] }[] = []
  for (const job of order) {
    const last = units.at(-1)
    if (job.group && last?.group === job.group) last.ids.push(job.id)
    else units.push({ group: job.group ?? '', ids: [job.id] })
  }
  const whole = (u: { ids: string[] }) => u.ids.every((id) => selected.has(id))
  for (const u of units) if (u.group && !whole(u)) u.ids = bubble(u.ids, (id) => selected.has(id))
  return bubble(units, (u) => (u.group ? whole(u) : selected.has(u.ids[0]))).flatMap((u) => u.ids)
}

const EPISODE = /^(.*?)[ ._-]*S(\d{1,2})[ ._-]*E\d+/i
const SEASON_FOLDER = /^(season|series|staffel|saison|s)[ ._-]*\d+$/i

/** A group name for these sources: "Show S01" from episode names, else their folder's ("Show Season 1" for a
 * season folder), else what their names start with, else "N jobs". */
export function defaultGroupName(sources: string[]): string {
  const parts = sources.map((s) => s.split(/[\\/]+/).filter(Boolean))
  const stems = parts.map((p) => (p.at(-1) ?? '').replace(/\.[^.]+$/, ''))
  const tidy = (text: string) => text.replace(/[._]+/g, ' ').replace(/\s+/g, ' ').trim()
  const episodes = stems.map((s) => s.match(EPISODE))
  if (episodes.length && episodes.every(Boolean)) {
    const titles = new Set(episodes.map((m) => tidy(m![1]).toLocaleLowerCase()))
    const seasons = new Set(episodes.map((m) => Number(m![2])))
    if (titles.size === 1 && seasons.size === 1) {
      const title = tidy(episodes[0]![1])
      const season = `S${String([...seasons][0]).padStart(2, '0')}`
      return title ? `${title} ${season}` : season
    }
  }
  const folders = new Set(parts.map((p) => p.slice(0, -1).join('/')))
  if (parts.length && folders.size === 1) {
    const folder = parts[0].slice(0, -1)
    const name = folder.at(-1) ?? ''
    if (name && !/^[a-z]:$/i.test(name)) {
      const show = folder.at(-2)
      return SEASON_FOLDER.test(name) && show && !/^[a-z]:$/i.test(show) ? `${show} ${name}` : name
    }
  }
  let prefix = stems[0] ?? ''
  for (const s of stems) while (prefix && !s.startsWith(prefix)) prefix = prefix.slice(0, -1)
  prefix = tidy(prefix.replace(/[ ._-]*(S\d*|E\d*|\d+)?$/i, ''))
  return prefix.length >= 3 ? prefix : `${sources.length} jobs`
}

// Whether a job can be queued: queued is locked (read-only), and the queue runs it. Not one still being
// probed, indexed, test encoded or crop-detected, a blocked one, or one already queued or running.
export function queueable(status: Status): boolean {
  return !['probing', 'error', 'cropping', 'indexing', 'sampling', 'blocked', 'queued', 'running'].includes(status)
}
