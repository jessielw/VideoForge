<script lang="ts">
  // One input slot on the New jobs page: a list of files/folders with Browse, remove and clear; files can be
  // dropped on it (in the window) or their paths pasted into it. A long list scrolls inside its box.
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import ListXIcon from '@lucide/svelte/icons/list-x'
  import XIcon from '@lucide/svelte/icons/x'
  import type { Snippet } from 'svelte'
  import { Button } from '$lib/components/ui/button'
  import { pathDrop } from '../lib/dropPaths.svelte'
  import { basename } from '../lib/format'
  import FileBrowser from './FileBrowser.svelte'
  import Tip from './Tip.svelte'

  let {
    label,
    hint,
    paths = $bindable([]),
    extensions = [],
    mode = 'files',
    actions,
  }: {
    label: string
    hint: string
    paths?: string[]
    extensions?: string[]
    mode?: 'files' | 'folder'
    actions?: Snippet
  } = $props()

  let browsing = $state(false)
  // Shown in the order a person reads names (E2 before E10), whatever order they were added in.
  const byName = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
  const shown = $derived(mode === 'files' ? [...paths].sort((a, b) => byName.compare(basename(a), basename(b))) : paths)

  function add(picked: string[]) {
    browsing = false
    if (!picked.length) return
    if (mode === 'folder') {
      paths = picked.slice(0, 1)
      return
    }
    const known = new Set(paths.map((p) => p.toLowerCase()))
    paths = [...paths, ...picked.filter((p) => !known.has(p.toLowerCase()))]
  }
</script>

<div
  class="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 @min-[40rem]/import:grid-cols-[8rem_minmax(0,1fr)_auto]"
>
  <div class="col-span-2 pt-1.5 text-sm text-muted-foreground @min-[40rem]/import:col-span-1">
    {label}{#if paths.length > 1}<span class="tabular-nums">{` · ${paths.length}`}</span>{/if}
  </div>
  <Tip class="grid min-w-0" text="Paste paths here (Explorer: select, Ctrl+Shift+C, then Ctrl+V)">
    <div
      class="flex max-h-24 min-h-8 min-w-0 flex-wrap gap-1.5 overflow-y-auto rounded-lg border border-input px-2 py-1 outline-none focus-visible:border-ring
      focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
      role={paths.length ? 'list' : 'group'}
      aria-label={label}
      use:pathDrop={{ rule: { mode: mode === 'folder' ? 'folder' : 'files', extensions, label }, accept: add }}
    >
      {#each shown as p (p)}
        <Tip class="min-w-0 max-w-full" text={p}>
          <span
            class="flex min-w-0 max-w-full items-center gap-1 rounded-md bg-muted py-0.5 pr-1 pl-2 text-xs break-all"
            role="listitem"
          >
            {basename(p)}{p.match(/[\\/]$/) || !p.match(/\.[a-z0-9]+$/i) ? '\\' : ''}
            <button
              class="rounded-sm text-muted-foreground hover:text-destructive"
              onclick={() => (paths = paths.filter((x) => x !== p))}
              aria-label="Remove"
            >
              <XIcon class="size-3" />
            </button>
          </span>
        </Tip>
      {:else}
        <span class="py-0.5 text-xs text-muted-foreground">{hint}</span>
      {/each}
    </div>
  </Tip>
  <div class="flex gap-2">
    <Button variant="outline" onclick={() => (browsing = true)}><FolderOpenIcon />Browse…</Button>
    {#if mode === 'files' && paths.length}
      <Tip text={`Clear all ${label.toLowerCase()}`}>
        <Button
          variant="outline"
          size="icon"
          onclick={() => (paths = [])}
          aria-label={`Clear all ${label.toLowerCase()}`}
        >
          <ListXIcon />
        </Button>
      </Tip>
    {/if}
    {@render actions?.()}
  </div>
</div>

{#if browsing}
  <FileBrowser title={label} {mode} {extensions} onpick={add} onclose={() => (browsing = false)} />
{/if}
