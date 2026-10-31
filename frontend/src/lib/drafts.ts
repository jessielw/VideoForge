// Per-tab drafts survive navigation and refresh. Memory still works when storage is unavailable.
export function createDraftStore(storage?: Pick<Storage, 'getItem' | 'setItem'>) {
  const memory = new Map<string, unknown>()
  return {
    read<T>(key: string): T | null {
      if (memory.has(key)) return structuredClone(memory.get(key)) as T
      try {
        const saved = JSON.parse(storage?.getItem(`videoforge.draft.${key}`) ?? 'null')
        return saved?.version === 1 ? (saved.value as T) : null
      } catch {
        return null
      }
    },
    write(key: string, value: unknown): void {
      const snapshot = structuredClone(value)
      memory.set(key, snapshot)
      try {
        storage?.setItem(`videoforge.draft.${key}`, JSON.stringify({ version: 1, value: snapshot }))
      } catch {
        /* memory fallback */
      }
    },
  }
}

function session(): Storage | undefined {
  try {
    return globalThis.sessionStorage
  } catch {
    return undefined
  }
}
export const drafts = createDraftStore(session())

// After the whole configuration changed (an import, a reset, another profile): the editors' drafts named its
// templates and presets, so they start again from its defaults. The New jobs form keeps its files.
export function forgetConfigurationDrafts(templates = true): void {
  if (templates) drafts.write('templates', null)
  const newJobs = drafts.read<Record<string, unknown>>('new-jobs')
  if (newJobs)
    drafts.write('new-jobs', { ...newJobs, ruleSet: '', templateName: null, encoder: null, container: '', output: [] })
}
