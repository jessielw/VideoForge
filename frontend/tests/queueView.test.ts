import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  defaultGroupName,
  dropTarget,
  matchingJobs,
  moveSelection,
  movedQueue,
  queuePage,
  queueRange,
  queueRows,
  queueSlots,
  queueable,
  sameQueue,
  slotPage,
  sharedFacts as sharedOf,
  QUEUE_PAGE_SIZE,
  type Dragged,
  type QueueRow,
} from '../src/lib/queueView.ts'
import { jobFacts } from '../src/lib/format.ts'
import type { JobSummary } from '../src/lib/types.ts'

const jobs = [
  { id: 'a', name: 'Episode 01', source: 'D:\\Show\\Season2\\01.mkv', status: 'ready' },
  { id: 'b', name: 'Episode 02', source: 'D:\\Show\\Season1\\02.mkv', status: 'done' },
  { id: 'c', name: 'Episode 03', label: 'dubbed', source: 'D:\\Show\\Season2\\03.mkv', status: 'failed' },
] as JobSummary[]

test('queue search combines words, labels, source paths, and status without changing run order', () => {
  assert.deepEqual(
    matchingJobs(jobs, '  SEASON2 episode ').map((j) => j.id),
    ['a', 'c'],
  )
  assert.deepEqual(
    matchingJobs(jobs, 'show', 'failed').map((j) => j.id),
    ['c'],
  )
  assert.deepEqual(
    matchingJobs(jobs, '', 'done').map((j) => j.id),
    ['b'],
  )
  assert.equal(matchingJobs(jobs, 'missing').length, 0)
  assert.deepEqual(matchingJobs(jobs, '  '), jobs)
  assert.deepEqual(
    matchingJobs(jobs, 'episode DUBBED').map((j) => j.id),
    ['c'],
  )
})

test("queue search also matches a row's format: its encoder, resolution and HDR tags", () => {
  const formats = [
    { ...jobs[0], encoder: 'x265 CRF 18 10-bit', source_facts: { resolution: '3840x2160', hdr: ['HDR10'] } },
    { ...jobs[1], encoder: 'x264 CRF 18', source_facts: { resolution: '1920x1080', hdr: [] } },
    { ...jobs[2], encoder: 'x265 CRF 20 10-bit', source_facts: { resolution: '3840x1608', hdr: ['DV 8.1', 'HDR10+'] } },
  ] as JobSummary[]
  const ids = (query: string) => matchingJobs(formats, query).map((j) => j.id)
  assert.deepEqual(ids('hdr10'), ['a', 'c']) // HDR10+ has HDR10 in it
  assert.deepEqual(ids('3840 x265'), ['a', 'c'])
  assert.deepEqual(ids('x264'), ['b'])
  assert.deepEqual(ids('dv episode'), ['c'])
  assert.deepEqual(ids('2160'), ['a'])
  assert.deepEqual(
    matchingJobs(jobs, 'x265').map((j) => j.id),
    [],
  ) // rows not read yet have no format
})

test('selection ranges follow matching order and recover when a live status removes the anchor', () => {
  assert.deepEqual(queueRange(['a', 'c'], 'c', 'a'), ['a', 'c'])
  assert.deepEqual(queueRange(['a', 'c'], 'b', 'c'), ['c'])
  assert.deepEqual(queueRange(['a', 'c'], 'a', 'gone'), [])
})

test('queue pages clamp after removal and handle empty and exact page boundaries', () => {
  assert.equal(queuePage(0, 9), 0)
  assert.equal(queuePage(QUEUE_PAGE_SIZE, 1), 0)
  assert.equal(queuePage(QUEUE_PAGE_SIZE + 1, 9), 1)
  assert.equal(queuePage(10_000, 99), 99)
})

test('a job can be queued once it is set up, and again after a run, but not while it is busy or blocked', () => {
  for (const s of ['ready', 'warn', 'index-queued', 'done', 'failed', 'invalid', 'skipped', 'cancelled'] as const)
    assert.ok(queueable(s), s)
  for (const s of ['probing', 'error', 'cropping', 'indexing', 'blocked', 'queued', 'running'] as const)
    assert.ok(!queueable(s), s)
})

// --- queue groups -----------------------------------------------------------------------------------------

const job = (id: string, group: string | null = null, status = 'ready') =>
  ({ id, name: id, label: '', source: id, status, group, group_name: group ? `Group ${group}` : '' }) as JobSummary
// a, then group G (g1 g2 g3), then b, then group H (h1)
const order = [job('a'), job('g1', 'G'), job('g2', 'G'), job('g3', 'G'), job('b'), job('h1', 'H')]
const ids = (rows: QueueRow[]) => rows.map((r) => (r.kind === 'job' ? r.job.id : `[${r.group}]`))

