<script lang="ts" generics="T">
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
  import FolderIcon from '@lucide/svelte/icons/folder'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { canonical, presetKey, presetLabel, type PresetChoice } from '../lib/presetDraft'

  let {
    title,
    choices,
    parents,
    parentOf,
    summary,
    onselect,
    selected = null,
    encoder = $bindable(''),
    path = $bindable<string[]>([]),
    search = $bindable(''),
    problem = () => '',
    allowIncompatible = false,
    builtinLabel = 'built-in',
    disabled = false,
    selecting = false,
    picked = $bindable<string[]>([]),
  }: {
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
    selecting?: boolean // saved presets get checkboxes (picked: their names); a folder's picks all inside it
    picked?: string[]
  } = $props()

  const parentChoices = $derived(choices.filter((c) => !encoder || parentOf(c.data) === encoder))
  const query = $derived(search.trim().toLocaleLowerCase())
  const encoderLabel = (data: T) => parents.find(([id]) => id === parentOf(data))?.[1] ?? parentOf(data)
  const folders = $derived(
    [
      ...new Set(
        parentChoices
          .filter(
            (c) =>
              !c.builtin &&
              (c.group ?? []).length > path.length &&
              canonical((c.group ?? []).slice(0, path.length)) === canonical(path),
          )
          .map((c) => c.group![path.length]),
      ),
    ].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
  )
  const visible = $derived(
    parentChoices.filter((c) =>
      query
        ? [...(c.group ?? []), presetLabel(c), parentOf(c.data), encoderLabel(c.data), summary(c.data)]
            .join(' / ')
            .toLocaleLowerCase()
            .includes(query)
        : c.builtin
          ? !path.length
          : canonical(c.group ?? []) === canonical(path),
    ),
  )
  const saved = $derived(
    visible
      .filter((c) => !c.builtin)
      .sort(
        (a, b) =>
          presetLabel(a).localeCompare(presetLabel(b), undefined, { numeric: true }) ||
          encoderLabel(a.data).localeCompare(encoderLabel(b.data)),
      ),
  )
  const builtins = $derived(visible.filter((c) => c.builtin))
  // The saved presets in a folder (at any depth) under the encoder filter, for its checkbox.
  const inFolder = (part: string) =>
    parentChoices
      .filter((c) => !c.builtin && canonical((c.group ?? []).slice(0, path.length + 1)) === canonical([...path, part]))
      .map((c) => c.name)
  function pickMany(names: string[], on: boolean) {
    picked = on ? [...new Set([...picked, ...names])] : picked.filter((n) => !names.includes(n))
  }
</script>

