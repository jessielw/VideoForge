// Dropped or pasted file paths for path fields. A page in a normal browser never learns where a
// dropped file lives; in `videoforge serve --window` pywebview does and hands the paths to
// `window.videoforgeDropped` (src/videoforge/desktop.py). Pasting paths (Explorer: Copy as path)
// works everywhere. Every field takes paths through the `pathDrop` action.
import type { Action } from 'svelte/action'
import { toast } from 'svelte-sonner'
import { api } from './api'
import { basename } from './format'

declare global {
  interface Window {
    videoforgeDesktop?: boolean
    videoforgeDropped?: (paths: string[]) => void
  }
}

export const drops = $state({ desktop: false })

// The field a drop landed on, waiting for the window's paths.
let pending: ((paths: string[]) => void) | null = null

const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files')

export function installDrops() {
  drops.desktop = !!window.videoforgeDesktop
  window.addEventListener('videoforge:desktop', () => (drops.desktop = true))
  window.videoforgeDropped = paths => {
    const take = pending
    pending = null
    if (take && paths.length) take(paths)
  }
  // Outside a field a dropped file must not replace the app with the file.
  const block = (e: DragEvent) => {
    if (!hasFiles(e) || e.defaultPrevented) return
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'none'
  }
  window.addEventListener('dragover', block)
  window.addEventListener('drop', block)
}

/** Paths in pasted text: one per line, quotes (Copy as path) and file:// URIs undone. */
export function pastedPaths(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map(line => {
      let p = line.trim().replace(/^"(.*)"$/, '$1').trim()
      if (/^file:\/\//i.test(p)) {
        p = decodeURIComponent(p.replace(/^file:\/\/(localhost)?/i, ''))
        if (/^\/[A-Za-z]:/.test(p)) p = p.slice(1).replaceAll('/', '\\')
      }
      return p
    })
    .filter(Boolean)
}

export interface PathRule {
  /** files: files and folders; file: files only; folder: a file stands for its folder */
  mode: 'files' | 'file' | 'folder'
  extensions?: string[]
  /** where the paths go, for the message about the ones left out */
  label: string
}

/** The paths that fit the rule (checked on the server); the others are named in a toast. */
export async function checkPaths(paths: string[], rule: PathRule): Promise<string[]> {
  let kinds
  try {
    kinds = await api.pathKinds(paths)
  } catch (e) {
    toast.error("Couldn't check the paths", { description: e instanceof Error ? e.message : String(e) })
    return []
  }
  const exts = (rule.extensions ?? []).map(x => x.toLowerCase())
  const ok: string[] = []
  const left: string[] = []
  for (const { path, kind } of kinds) {
    const name = basename(path) || path
    if (kind === 'missing') left.push(`${path}: not found`)
    else if (kind === 'outside') left.push(`${name}: outside the browsable folders (Settings)`)
    else if (rule.mode === 'folder') ok.push(kind === 'folder' ? path : path.replace(/[\\/][^\\/]*$/, ''))
    else if (kind === 'folder') {
      if (rule.mode === 'files') ok.push(path)
      else left.push(`${name}: a folder, not a file`)
    } else if (!exts.length || exts.some(x => name.toLowerCase().endsWith(x))) ok.push(path)
    else left.push(`${name}: not ${exts.join(' ')}`)
  }
  if (left.length) toast.warning(`Not added to ${rule.label}`, { description: left.join('\n') })
  return [...new Map(ok.map(p => [p.toLowerCase(), p])).values()]
}

export interface PathDropOptions {
  rule: PathRule
  accept: (paths: string[]) => void
  disabled?: boolean
}

// Shown on a field while files are dragged over it.
const OVER = ['ring-2', 'ring-primary/70', 'bg-primary/5']

/** Makes an element take dropped files (in the window) and pasted paths. It becomes focusable for pasting;
 * a paste into a text box inside it is left alone. */
export const pathDrop: Action<HTMLElement, PathDropOptions> = (node, initial) => {
  let opts = initial
  let depth = 0
  const clear = () => {
    depth = 0
    node.classList.remove(...OVER)
  }
  const take = async (paths: string[]) => {
    const ok = await checkPaths(paths, opts.rule)
    if (ok.length) opts.accept(ok)
  }

  const enter = (e: DragEvent) => {
    if (!hasFiles(e) || opts.disabled) return
    e.preventDefault()
    if (depth++ === 0) node.classList.add(...OVER)
  }
  const dragover = (e: DragEvent) => {
    if (!hasFiles(e) || opts.disabled) return
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }
  const leave = (e: DragEvent) => {
    if (hasFiles(e) && depth > 0 && --depth === 0) clear()
  }
  // Not stopped: the window's own drop handler on the document reads the paths.
  const drop = (e: DragEvent) => {
    if (!hasFiles(e) || opts.disabled) return
    e.preventDefault()
    clear()
    if (drops.desktop) pending = take
    else
      toast.info('A browser keeps dropped files’ paths to itself', {
        description:
          'Paste the paths instead (Explorer: select, Ctrl+Shift+C, then Ctrl+V here), use Browse…, ' +
          'or start VideoForge with `videoforge serve --window` to drop files.',
      })
  }
  const paste = (e: ClipboardEvent) => {
    if (opts.disabled) return
    const t = e.target as HTMLElement
    if (t !== node && t.closest('input, textarea, [contenteditable]')) return
    const paths = pastedPaths(e.clipboardData?.getData('text/plain') ?? '')
    if (!paths.length) return
    e.preventDefault()
    take(paths)
  }

  if (node.tabIndex < 0) node.tabIndex = 0
  const events = { dragenter: enter, dragover, dragleave: leave, drop, paste } as unknown as Record<string, EventListener>
  for (const [k, f] of Object.entries(events)) node.addEventListener(k, f)
  return {
    update: next => (opts = next),
    destroy: () => {
      for (const [k, f] of Object.entries(events)) node.removeEventListener(k, f)
    },
  }
}
