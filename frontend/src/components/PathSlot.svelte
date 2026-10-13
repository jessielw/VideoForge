<script lang="ts">
  // One input slot on the New jobs page: a list of files/folders with Browse and remove.
  import { basename } from '../lib/format'
  import FileBrowser from './FileBrowser.svelte'
  import Icon from './Icon.svelte'

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
  <div class="pt-1.5 text-sm text-muted">{label}</div>
  <div class="field min-h-8 flex flex-wrap gap-1.5">
    {#each paths as p (p)}
      <span class="flex items-center gap-1 rounded bg-raised px-2 py-0.5 text-xs" title={p}>
        {basename(p)}{p.match(/[\\/]$/) || !p.match(/\.[a-z0-9]+$/i) ? '\\' : ''}
        <button class="text-muted hover:text-bad" onclick={() => (paths = paths.filter(x => x !== p))} aria-label="Remove">
          <Icon name="x" size={12} />
        </button>
      </span>
    {:else}
      <span class="py-0.5 text-xs text-muted">{hint}</span>
    {/each}
  </div>
  <button class="btn" onclick={() => (browsing = true)}><Icon name="folder" />Browse…</button>
</div>

{#if browsing}
  <FileBrowser title={label} {mode} {extensions} onpick={add} onclose={() => (browsing = false)} />
{/if}
