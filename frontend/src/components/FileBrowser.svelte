<script lang="ts">
  // Browses the server's file system (the browser can't hand us real paths).
  // mode "files": tick files and/or folders; mode "folder": choose one folder.
  import { onMount } from 'svelte'
  import { api } from '../lib/api'
  import { bytes } from '../lib/format'
  import type { DirListing } from '../lib/types'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import FileIcon from '@lucide/svelte/icons/file'
  import FolderIcon from '@lucide/svelte/icons/folder'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'

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
</script>

<Dialog.Root open onOpenChange={o => !o && onclose()}>
  <Dialog.Content class="flex h-[80vh] flex-col gap-0 p-0 sm:max-w-3xl" showCloseButton={false} aria-label={title}>
    <header class="flex items-center gap-2 border-b p-3">
      <Dialog.Title>{title}</Dialog.Title>
      <NativeSelect class="ml-auto" aria-label="Drive or folder" onchange={e => open((e.target as HTMLSelectElement).value)}>
        {#each roots as r (r)}<option value={r} selected={listing?.path.startsWith(r)}>{r}</option>{/each}
      </NativeSelect>
    </header>

    <div class="flex items-center gap-2 border-b p-2">
      <Button
        variant="ghost"
        size="icon"
        disabled={!listing?.parent}
        onclick={() => listing?.parent && open(listing.parent)}
        title="Up"
        aria-label="Up"
      >
        <ArrowUpIcon />
      </Button>
      <Input class="flex-1 font-mono text-xs" aria-label="Path" bind:value={pathInput} onkeydown={e => e.key === 'Enter' && open(pathInput)} />
    </div>

    {#if error}<div class="px-3 py-2 text-sm text-destructive">{error}</div>{/if}

    <div class="min-h-0 flex-1 overflow-auto p-1">
      {#if listing}
        {#each listing.dirs as d (d.path)}
          <div class="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-accent">
            {#if mode === 'files'}
              <Checkbox checked={picked.includes(d.path)} onCheckedChange={() => toggle(d.path)} aria-label="Pick {d.name}" />
            {/if}
            <button class="flex flex-1 items-center gap-2 text-left" onclick={() => open(d.path)}>
              <FolderIcon class="size-4 text-primary" />{d.name}
            </button>
          </div>
        {/each}
        {#if mode === 'files'}
          {#each listing.files as f (f.path)}
            <label class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 hover:bg-accent">
              <Checkbox checked={picked.includes(f.path)} onCheckedChange={() => toggle(f.path)} />
              <FileIcon class="size-4 text-muted-foreground" />
              <span class="flex-1 truncate">{f.name}</span>
              <span class="text-xs text-muted-foreground">{bytes(f.size)}</span>
            </label>
          {/each}
          {#if !listing.dirs.length && !listing.files.length}
            <div class="p-4 text-center text-muted-foreground">Nothing here{extensions.length ? ` (${extensions.join(' ')})` : ''}</div>
          {/if}
        {/if}
      {/if}
    </div>

    <footer class="flex items-center gap-2 border-t p-3">
      <span class="text-xs text-muted-foreground">
        {#if mode === 'files'}
          {picked.length ? `${picked.length} selected` : 'Nothing ticked: the current folder is used'}
        {:else}
          Choose the folder you're in
        {/if}
      </span>
      <Button variant="outline" class="ml-auto" onclick={onclose}>Cancel</Button>
      <Button onclick={confirm}>{mode === 'folder' ? 'Use this folder' : 'Add'}</Button>
    </footer>
  </Dialog.Content>
</Dialog.Root>
