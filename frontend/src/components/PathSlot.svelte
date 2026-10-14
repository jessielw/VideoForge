<script lang="ts">
  // One input slot on the New jobs page: a list of files/folders with Browse and remove.
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { basename } from '../lib/format'
  import FileBrowser from './FileBrowser.svelte'

  let {
    label,
    hint,
    paths = $bindable([]),
    extensions = [],
    mode = 'files',
  }: { label: string; hint: string; paths?: string[]; extensions?: string[]; mode?: 'files' | 'folder' } = $props()

  let browsing = $state(false)

  function add(picked: string[]) {
    browsing = false
    if (mode === 'folder') {
      paths = picked.slice(0, 1)
      return
    }
    const known = new Set(paths.map(p => p.toLowerCase()))
    paths = [...paths, ...picked.filter(p => !known.has(p.toLowerCase()))]
  }
</script>

<div class="grid grid-cols-[8rem_1fr_auto] items-start gap-3">
  <div class="pt-1.5 text-sm text-muted-foreground">{label}</div>
  <div class="flex min-h-8 flex-wrap gap-1.5 rounded-lg border border-input px-2 py-1 dark:bg-input/30">
    {#each paths as p (p)}
      <span class="flex items-center gap-1 rounded-md bg-muted py-0.5 pr-1 pl-2 text-xs" title={p}>
        {basename(p)}{p.match(/[\\/]$/) || !p.match(/\.[a-z0-9]+$/i) ? '\\' : ''}
        <button
          class="rounded-sm text-muted-foreground hover:text-destructive"
          onclick={() => (paths = paths.filter(x => x !== p))}
          aria-label="Remove"
        >
          <XIcon class="size-3" />
        </button>
      </span>
    {:else}
      <span class="py-0.5 text-xs text-muted-foreground">{hint}</span>
    {/each}
  </div>
  <Button variant="outline" onclick={() => (browsing = true)}><FolderOpenIcon />Browse…</Button>
</div>

{#if browsing}
  <FileBrowser title={label} {mode} {extensions} onpick={add} onclose={() => (browsing = false)} />
{/if}
