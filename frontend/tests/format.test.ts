import assert from 'node:assert/strict'
import { test } from 'node:test'
import { factsText, issueCounts, jobFacts, needsDvNote, plural, sizeLabel } from '../src/lib/format.ts'
import { factJob } from './factJob.ts'

test('jobFacts: the facts line in order, only what the job has', () => {
  assert.deepEqual(
    jobFacts(
      factJob({
        custom_script: true,
        source_facts: { resolution: '3840x2160', duration_ms: null, hdr: [], interlaced: true },
      }),
    ).map((f) => f.text),
    ['3840×2160', 'interlaced', 'x265', 'custom script', '2 audio', '3 subs'],
  )
  assert.deepEqual(
    jobFacts(factJob({ source_facts: null })).map((f) => f.key),
    ['encoder', 'audio', 'subs'],
  )
})

test('factsText joins a facts line with its HDR tags, and needsDvNote spots a profile 7 tag with its layer unread', () => {
  const facts = jobFacts(factJob())
  assert.equal(factsText(facts), '1920×1080 · 25:00 · HDR10 · HLG · x265 · 2 audio · 3 subs')
  assert.equal(needsDvNote(facts), false)
  const dv7 = jobFacts(factJob({ source_facts: { ...factJob().source_facts!, hdr: ['Dolby Vision 7?'] } }))
  assert.equal(needsDvNote(dv7), true)
})

test('a plain size reads with a times sign; a size class stays as it is', () => {
  assert.equal(sizeLabel('1920x1040'), '1920×1040')
  assert.equal(sizeLabel('3840x2076'), '3840×2076')
  assert.equal(sizeLabel('1080p'), '1080p')
  assert.equal(sizeLabel(''), '')
})

test("a job's issues read as counts of errors and warnings, leaving out a kind with none", () => {
  assert.deepEqual(issueCounts({ block: 1, warn: 2 }), ['1 error', '2 warnings'])
  assert.deepEqual(issueCounts({ block: 3, warn: 1 }), ['3 errors', '1 warning'])
  assert.deepEqual(issueCounts({ block: 0, warn: 4 }), ['4 warnings'])
  assert.deepEqual(issueCounts({ block: 0, warn: 0 }), [])
})

test('plural adds an s for anything but one', () => {
  assert.equal(plural(0, 'job'), '0 jobs')
  assert.equal(plural(1, 'job'), '1 job')
  assert.equal(plural(2, 'job'), '2 jobs')
})
