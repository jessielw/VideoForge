<script lang="ts">
  // Browses the server's file system (the browser can't hand us real paths).
  // mode "files": tick files and/or folders; mode "folder": choose one folder.
  import { onMount } from 'svelte'
  import { api } from '../lib/api'
  import { bytes } from '../lib/format'
  import type { DirListing } from '../lib/types'
  import Icon from './Icon.svelte'

  let {
    title,
    mode = 'files',
    extensions = [],
    start = '',
    onpick,
    onclose,
  }: {
    title: string
    mode?: 'files' | 'folder'
    extensions?: string[]
    start?: string
    onpick: (paths: string[]) => void
    onclose: () => void
  } = $props()

  let roots = $state<string[]>([])
  let listing = $state<DirListing | null>(null)
  let pathInput = $state('')
  let error = $state('')
  let picked = $state<string[]>([])

  async function open(path: string) {
    error = ''
    try {
      listing = await api.list(path, extensions)
      pathInput = listing.path
      api.saveSettings({ last_dir: listing.path }).catch(() => {})
    } catch (e) {
      error = String(e instanceof Error ? e.message : e)
    }
  }

  onMount(async () => {
    roots = await api.roots()
    const settings = await api.settings().catch(() => ({ last_dir: '', output_dir: '' }))
    await open(start || settings.last_dir || roots[0] || 'C:\\')
    if (!listing && roots[0]) await open(roots[0])
  })

  function toggle(path: string) {
    picked = picked.includes(path) ? picked.filter(p => p !== path) : [...picked, path]
  }

  function confirm() {
    if (mode === 'folder') {
      if (listing) onpick([listing.path])
    } else {
      onpick(picked.length ? picked : listing ? [listing.path] : [])
    }
  }

  function onkey(e: KeyboardEvent) {
    if (e.key === 'Escape') onclose()
  }
</script>

<svelte:window onkeydown={onkey} />

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" role="presentation" onclick={onclose}>
  <div
    class="panel flex h-[80vh] w-full max-w-3xl flex-col shadow-2xl"
    role="dialog"
    aria-label={title}
    tabindex="-1"
    onclick={e => e.stopPropagation()}
    onkeydown={() => {}}
  >
    <header class="flex items-center gap-2 border-b border-line p-3">
      <h2 class="font-semibold">{title}</h2>
      <select class="field ml-auto" onchange={e => open((e.target as HTMLSelectElement).value)}>
        {#each roots as r (r)}<option value={r} selected={listing?.path.startsWith(r)}>{r}</option>{/each}
      </select>
    </header>

    <div class="flex items-center gap-2 border-b border-line p-2">
      <button class="btn-ghost" disabled={!listing?.parent} onclick={() => listing?.parent && open(listing.parent)} title="Up">
        <Icon name="up" />
      </button>
      <input
        class="field flex-1 font-mono text-xs"
        bind:value={pathInput}
        onkeydown={e => e.key === 'Enter' && open(pathInput)}
      />
    </div>

    {#if error}<div class="px-3 py-2 text-sm text-bad">{error}</div>{/if}

    <div class="min-h-0 flex-1 overflow-auto p-1">
      {#if listing}
        {#each listing.dirs as d (d.path)}
          <div class="flex items-center gap-2 rounded px-2 py-1 hover:bg-raised">
            {#if mode === 'files'}
              <input type="checkbox" checked={picked.includes(d.path)} onchange={() => toggle(d.path)} />
            {/if}
            <button class="flex flex-1 items-center gap-2 text-left" ondblclick={() => open(d.path)} onclick={() => open(d.path)}>
              <Icon name="folder" class="text-accent" />{d.name}
            </button>
          </div>
        {/each}
        {#if mode === 'files'}
          {#each listing.files as f (f.path)}
            <label class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-raised">
              <input type="checkbox" checked={picked.includes(f.path)} onchange={() => toggle(f.path)} />
              <Icon name="file" class="text-muted" />
              <span class="flex-1 truncate">{f.name}</span>
              <span class="text-xs text-muted">{bytes(f.size)}</span>
            </label>
          {/each}
          {#if !listing.dirs.length && !listing.files.length}
            <div class="p-4 text-center text-muted">Nothing here{extensions.length ? ` (${extensions.join(' ')})` : ''}</div>
          {/if}
        {/if}
      {/if}
    </div>

    <footer class="flex items-center gap-2 border-t border-line p-3">
      <span class="text-xs text-muted">
        {#if mode === 'files'}
          {picked.length ? `${picked.length} selected` : 'Nothing ticked: the current folder is used'}
        {:else}
          Choose the folder you're in
        {/if}
      </span>
      <button class="btn ml-auto" onclick={onclose}>Cancel</button>
      <button class="btn-primary" onclick={confirm}>{mode === 'folder' ? 'Use this folder' : 'Add'}</button>
    </footer>
  </div>
</div>
