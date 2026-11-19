<script lang="ts">
  // Browses the server's file system (the browser can't hand us real paths).
  // mode "files": tick files and/or folders; mode "folder": choose one folder.
  // programs: list only programs (the server decides what one is on its OS), and one has to be ticked,
  // unless orFolder: then the folder you're in will do (DEE's split encoders are a folder of programs).
  // Folders can be made here, and one made here deleted again while it's empty: the undo for a mistake.
  // Other file work belongs in a file manager (the server only deletes empty folders).
  // Ticking: a click (on a file's row or any box) toggles one, Shift+click ticks or unticks the range
  // from the last one clicked, a mouse press dragged over rows ticks or unticks them the way the first
  // one went, and Ctrl+A or the All box ticks every file here (not the folders).
  import { onMount } from 'svelte'
  import { api } from '../lib/api'
  import { bytes } from '../lib/format'
  import { pickAll, pickClick, pickRange } from '../lib/pickPaths'
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
  let anchor = $state<string | null>(null) // the last path clicked: Shift+click ticks from here
  // A mouse press ticks on the way down and drags over rows from there; its click then does nothing.
  let drag = $state<{ from: string; on: boolean; base: string[] } | null>(null)
  let pressed: string | null = null
  let newName = $state<string | null>(null) // the new folder's name while one is being made
  let made = $state<string[]>([]) // folders made here: only these offer Delete
  let deleting = $state<{ name: string; path: string } | null>(null)
  let busy = $state(false)

  const message = (e: unknown) => String(e instanceof Error ? e.message : e)

  async function open(path: string) {
    error = ''
    try {
      listing = await api.list(path, extensions, programs)
      anchor = null
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

  // The rows as shown, in the order Shift+click ranges over; picking one program means no ranges or All.
  const order = $derived(listing && mode === 'files' ? [...listing.dirs, ...listing.files].map((x) => x.path) : [])
  const files = $derived(listing && mode === 'files' && !programs ? listing.files.map((f) => f.path) : [])
  const filesPicked = $derived.by(() => {
    const has = new Set(picked)
    return files.filter((p) => has.has(p)).length
  })

  function click(path: string, e: MouseEvent) {
    e.stopPropagation() // a box's click is the row's too
    e.preventDefault() // and the box doesn't toggle itself: it shows what's picked
    if (e.detail > 0 && pressed === path) return void (pressed = null) // the press did it (detail 0: a key)
    picked = pickClick(picked, order, path, anchor, e.shiftKey && !programs)
    anchor = path
  }

  // Touch keeps its drag for scrolling, so only a mouse paints; a single program has nothing to drag over.
  function press(path: string, e: PointerEvent) {
    pressed = null
    if (e.pointerType !== 'mouse' || e.button !== 0 || e.shiftKey || programs) return
    pressed = path
    const on = !picked.includes(path)
    drag = { from: path, on, base: picked }
    picked = pickRange(picked, order, path, path, on)
    anchor = path
  }

  function over(path: string) {
    if (drag) picked = pickRange(drag.base, order, drag.from, path, drag.on)
  }

  function keys(e: KeyboardEvent) {
    const typing = e.target instanceof HTMLElement && e.target.closest('input, textarea, [contenteditable]')
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'a' || e.altKey || typing || !files.length) return
    e.preventDefault()
    picked = pickAll(picked, files)
  }

  function confirm() {
    if (mode === 'folder') {
      if (listing) onpick([listing.path])
    } else {
      onpick(picked.length ? picked : listing ? [listing.path] : [])
    }
  }
</script>

<svelte:window onpointerup={() => (drag = null)} onblur={() => (drag = null)} />

<Dialog.Root open onOpenChange={(o) => !o && onclose()}>
  <Dialog.Content
    class="flex h-[80vh] flex-col gap-0 p-0 sm:max-w-3xl"
    showCloseButton={false}
    aria-label={title}
    onkeydown={keys}
  >
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
        {#if files.length > 1}
          <div class="flex items-center gap-2 border-b px-2 pt-1 pb-2 text-sm text-muted-foreground select-none">
            <Checkbox
              checked={filesPicked === files.length}
              indeterminate={filesPicked > 0 && filesPicked < files.length}
              onclick={(e: MouseEvent) => {
                e.preventDefault()
                picked = pickAll(picked, files)
              }}
              aria-label="Pick all files"
            />
            <span class="flex-1">All {files.length} files</span>
            <span class="hidden text-xs sm:inline">Drag or Shift+click ticks a range · Ctrl+A ticks all</span>
          </div>
        {/if}
        {#each listing.dirs as d (d.path)}
          <div
            class="group flex items-center gap-2 rounded-md px-2 py-1 select-none hover:bg-accent"
            role="presentation"
            onpointerenter={() => over(d.path)}
          >
            {#if mode === 'files'}
              <Checkbox
                checked={picked.includes(d.path)}
                onpointerdown={(e: PointerEvent) => press(d.path, e)}
                onclick={(e: MouseEvent) => click(d.path, e)}
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
            <!-- The box is the keyboard's way to tick; the row is a bigger target for the mouse. -->
            <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
            <div
              class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 select-none hover:bg-accent"
              onpointerdown={(e) => press(f.path, e)}
              onpointerenter={() => over(f.path)}
              onclick={(e) => click(f.path, e)}
            >
              <Checkbox
                checked={picked.includes(f.path)}
                onclick={(e: MouseEvent) => click(f.path, e)}
                aria-label="Pick {f.name}"
              />
              <FileIcon class="size-4 text-muted-foreground" />
              <span class="flex-1 truncate">{f.name}</span>
              <span class="text-xs text-muted-foreground">{bytes(f.size)}</span>
            </div>
          {/each}
          {#if !listing.dirs.length && !listing.files.length}
            <div class="p-4 text-center text-muted-foreground">
              {programs
                ? 'No programs here'
                : extensions.length
                  ? `No ${extensions.join(' ')} files here`
                  : 'Nothing here'}
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
                ? "Tick the program, or use this folder for DEE's split encoders."
                : 'Tick the program'
              : "With nothing ticked, Add uses the folder you're in."}
        {:else}
          Open the folder you want, then choose Use this folder.
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
