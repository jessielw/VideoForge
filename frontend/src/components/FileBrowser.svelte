<script lang="ts">
  // Browses the server's file system (the browser can't hand us real paths).
  // mode "files": tick files and/or folders; mode "folder": choose one folder.
  // programs: list only programs (the server decides what one is on its OS), and one has to be ticked,
  // unless orFolder: then the folder you're in will do (DEE's split encoders are a folder of programs).
  // Folders can be made here, and one made here deleted again while it's empty: the undo for a mistake.
  // Other file work belongs in a file manager (the server only deletes empty folders).
  import { onMount } from 'svelte'
  import { api } from '../lib/api'
  import { bytes } from '../lib/format'
  import type { DirListing } from '../lib/types'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import FileIcon from '@lucide/svelte/icons/file'
  import FolderIcon from '@lucide/svelte/icons/folder'
  import FolderPlusIcon from '@lucide/svelte/icons/folder-plus'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import Tip from './Tip.svelte'

  let {
    title,
    mode = 'files',
    extensions = [],
    programs = false,
    orFolder = false,
    start = '',
    onpick,
    onclose,
  }: {
    title: string
    mode?: 'files' | 'folder'
    extensions?: string[]
    programs?: boolean
    orFolder?: boolean
    start?: string
    onpick: (paths: string[]) => void
    onclose: () => void
  } = $props()

  let roots = $state<string[]>([])
  let listing = $state<DirListing | null>(null)
  let pathInput = $state('')
  let error = $state('')
  let picked = $state<string[]>([])
  let newName = $state<string | null>(null) // the new folder's name while one is being made
  let made = $state<string[]>([]) // folders made here: only these offer Delete
  let deleting = $state<{ name: string; path: string } | null>(null)
  let busy = $state(false)

  const message = (e: unknown) => String(e instanceof Error ? e.message : e)

  async function open(path: string) {
    error = ''
    try {
      listing = await api.list(path, extensions, programs)
      pathInput = listing.path
      api.saveSettings({ last_dir: listing.path }).catch(() => {})
    } catch (e) {
      error = message(e)
    }
  }

  async function makeDir() {
    if (!listing || !newName?.trim()) return
    busy = true
    try {
      const dir = await api.makeDir(listing.path, newName)
      made = [...made, dir.path]
      newName = null
      // Picking a folder: go into the new one, ready to use; picking files: it shows in the list.
      await open(mode === 'folder' ? dir.path : listing.path)
    } catch (e) {
      error = message(e)
    } finally {
      busy = false
    }
  }

  async function removeDir() {
    if (!deleting || !listing) return
    const { path } = deleting
    busy = true
    try {
      await api.removeDir(path)
      picked = picked.filter((p) => p !== path)
      made = made.filter((p) => p !== path)
      deleting = null
      await open(listing.path)
    } catch (e) {
      deleting = null
      error = message(e)
    } finally {
      busy = false
    }
  }

  onMount(async () => {
    roots = await api.roots()
    const settings = await api.settings().catch(() => ({ last_dir: '', output_dir: '' }))
    await open(start || settings.last_dir || roots[0] || 'C:\\')
    if (!listing && roots[0]) await open(roots[0])
  })

  function toggle(path: string) {
    picked = picked.includes(path) ? picked.filter((p) => p !== path) : [...picked, path]
  }

  function confirm() {
    if (mode === 'folder') {
      if (listing) onpick([listing.path])
    } else {
      onpick(picked.length ? picked : listing ? [listing.path] : [])
    }
  }
</script>