{#snippet choiceRow(c: PresetChoice<T>)}
  {@const reason = problem(c.data)}
  {@const chosen = picked.includes(c.name)}
  <li class={selecting ? 'flex items-center gap-1' : ''}>
    {#if selecting}
      <span class="flex w-6 shrink-0 justify-center">
        {#if !c.builtin}<Checkbox
            checked={chosen}
            {disabled}
            aria-label="Select {presetLabel(c)}"
            onCheckedChange={(on) => pickMany([c.name], on)}
          />{/if}
      </span>
    {/if}
    <button
      class="flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-accent disabled:opacity-60 {presetKey(
        c,
      ) === selected
        ? 'bg-accent'
        : ''}"
      disabled={disabled || (!allowIncompatible && !!reason)}
      aria-current={presetKey(c) === selected ? 'true' : undefined}
      onclick={() => (selecting ? !c.builtin && pickMany([c.name], !chosen) : onselect(c))}
    >
      <span class="w-4 shrink-0"
        >{#if presetKey(c) === selected}<CheckIcon class="size-4 text-primary" />{/if}</span
      >
      <span class="min-w-0 flex-1">
        <span class="block break-words">{presetLabel(c)}</span>
        {#if query && c.group?.length}<span class="block break-words text-xs text-muted-foreground"
            >{c.group.join(' / ')}</span
          >{/if}
        <span class="block break-words text-xs text-muted-foreground">{encoderLabel(c.data)} · {summary(c.data)}</span>
        {#if reason}<span class="block break-words text-xs text-warning">{reason}</span>{/if}
      </span>
      {#if c.builtin}<span class="shrink-0 text-xs text-muted-foreground">{c.badge ?? builtinLabel}</span>{/if}
    </button>
  </li>
{/snippet}

<div class="flex min-h-0 flex-1 flex-col gap-3">
  <Input
    class="shrink-0"
    aria-label="Search {title.toLowerCase()} presets"
    placeholder={encoder ? 'Search presets…' : 'Search all presets…'}
    bind:value={search}
    {disabled}
  />
  <label class="flex shrink-0 items-center gap-3 text-sm">
    Encoder
    <NativeSelect
      class="min-w-0 flex-1"
      aria-label="Filter {title.toLowerCase()} presets by encoder"
      value={encoder}
      {disabled}
      onchange={(e) => {
        encoder = e.currentTarget.value
        path = []
      }}
    >
      <option value="">All encoders</option>
      {#each parents as [id, label] (id)}<option value={id}>{label}</option>{/each}
    </NativeSelect>
  </label>
  {#if !query && path.length}
    <nav class="flex shrink-0 flex-wrap items-center gap-1 text-xs" aria-label="Preset folders">
      <button class="rounded px-1 py-0.5 hover:bg-accent" {disabled} onclick={() => (path = [])}>My presets</button>
      {#each path as part, i (i)}
        <ChevronRightIcon class="size-3 shrink-0" />
        <button
          class="min-w-0 break-words rounded px-1 py-0.5 hover:bg-accent"
          {disabled}
          onclick={() => (path = path.slice(0, i + 1))}>{part}</button
        >
      {/each}
    </nav>
  {/if}
  <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain">
    {#if saved.length || (!query && folders.length)}
      <section aria-label="My presets">
        <h3 class="px-2 pb-1 text-xs font-medium text-muted-foreground">My presets</h3>
        <ul aria-label="My {title.toLowerCase()} presets">
          {#if !query}
            {#each folders as part (part)}
              {@const inside = inFolder(part)}
              {@const some = inside.filter((n) => picked.includes(n)).length}
              <li class={selecting ? 'flex items-center gap-1' : ''}>
                {#if selecting}
                  <span class="flex w-6 shrink-0 justify-center">
                    <Checkbox
                      checked={some === inside.length}
                      indeterminate={some > 0 && some < inside.length}
                      {disabled}
                      aria-label="Select everything in {part}"
                      onCheckedChange={(on) => pickMany(inside, on)}
                    />
                  </span>
                {/if}
                <button
                  class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-accent"
                  {disabled}
                  onclick={() => (path = [...path, part])}
                >
                  <FolderIcon class="size-4 shrink-0 text-muted-foreground" /><span class="min-w-0 flex-1 break-words"
                    >{part}</span
                  ><ChevronRightIcon class="size-4 shrink-0" />
                </button>
              </li>
            {/each}
          {/if}
          {#each saved as c (presetKey(c))}{@render choiceRow(c)}{/each}
        </ul>
      </section>
    {/if}
    {#if builtins.length}
      <section aria-label="Built-in presets">
        <h3 class="px-2 pb-1 text-xs font-medium text-muted-foreground">Built-in</h3>
        <ul aria-label="Built-in {title.toLowerCase()} presets">
          {#each builtins as c (presetKey(c))}{@render choiceRow(c)}{/each}
        </ul>
      </section>
    {/if}
    {#if !visible.length && (query || !folders.length)}
      <p class="px-2 py-3 text-xs text-muted-foreground" role="status">
        {query
          ? 'No presets match your search.'
          : path.length
            ? 'No presets in this folder.'
            : encoder
              ? 'No presets for this encoder.'
              : 'No presets available.'}
      </p>
    {/if}
  </div>
</div>
