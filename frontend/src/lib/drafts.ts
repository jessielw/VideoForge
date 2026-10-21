// Per-tab drafts survive navigation and refresh. Memory still works when storage is unavailable.
export function createDraftStore(storage?: Pick<Storage, 'getItem' | 'setItem'>) {
  const memory = new Map<string, unknown>()
  return {
    read<T>(key: string): T | null {
      if (memory.has(key)) return structuredClone(memory.get(key)) as T
      try {
        const saved = JSON.parse(storage?.getItem(`videoforge.draft.${key}`) ?? 'null')
        return saved?.version === 1 ? saved.value as T : null
      } catch { return null }
    },
    write(key: string, value: unknown): void {
      const snapshot = structuredClone(value)
      memory.set(key, snapshot)
      try { storage?.setItem(`videoforge.draft.${key}`, JSON.stringify({ version: 1, value: snapshot })) } catch { /* memory fallback */ }
    },
  }
}

function session(): Storage | undefined {
  try { return globalThis.sessionStorage } catch { return undefined }
}
export const drafts = createDraftStore(session())
