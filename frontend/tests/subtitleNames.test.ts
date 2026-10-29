import assert from 'node:assert/strict'
import { test } from 'node:test'
import { subtitleName } from '../src/lib/format.ts'

// The same table as tests/test_template.py's (the server names subtitles alike for templates).
const NAMES: [string, { forced?: boolean; hearing_impaired?: boolean; commentary?: boolean }, string][] = [
  ['en', {}, 'English'],
  ['en', { forced: true }, 'English (Forced)'],
  ['en', { hearing_impaired: true }, 'English (SDH)'],
  ['en', { forced: true, hearing_impaired: true, commentary: true }, 'English (Forced) (SDH) (Commentary)'],
  ['es-419', { hearing_impaired: true }, 'Spanish (Latin America) (SDH)'],
  ['es-ES', {}, 'Spanish (Spain)'],
  ['fr-CA', {}, 'French (Canada)'],
  ['zh-Hans', {}, 'Chinese (Simplified)'],
  ['yue', {}, 'Cantonese'],
  ['pt-BR', {}, 'Portuguese (Brazil)'],
  ['ja', { commentary: true }, 'Japanese (Commentary)'],
  ['und', {}, 'Unknown'],
  ['', {}, 'Unknown'],
]

test('subtitles are named from their language and flags', () => {
  for (const [language, flags, name] of NAMES) assert.equal(subtitleName(language, flags), name, language)
})
