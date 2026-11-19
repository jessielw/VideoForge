<script lang="ts">
  // Browses the server's file system (the browser can't hand us real paths).
  // mode "files": tick files and/or folders; mode "folder": choose one folder.
  // programs: list only programs (the server decides what one is on its OS), and one has to be ticked,
  // unless orFolder: then the folder you're in will do (DEE's split encoders are a folder of programs).
  // Folders can be made here, and one made here deleted again while it's empty: the undo for a mistake.
  // Other file work belongs in a file manager (the server only deletes empty folders).
  // Ticking: a click (on a file's row or any box) toggles one, Shift+click ticks or unticks the range
  // from the last one clicked, a mouse press dragged over rows ticks or unticks them the way the first
  // one went, and Ctrl+A or the All box ticks every file here (not the folders). The filter narrows the
  // rows to names with every word in them; ranges and Ctrl+A only take the rows it shows. The column
  // headers sort by name, date or size (folders stay first), remembered in this browser.
  // Keys on a row: arrows, Home and End move (Shift+arrows tick on the way), Space ticks, Enter opens a
  // folder or adds (the file under the cursor when nothing is ticked), Backspace or Alt+Up goes up.
  // KeyboardShortcuts lists them: keep it in step.
  import { onMount, tick } from 'svelte'
  import { api } from '../lib/api'
  import { filterEntries, sortEntries, type FileSort, type SortKey } from '../lib/fileList'
  import { bytes } from '../lib/format'
  import { pickAll, pickClick, pickRange } from '../lib/pickPaths'
  import type { DirListing } from '../lib/types'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import ChevronUpIcon from '@lucide/svelte/icons/chevron-up'
  import FileIcon from '@lucide/svelte/icons/file'
  import FolderIcon from '@lucide/svelte/icons/folder'
  import FolderPlusIcon from '@lucide/svelte/icons/folder-plus'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import SearchIcon from '@lucide/svelte/icons/search'
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
  let filter = $state('') // kept on Refresh, cleared on going to another folder
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
  let list = $state<HTMLElement | null>(null)

  const message = (e: unknown) => String(e instanceof Error ? e.message : e)

  const SORT_KEY = 'videoforge.fileSort'
  let sort = $state<FileSort>(savedSort())

  function savedSort(): FileSort {
    try {
      const v = JSON.parse(localStorage.getItem(SORT_KEY) ?? 'null')
      if (['name', 'mtime', 'size'].includes(v?.key)) return { key: v.key, desc: !!v.desc }
    } catch {
      /* storage blocked */
    }
    return { key: 'name', desc: false }
  }

  // A new column starts newest or biggest first (names A to Z); the same column again flips it.
  function sortBy(key: SortKey) {
    sort = sort.key === key ? { key, desc: !sort.desc } : { key, desc: key !== 'name' }
    try {
      localStorage.setItem(SORT_KEY, JSON.stringify(sort))
    } catch {
      /* storage blocked */
    }
  }

  const modified = (mtime: number) =>
    new Date(mtime * 1000).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })

  // focus: from the keyboard, put the cursor on this row once it's listed (true: the first row).
  async function open(path: string, focus?: string | true) {
    error = ''
    try {
      const next = await api.list(path, extensions, programs)
      if (next.path !== listing?.path) filter = ''
      listing = next
      anchor = null
      pathInput = listing.path
      api.saveSettings({ last_dir: listing.path }).catch(() => {})
      if (focus) {
        await tick()
        focusRow(focus === true ? null : focus)
      }
    } catch (e) {
      error = message(e)
    }
  }

  // The rows the keyboard moves over: each row's box, or a folder's name when choosing a folder.
  const rows = () => [...(list?.querySelectorAll<HTMLElement>('[data-row]') ?? [])]

  function focusRow(path: string | null) {
    const all = rows()
    ;(all.find((r) => r.dataset.row === path) ?? all[0])?.focus()
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
  const dirs = $derived(listing ? sortEntries(filterEntries(listing.dirs, filter), sort) : [])
  const shownFiles = $derived(
    listing && mode === 'files' ? sortEntries(filterEntries(listing.files, filter), sort) : [],
  )
  const order = $derived(mode === 'files' ? [...dirs, ...shownFiles].map((x) => x.path) : [])
  const files = $derived(programs ? [] : shownFiles.map((f) => f.path))
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

  // A box toggles itself on Space (no click), so Space has to tick here, before it does.
  function space(e: KeyboardEvent, tickIt: () => void) {
    if (e.key !== ' ') return
    e.preventDefault()
    tickIt()
  }

  function spaceRow(path: string, e: KeyboardEvent) {
    space(e, () => {
      picked = pickClick(picked, order, path, anchor, e.shiftKey && !programs)
      anchor = path
    })
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
    if (e.key === 'F5' && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault()
      e.stopPropagation() // the Video tab's F5 is the preview's
      if (listing) open(listing.path)
      return
    }
    const el = e.target instanceof HTMLElement ? e.target : null
    const typing = !!el?.closest('input, textarea, [contenteditable]')
    const row = el?.closest<HTMLElement>('[data-row]')?.dataset.row
    const plain = !e.ctrlKey && !e.metaKey && !e.altKey
    if (e.key === 'ArrowDown' && plain && el?.closest('[data-filter]')) {
      e.preventDefault()
      focusRow(null)
    } else if (!typing && ((e.key === 'Backspace' && plain) || (e.key === 'ArrowUp' && e.altKey))) {
      e.preventDefault()
      if (listing?.parent) open(listing.parent, listing.path) // the cursor lands on the folder left
    } else if (row !== undefined && plain && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
      e.preventDefault()
      move(row, e.key, e.shiftKey)
    } else if (row !== undefined && plain && e.key === 'Enter') {
      e.preventDefault()
      if (listing?.dirs.some((d) => d.path === row)) open(row, true)
      else {
        if (!picked.length) picked = [row]
        confirm()
      }
    } else if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'a' && !typing && files.length) {
      e.preventDefault()
      picked = pickAll(picked, files)
    }
  }

  // Shift ticks every row from where the moving started (the anchor) to the one it lands on.
  function move(row: string, key: string, shift: boolean) {
    const all = rows()
    const at = all.findIndex((r) => r.dataset.row === row)
    const to = key === 'Home' ? 0 : key === 'End' ? all.length - 1 : at + (key === 'ArrowDown' ? 1 : -1)
    const next = all[Math.max(0, Math.min(to, all.length - 1))]
    const path = next?.dataset.row
    if (!next || path === undefined) return
    next.focus()
    if (shift && mode === 'files' && !programs) {
      anchor ??= row
      picked = pickRange(picked, order, anchor, path, true)
    } else anchor = path
  }

  function confirm() {
    if (mode === 'folder') {
      if (listing) onpick([listing.path])
    } else {
      onpick(picked.length ? picked : listing ? [listing.path] : [])
    }
  }
