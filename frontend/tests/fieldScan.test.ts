import assert from 'node:assert/strict'
import { test } from 'node:test'
import { applyFieldFix, fixChanges, stretchTimes, stripCells } from '../src/lib/fieldScan.ts'
import type { FieldScanFix, FieldScanReport, FilterStep, VideoSettings } from '../src/lib/types.ts'

const report = (over: Partial<FieldScanReport> = {}): FieldScanReport => ({
  verdict: 'hybrid',
  order: 'tff',
  stream_order: '',
  frames: 41928,
  fps_num: 30000,
  fps_den: 1001,
  moving: 13280,
  combed: 5065,
  left_tff: 1267,
  left_bff: 4963,
  fallback: 2146,
  cadence: 0.69,
  jitter: 1.45,
  strip: 'TTTT',
  stretches: [],
  seconds: 18,
  chunk: 30,
  version: 1,
  ...over,
})

const step = (name: string, category: FilterStep['category'] = 'field'): FilterStep => ({
  category,
  name,
  script: category === 'crop' || category === 'resize' ? '' : `# ${name}`,
  enabled: true,
})

const video = (filters: FilterStep[], over: Partial<VideoSettings> = {}): VideoSettings => ({
  source_filter: 'ffms2',
  crop: { left: 0, top: 0, right: 0, bottom: 0 },
  resize: null,
  filters,
  custom: null,
  pulldown: false,
  ...over,
})

test('stripCells: each cell shows the most combed of what it covers, with its times', () => {
  const cells = stripCells(report({ strip: 'TT.I' + 'P'.repeat(4) }), 4)
  assert.deepEqual(
    cells.map((c) => c.kind.id),
    ['T', 'I', 'P', 'P'],
  )
  assert.equal(cells[1].from.toFixed(3), (2 * 1.001).toFixed(3)) // 2 chunks of 30 frames at 29.97
  assert.equal(stripCells(report({ strip: 'TIP' }), 10).length, 3) // never wider than the strip
  assert.deepEqual(stripCells(report({ strip: '' }), 10), [])
})

test('stretchTimes: the stretches left combed as times', () => {
  const r = report({
    stretches: [
      [7240, 7480, 35],
      [30000, 30000, 1],
    ],
  })
  assert.deepEqual(stretchTimes(r), ['4:02–4:10 (35 frames)', '16:41 (1 frame)'])
  assert.equal(stretchTimes(r, 1).length, 1)
})

test('applyFieldFix: the Field steps make way for the scan’s, first in the chain', () => {
  const fix: FieldScanFix = {
    step: step('Field scan: IVTC + QTGMC'),
    pulldown: true,
    source_filter: 'bestsource',
    applied: false,
  }
  const before = video([step('Bwdif'), step('Crop', 'crop'), step('Resize', 'resize'), step('Invert', 'custom')])
  const after = applyFieldFix(before, fix)
  assert.deepEqual(
    after.filters.map((s) => s.name),
    ['Field scan: IVTC + QTGMC', 'Crop', 'Resize', 'Invert'],
  )
  assert.equal(after.pulldown, true)
  assert.equal(after.source_filter, 'bestsource')
  assert.equal(before.filters.length, 4) // not changed in place
  assert.equal(
    fixChanges(before, fix),
    'Apply adds Field scan: IVTC + QTGMC first in the chain, removes Bwdif, turns on Apply pulldown, switches the source filter to BestSource.',
  )
  const none: FieldScanFix = { step: null, pulldown: false, source_filter: 'ffms2', applied: false }
  assert.deepEqual(
    applyFieldFix(before, none).filters.map((s) => s.name),
    ['Crop', 'Resize', 'Invert'],
  )
  assert.equal(fixChanges(before, none), 'Apply removes Bwdif.')
})