<Dialog.Root open onOpenChange={(o) => !o && onclose()}>
  <Dialog.Content class="flex h-[80vh] flex-col gap-0 p-0 sm:max-w-3xl" showCloseButton={false} aria-label={title}>
    <header class="flex items-center gap-2 border-b p-3">
      <Dialog.Title>{title}</Dialog.Title>
      <NativeSelect
        class="ml-auto"
        aria-label="Drive or folder"
        onchange={(e) => open((e.target as HTMLSelectElement).value)}
      >
        {#each roots as r (r)}<option value={r} selected={listing?.path.startsWith(r)}>{r}</option>{/each}
      </NativeSelect>
    </header>

    <div class="flex items-center gap-2 border-b p-2">
      <Tip text="Up">
        <Button
          variant="ghost"
          size="icon"
          disabled={!listing?.parent}
          onclick={() => listing?.parent && open(listing.parent)}
          aria-label="Up"
        >
          <ArrowUpIcon />
        </Button>
      </Tip>
      <Input
        class="flex-1 font-mono text-xs"
        aria-label="Path"
        bind:value={pathInput}
        onkeydown={(e) => e.key === 'Enter' && open(pathInput)}
      />
      <Tip text="New folder">
        <Button variant="ghost" size="icon" disabled={!listing} onclick={() => (newName = '')} aria-label="New folder">
          <FolderPlusIcon />
        </Button>
      </Tip>
    </div>

    {#if error}<div class="px-3 py-2 text-sm text-destructive">{error}</div>{/if}

    <div class="min-h-0 flex-1 overflow-auto p-1">
      {#if listing}
        {#if newName !== null}
          <form
            class="flex items-center gap-2 px-2 py-1"
            onsubmit={(e) => {
              e.preventDefault()
              makeDir()
            }}
          >
            <FolderPlusIcon class="size-4 text-primary" />
            <!-- svelte-ignore a11y_autofocus -->
            <Input
              class="h-7 flex-1"
              aria-label="New folder name"
              placeholder="New folder name"
              autofocus
              bind:value={newName}
              onkeydown={(e) => {
                if (e.key === 'Escape') {
                  e.stopPropagation() // closes this, not the browser
                  newName = null
                }
              }}
            />
            <Button type="submit" size="sm" disabled={busy || !newName.trim()}>Create</Button>
            <Button variant="ghost" size="sm" onclick={() => (newName = null)}>Cancel</Button>
          </form>
        {/if}
        {#each listing.dirs as d (d.path)}
          <div class="group flex items-center gap-2 rounded-md px-2 py-1 hover:bg-accent">
            {#if mode === 'files'}
              <Checkbox
                checked={picked.includes(d.path)}
                onCheckedChange={() => toggle(d.path)}
                aria-label="Pick {d.name}"
              />
            {/if}
            <button class="flex flex-1 items-center gap-2 text-left" onclick={() => open(d.path)}>
              <FolderIcon class="size-4 text-primary" />{d.name}
            </button>
            {#if made.includes(d.path)}
              <Tip text="Delete {d.name}">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  class="opacity-0 group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100"
                  onclick={() => ((error = ''), (deleting = d))}
                  aria-label="Delete {d.name}"
                >
                  <Trash2Icon />
                </Button>
              </Tip>
            {/if}
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
            <div class="p-4 text-center text-muted-foreground">
              Nothing here{programs ? ' (programs)' : extensions.length ? ` (${extensions.join(' ')})` : ''}
            </div>
          {/if}
        {/if}
      {/if}
    </div>

    <footer class="flex items-center gap-2 border-t p-3">
      <span class="text-xs text-muted-foreground">
        {#if mode === 'files'}
          {picked.length
            ? `${picked.length} selected`
            : programs
              ? orFolder
                ? 'Tick the program, or use this folder if it holds the split encoders'
                : 'Tick the program'
              : 'Nothing ticked: the current folder is used'}
        {:else}
          Choose the folder you're in
        {/if}
      </span>
      <Button variant="outline" class="ml-auto" onclick={onclose}>Cancel</Button>
      <Button disabled={programs && !orFolder && !picked.length} onclick={confirm}
        >{mode === 'folder' || (orFolder && !picked.length) ? 'Use this folder' : 'Add'}</Button
      >
    </footer>
  </Dialog.Content>
</Dialog.Root>

{#if deleting}
  {@const { name, path } = deleting}
  <Dialog.Root open onOpenChange={(o) => !o && (deleting = null)}>
    <Dialog.Content class="sm:max-w-md">
      <Dialog.Header>
        <Dialog.Title>Delete {name}?</Dialog.Title>
        <Dialog.Description class="font-mono text-xs break-all">{path}</Dialog.Description>
      </Dialog.Header>
      <p class="text-sm text-muted-foreground">It's empty, so no files are deleted.</p>
      <Dialog.Footer>
        <Button variant="outline" onclick={() => (deleting = null)}>Cancel</Button>
        <Button variant="destructive" disabled={busy} onclick={removeDir}><Trash2Icon />Delete</Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}
