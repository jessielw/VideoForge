// File paths headed for the New jobs page: pasted anywhere in the app, or picked with "Add files…". A browser
// never learns where a dropped file lives, so paths come from the clipboard. The page takes them from `pending`.
import { checkPaths, pastedPaths } from './dropPaths.svelte'
import { router } from './router.svelte'

export const SOURCE_EXTENSIONS = ['.mkv', '.mp4', '.m4v', '.m2ts', '.mts', '.ts']

class Incoming {
  pending = $state<string[]>([])

  /** Hands paths to the New jobs page (no duplicates, any case) and shows it. */
  add(paths: string[]): void {
    const known = new Set(this.pending.map((p) => p.toLowerCase()))
    this.pending = [...this.pending, ...paths.filter((p) => !known.has(p.toLowerCase()))]
    if (this.pending.length) router.go('new')
  }
}

export const incoming = new Incoming()

/** Whether every line looks like an absolute path, so ordinary text pasted outside a field is left alone. */
export function looksLikePaths(lines: string[]): boolean {
  return lines.length > 0 && lines.every((l) => /^([A-Za-z]:[\/]|\\|\/)/.test(l))
}

/** Window paste handler: pasted paths go to New jobs. A paste into a field, or one a slot already took, is left alone. */
export async function onWindowPaste(e: ClipboardEvent): Promise<void> {
  if (e.defaultPrevented) return
  const t = e.target as HTMLElement | null
  if (t?.closest('input, textarea, select, [contenteditable]')) return
  const lines = pastedPaths(e.clipboardData?.getData('text/plain') ?? '')
  if (!looksLikePaths(lines)) return
  e.preventDefault()
  const ok = await checkPaths(lines, { mode: 'files', extensions: SOURCE_EXTENSIONS, label: 'the new jobs' })
  if (ok.length) incoming.add(ok)
}