test('a group shows its header before its jobs, and a collapsed group is one slot', () => {
  const open = queueSlots(order, new Set())
  assert.equal(open.length, 6)
  assert.deepEqual(ids(queueRows(open, 0, order)), ['a', '[G]', 'g1', 'g2', 'g3', 'b', '[H]', 'h1'])
  const shut = queueSlots(order, new Set(['G']))
  assert.equal(shut.length, 4)
  const rows = queueRows(shut, 0, order)
  assert.deepEqual(ids(rows), ['a', '[G]', 'b', '[H]', 'h1'])
  const header = rows[1]
  assert.ok(header.kind === 'group' && header.collapsed && header.members.length === 3 && header.name === 'Group G')
  assert.equal(slotPage(shut, 'g2'), 0)
  assert.equal(slotPage(shut, 'gone'), -1)
})

test('a filtered group counts what matches, and a group carried to the next page shows its header again', () => {
  const rows = queueRows(queueSlots([order[0], order[2]], new Set()), 0, order)
  const header = rows[1]
  assert.ok(header.kind === 'group' && header.matching.length === 1 && header.members.length === 3)
  const many = [...Array.from({ length: QUEUE_PAGE_SIZE - 1 }, (_, i) => job(`x${i}`)), job('p1', 'P'), job('p2', 'P')]
  const slots = queueSlots(many, new Set())
  const second = queueRows(slots, 1, many)
  assert.deepEqual(ids(second), ['[P]', 'p2'])
  assert.ok(second[0].kind === 'group' && second[0].continued)
  assert.equal(slotPage(slots, 'p2'), 1)
})

test('a job dropped by a group joins it inside, and stays out on the outer side of its edges', () => {
  const rows = queueRows(queueSlots(order, new Set()), 0, order) // a [G] g1 g2 g3 b [H] h1
  const jobs: Dragged = { kind: 'jobs', ids: ['b'] }
  const at = (index: number, y: number) => {
    const d = dropTarget(rows, index, y, order, jobs)
    return d && [d.before, d.group, d.indent]
  }
  assert.deepEqual(at(0, 0.2), ['a', '', false]) // before a
  assert.deepEqual(at(1, 0.2), ['g1', '', false]) // above G's header: before the group
  assert.deepEqual(at(1, 0.8), ['g1', 'G', true]) // header's lower half: first in G
  assert.deepEqual(at(3, 0.2), ['g2', 'G', true]) // between g1 and g2
  assert.deepEqual(at(4, 0.8), ['b', 'G', true]) // below the last member: still in G (indented line)
  assert.deepEqual(at(5, 0.2), ['b', '', false]) // above b: after G, ungrouped (full-width line)
  assert.deepEqual(at(rows.length, 0), [null, '', false]) // below the list: at the end
})

test('a collapsed header takes a job before it, into it, or after it, by thirds', () => {
  const rows = queueRows(queueSlots(order, new Set(['G'])), 0, order) // a [G] b [H] h1
  const at = (y: number) => {
    const d = dropTarget(rows, 1, y, order, { kind: 'jobs', ids: ['a'] })
    return d && [d.before, d.group, d.edge]
  }
  assert.deepEqual(at(0.1), ['g1', '', 'top'])
  assert.deepEqual(at(0.5), ['b', 'G', 'inside'])
  assert.deepEqual(at(0.9), ['b', '', 'bottom'])
})

test('a dragged group lands before or after another group, never inside it or itself', () => {
  const rows = queueRows(queueSlots(order, new Set()), 0, order) // a [G] g1 g2 g3 b [H] h1
  const group: Dragged = { kind: 'group', group: 'H' }
  const at = (index: number, y: number) => {
    const d = dropTarget(rows, index, y, order, group)
    return d && [d.before, d.group]
  }
  assert.deepEqual(at(0, 0.2), ['a', 'H'])
  assert.deepEqual(at(2, 0.8), ['g1', 'H']) // in G's upper half: before G
  assert.deepEqual(at(4, 0.8), ['b', 'H']) // in G's lower half: after G
  assert.equal(at(7, 0.5), null) // onto itself
})