</script>

{#snippet column(key: SortKey, label: string, cls: string)}
  <button
    class="flex items-center gap-1 hover:text-foreground {cls} {sort.key === key ? 'font-medium text-foreground' : ''}"
    onclick={() => sortBy(key)}
    aria-label="Sort by {label.toLowerCase()}"
    aria-pressed={sort.key === key}
  >
    {label}
    {#if sort.key === key}
      {#if sort.desc}<ChevronDownIcon class="size-3" />{:else}<ChevronUpIcon class="size-3" />{/if}
    {/if}
  </button>
{/snippet}

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
      <Tip text="Refresh (F5)">
        <Button
          variant="ghost"
          size="icon"
          disabled={!listing}
          onclick={() => listing && open(listing.path)}
          aria-label="Refresh"
        >
          <RefreshCwIcon />
        </Button>
      </Tip>
      <Tip text="New folder">
        <Button variant="ghost" size="icon" disabled={!listing} onclick={() => (newName = '')} aria-label="New folder">
          <FolderPlusIcon />
        </Button>
      </Tip>
    </div>

    <div class="relative border-b p-2">
      <SearchIcon class="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        class="h-8 pl-8"
        type="search"
        aria-label="Filter this folder"
        data-filter
        placeholder="Filter this folder"
        bind:value={filter}
        onkeydown={(e) => {
          if (e.key === 'Escape' && filter) {
            e.stopPropagation() // clears the filter, not closes the browser
            e.preventDefault()
            filter = ''
          }
        }}
      />
    </div>

    {#if error}<div class="px-3 py-2 text-sm text-destructive">{error}</div>{/if}

    <div class="min-h-0 flex-1 overflow-auto p-1" bind:this={list}>
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
        {#if dirs.length + shownFiles.length > 1}
          <div
            class="sticky top-0 z-10 flex items-center gap-2 border-b bg-background px-2 py-1 text-xs text-muted-foreground select-none"
          >
            {#if files.length > 1}
              <Tip text="All {files.length} files (Ctrl+A)">
                <Checkbox
                  checked={filesPicked === files.length}
                  indeterminate={filesPicked > 0 && filesPicked < files.length}
                  onclick={(e: MouseEvent) => {
                    e.preventDefault()
                    picked = pickAll(picked, files)
                  }}
                  onkeydown={(e: KeyboardEvent) => space(e, () => (picked = pickAll(picked, files)))}
                  aria-label="Pick all files"
                />
              </Tip>
            {:else if mode === 'files'}
              <span class="size-4 shrink-0"></span>
            {/if}
            {@render column('name', 'Name', 'flex-1')}
            {@render column('mtime', 'Modified', 'hidden w-36 sm:flex')}
            {#if mode === 'files'}{@render column('size', 'Size', 'w-20 justify-end')}{/if}
          </div>
        {/if}
        {#each dirs as d (d.path)}
          <div
            class="group flex items-center gap-2 rounded-md px-2 py-1 select-none hover:bg-accent"
            role="presentation"
            onpointerenter={() => over(d.path)}
          >
            {#if mode === 'files'}
              <Checkbox
                class="scroll-mt-9"
                data-row={d.path}
                checked={picked.includes(d.path)}
                onpointerdown={(e: PointerEvent) => press(d.path, e)}
                onclick={(e: MouseEvent) => click(d.path, e)}
                onkeydown={(e: KeyboardEvent) => spaceRow(d.path, e)}
                aria-label="Pick {d.name}"
              />
            {/if}
            <button
              class="flex min-w-0 flex-1 scroll-mt-9 items-center gap-2 text-left"
              data-row={mode === 'folder' ? d.path : undefined}
              onclick={() => open(d.path)}
            >
              <FolderIcon class="size-4 shrink-0 text-primary" /><span class="truncate">{d.name}</span>
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
            <span class="hidden w-36 text-xs text-muted-foreground sm:block">{modified(d.mtime)}</span>
            {#if mode === 'files'}<span class="w-20"></span>{/if}
          </div>
        {/each}
        {#if mode === 'folder' && !dirs.length && listing.dirs.length}
          <div class="p-4 text-center text-muted-foreground">No folder here matches “{filter.trim()}”</div>
        {/if}
        {#if mode === 'files'}
          {#each shownFiles as f (f.path)}
            <!-- The box is the keyboard's way to tick; the row is a bigger target for the mouse. -->
            <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
            <div
              class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 select-none hover:bg-accent"
              onpointerdown={(e) => press(f.path, e)}
              onpointerenter={() => over(f.path)}
              onclick={(e) => click(f.path, e)}
            >
              <Checkbox
                class="scroll-mt-9"
                data-row={f.path}
                checked={picked.includes(f.path)}
                onclick={(e: MouseEvent) => click(f.path, e)}
                onkeydown={(e: KeyboardEvent) => spaceRow(f.path, e)}
                aria-label="Pick {f.name}"
              />
              <FileIcon class="size-4 text-muted-foreground" />
              <span class="flex-1 truncate">{f.name}</span>
              <span class="hidden w-36 text-xs text-muted-foreground sm:block">{modified(f.mtime)}</span>
              <span class="w-20 text-right text-xs text-muted-foreground">{bytes(f.size)}</span>
            </div>
          {/each}
          {#if !dirs.length && !shownFiles.length}
            <div class="p-4 text-center text-muted-foreground">
              {filter.trim() && (listing.dirs.length || listing.files.length)
                ? `Nothing here matches “${filter.trim()}”`
                : programs
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
            ? `${picked.length} selected${programs ? '' : '. Drag or Shift+click ticks a range, Ctrl+A every file.'}`
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
