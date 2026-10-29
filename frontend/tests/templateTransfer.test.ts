import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  downloadTemplates,
  MAX_TEMPLATE_BYTES,
  templateBundle,
  templateFilename,
  templateScripts,
} from '../src/lib/templateTransfer.ts'
import type { Template } from '../src/lib/types.ts'

test('exports only template names and data, keeping settings embedded', () => {
  const data = { encoder: { encoder: 'x265', options: { 'aq-mode': '3' } } } as unknown as Template
  const bundle = templateBundle([{ name: 'Group', data, builtin: true } as { name: string; data: Template }])
  assert.deepEqual(bundle, { format: 'videoforge.templates', version: 1, templates: [{ name: 'Group', data }] })
})

test('download filenames cannot contain path separators or invalid Windows characters', () => {
  assert.equal(templateFilename('../A\\B:setup?'), '.._A_B_setup_.videoforge.json')
  assert.equal(templateFilename('日本語'), '日本語.videoforge.json')
  assert.equal(templateFilename('...'), 'templates.videoforge.json')
  assert.ok(templateFilename('A'.repeat(100)).length < 100)
})

test('script preview includes disabled filters and a custom body', () => {
  const data = {
    video: {
      custom: 'clip = src',
      filters: [
        { name: 'Crop', script: '', enabled: true },
        { name: 'Disabled Python', script: 'clip = process(clip)', enabled: false },
      ],
    },
  } as unknown as Template
  assert.deepEqual(templateScripts(data), [
    { name: 'Custom script body', script: 'clip = src' },
    { name: 'Disabled Python', script: 'clip = process(clip)' },
  ])
})

test('export refuses a formatted file larger than the import limit', () => {
  const data = { video: { custom: 'x'.repeat(MAX_TEMPLATE_BYTES) } } as unknown as Template
  assert.throws(() => downloadTemplates(templateBundle([{ name: 'Large', data }]), 'large.json'), /exceeds 5 MiB/)
})
