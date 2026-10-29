import type { ImportAction } from './types'

// What an import will do, counted for the dialog: "2 new · 20 replace yours · 3 unchanged".
const WORDS: [ImportAction, string][] = [
  ['new', 'new'],
  ['replaced', 'replace yours'],
  ['unchanged', 'unchanged'],
  ['copy', 'numbered copies'],
]

export function importSummary(actions: ImportAction[]): string {
  return WORDS.map(([action, word]) => [actions.filter((a) => a === action).length, word] as const)
    .filter(([n]) => n)
    .map(([n, word]) => (word === 'numbered copies' && n === 1 ? '1 numbered copy' : `${n} ${word}`))
    .join(' · ')
}
