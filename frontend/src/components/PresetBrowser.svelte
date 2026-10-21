<script lang="ts" generics="T">
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
  import FolderIcon from '@lucide/svelte/icons/folder'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { canonical, presetKey, presetLabel, type PresetChoice } from '../lib/presetDraft'

  let { title, choices, parents, parentOf, summary, onselect, selected = null,
    encoder = $bindable(''), path = $bindable<string[]>([]), search = $bindable(''),
    problem = () => '', allowIncompatible = false, builtinLabel = 'built-in', disabled = false }: {
    title: string
    choices: PresetChoice<T>[]
    parents: [string, string][]
    parentOf: (data: T) => string
    summary: (data: T) => string
    onselect: (choice: PresetChoice<T>) => void
    selected?: string | null
    encoder?: string
    path?: string[]
    search?: string
    problem?: (data: T) => string
    allowIncompatible?: boolean
    builtinLabel?: string
    disabled?: boolean
  } = $props()

  const parentChoices = $derived(choices.filter(c => parentOf(c.data) === encoder))
  const query = $derived(search.trim().toLocaleLowerCase())
  const folders = $derived([...new Set(parentChoices.filter(c => (c.group ?? []).length > path.length
    && canonical((c.group ?? []).slice(0, path.length)) === canonical(path)).map(c => c.group![path.length]))]
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true })))
  const visible = $derived(parentChoices.filter(c => query
    ? [...(c.group ?? []), presetLabel(c)].join(' / ').toLocaleLowerCase().includes(query)
    : canonical(c.group ?? []) === canonical(path))
    .sort((a, b) => Number(b.builtin) - Number(a.builtin) || presetLabel(a).localeCompare(presetLabel(b))))
</script>

<div class="flex min-h-0 flex-1 flex-col gap-3">
  <label class="flex shrink-0 items-center gap-3 text-sm">
    Encoder
    <NativeSelect class="min-w-0 flex-1" aria-label="Browse {title.toLowerCase()} presets" value={encoder} {disabled}
      onchange={e => { encoder = e.currentTarget.value; path = []; search = '' }}>
      {#each parents as [id, label] (id)}<option value={id}>{label}</option>{/each}
    </NativeSelect>
  </label>
  <Input class="shrink-0" aria-label="Search {title.toLowerCase()} presets" placeholder="Search presets…" bind:value={search} {disabled} />
  {#if !query}
    <nav class="flex shrink-0 flex-wrap items-center gap-1 text-xs" aria-label="Preset folders">
      <button class="rounded px-1 py-0.5 hover:bg-accent" {disabled} onclick={() => (path = [])}>{parents.find(([id]) => id === encoder)?.[1] ?? encoder}</button>
      {#each path as part, i (i)}
        <ChevronRightIcon class="size-3 shrink-0" />
        <button class="rounded px-1 py-0.5 hover:bg-accent" {disabled} onclick={() => (path = path.slice(0, i + 1))}>{part}</button>
      {/each}
    </nav>
  {/if}
  <ul class="min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="{title} preset choices">
    {#if !query}
      {#each folders as part (part)}
        <li>
          <button class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-accent" {disabled} onclick={() => (path = [...path, part])}>
            <FolderIcon class="size-4 shrink-0 text-muted-foreground" /><span class="min-w-0 flex-1 break-words">{part}</span><ChevronRightIcon class="size-4" />
          </button>
        </li>
      {/each}
    {/if}
    {#each visible as c (presetKey(c))}
      {@const reason = problem(c.data)}
      <li>
        <button class="flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-accent disabled:opacity-60 {presetKey(c) === selected ? 'bg-accent' : ''}"
          disabled={disabled || (!allowIncompatible && !!reason)} title={reason || undefined} onclick={() => onselect(c)}>
          <span class="w-4 shrink-0">{#if presetKey(c) === selected}<CheckIcon class="size-4 text-primary" />{/if}</span>
          <span class="min-w-0 flex-1">
            <span class="block break-words">{presetLabel(c)}</span>
            {#if query && c.group?.length}<span class="block text-xs text-muted-foreground">{c.group.join(' / ')}</span>{/if}
            <span class="block text-xs text-muted-foreground">{summary(c.data)}</span>
            {#if reason}<span class="block text-xs text-warning">{reason}</span>{/if}
          </span>
          {#if c.builtin}<span class="text-xs text-muted-foreground">{c.badge ?? builtinLabel}</span>{/if}
        </button>
      </li>
    {/each}
    {#if !visible.length && (query || !folders.length)}<li class="px-2 py-3 text-xs text-muted-foreground">No presets here. Use Manage presets to create one.</li>{/if}
  </ul>
</div>