test('Up and Down keep a job inside its group and move a whole group as one', () => {
  const plain = order.map((j) => j.id)
  assert.deepEqual(moveSelection(order, new Set(['g1']), -1), plain) // stops at the group's top
  assert.deepEqual(moveSelection(order, new Set(['g2']), -1), ['a', 'g2', 'g1', 'g3', 'b', 'h1'])
  assert.deepEqual(moveSelection(order, new Set(['b']), -1), ['a', 'b', 'g1', 'g2', 'g3', 'h1']) // hops over G
  assert.deepEqual(moveSelection(order, new Set(['g1', 'g2', 'g3']), -1), ['g1', 'g2', 'g3', 'a', 'b', 'h1'])
  assert.deepEqual(moveSelection(order, new Set(['a']), 1), ['g1', 'g2', 'g3', 'a', 'b', 'h1'])
  assert.deepEqual(moveSelection(order, new Set(['h1']), 1), plain)
})

test('a new group is named after the season, the folder, or what the names share', () => {
  assert.equal(
    defaultGroupName(['D:\\TV\\Show.Name.S01E01.1080p.mkv', 'D:\\TV\\Show.Name.S01E02.1080p.mkv']),
    'Show Name S01',
  )
  assert.equal(defaultGroupName(['/tv/Show/Season 2/01.mkv', '/tv/Show/Season 2/02.mkv']), 'Show Season 2')
  assert.equal(defaultGroupName(['/media/Concerts/a.mkv', '/media/Concerts/b.mkv']), 'Concerts')
  assert.equal(defaultGroupName(['/a/Movie Part 1.mkv', '/b/Movie Part 2.mkv']), 'Movie Part')
  assert.equal(defaultGroupName(['D:\\x.mkv', 'E:\\y.mkv']), '2 jobs')
  assert.equal(defaultGroupName(['D:\\a.mkv', 'D:\\b.mkv']), '2 jobs') // a drive is no name
})

test('a move that changes nothing is told apart from one that does', () => {
  const plain = order.map(({ id, group }) => ({ id, group }))
  // a job dropped where it already is, or just after itself
  assert.ok(sameQueue(movedQueue(plain, ['g2'], 'g2', 'G'), plain))
  assert.ok(sameQueue(movedQueue(plain, ['g2'], 'g3', 'G'), plain))
  // the same place, out of its group, is a change
  assert.ok(!sameQueue(movedQueue(plain, ['g3'], 'b', ''), plain))
  assert.deepEqual(
    movedQueue(plain, ['a'], 'g2', 'G').map((j) => `${j.id}:${j.group ?? ''}`),
    ['g1:G', 'a:G', 'g2:G', 'g3:G', 'b:', 'h1:H'],
  )
  assert.deepEqual(
    movedQueue(plain, ['g1', 'g2', 'g3'], null, 'G').map((j) => j.id),
    ['a', 'b', 'h1', 'g1', 'g2', 'g3'],
  )
})

const factJob = (over: Partial<JobSummary> = {}) =>
  ({
    encoder: 'x265',
    crop: null,
    custom_script: false,
    audio: [{}, {}],
    subs: 3,
    source_facts: { resolution: '1920x1080', duration_ms: 1_500_000, hdr: ['HDR10', 'HLG'], interlaced: false },
    ...over,
  }) as unknown as JobSummary

const sharedFacts = (jobs: JobSummary[]) => sharedOf(jobs.map(jobFacts))

test('sharedFacts: what every job in a group has the same, compared as a row shows it', () => {
  const same = [factJob(), factJob(), factJob()]
  assert.deepEqual([...sharedFacts(same)].sort(), ['audio', 'encoder', 'hdr', 'length', 'resolution', 'subs'].sort())
  // One value differs: only that fact leaves; the HDR tags compare as a set.
  const differs = [
    factJob(),
    factJob({
      encoder: 'x264',
      source_facts: { resolution: '1920x1080', duration_ms: 1_560_000, hdr: ['HLG', 'HDR10'], interlaced: false },
    }),
  ]
  assert.deepEqual([...sharedFacts(differs)].sort(), ['audio', 'hdr', 'resolution', 'subs'].sort())
  // A custom script, or the same crop, is shared; a different crop is not.
  const crop = { left: 0, top: 42, right: 0, bottom: 42 }
  assert.ok(sharedFacts([factJob({ crop }), factJob({ crop: { ...crop } })]).has('extras'))
  assert.ok(!sharedFacts([factJob({ crop }), factJob({ crop: { ...crop, top: 40 } })]).has('extras'))
  assert.ok(!sharedFacts([factJob({ custom_script: true }), factJob()]).has('extras'))
})

test('sharedFacts: a group of one shares nothing, and a job without source facts shares no source fact', () => {
  assert.equal(sharedFacts([factJob()]).size, 0)
  assert.equal(sharedFacts([]).size, 0)
  const reading = [factJob(), factJob({ source_facts: null })]
  assert.deepEqual([...sharedFacts(reading)].sort(), ['audio', 'encoder', 'subs'])
})
