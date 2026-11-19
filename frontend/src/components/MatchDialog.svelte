<script lang="ts">
  // Review matches: every file of the batch (unmatched ones first, then each source's video, chapters and
  // subtitles) with the source it goes to, how it matched, and a menu to change that: any source, or none.
  // "Needs a look" shows the unmatched files and the guesses (closest name, numbered set, the only source);
  // a file changed here stays in that view until the dialog closes. Matching one file of a numbered set offers
  // the rest of the set the same way. Each change matches the batch again, so the list shows the result.
  import { tick } from 'svelte'
  import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
  import SparklesIcon from '@lucide/svelte/icons/sparkles'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import Undo2Icon from '@lucide/svelte/icons/undo-2'
  import WandSparklesIcon from '@lucide/svelte/icons/wand-sparkles'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import { basename } from '../lib/format'
  import { MATCH_NOTE, nameParts } from '../lib/matchCheck'
  import { MATCH_ICONS, matchTone } from '../lib/matchIcons'
  import {
    filterEntries,
    matchEntries,
    needsLook,
    suggestedMatches,
    type MatchEntry,
    type MatchKind,
  } from '../lib/matchReview'
  import type { MatchResult } from '../lib/types'
  import Tip from './Tip.svelte'

  let {
    open = $bindable(false),
    result,
    matching = false,
    assign = $bindable({}),
    focus = null,
  }: {
    open?: boolean
    result: MatchResult | null
    matching?: boolean
    assign?: Record<string, string | null>
    focus?: string | null // a file to show and put the cursor on when the dialog opens
  } = $props()

  const KIND: Record<MatchKind, string> = { video: 'Video', subtitles: 'Subtitles', chapters: 'Chapters' }

  const entries = $derived(result ? matchEntries(result) : [])
  const sources = $derived(result?.jobs.map((j) => j.source) ?? [])
  const lookCount = $derived(entries.filter(needsLook).length)
  let view = $state<'look' | 'all'>('look')
  let query = $state('')
  let touched = $state<string[]>([]) // changed since the dialog opened: kept in "Needs a look"
  let list = $state<HTMLElement>()

  const shown = $derived(
    filterEntries(view === 'look' ? entries.filter((e) => needsLook(e) || touched.includes(e.path)) : entries, query),
  )
  const learned = $derived(suggestedMatches(entries, 'pattern'))
  const suggested = $derived(suggestedMatches(entries))
  const mine = $derived(Object.keys(assign).length)

  // Each opening starts afresh: "Needs a look" when something does, all files otherwise or to show one file.
  let wasOpen = false
  $effect(() => {
    if (open && !wasOpen) {
      query = ''
      touched = []
      view = focus || !lookCount ? 'all' : 'look'
      if (focus) void reveal(focus)
    }
    wasOpen = open
  })

  async function reveal(path: string) {
    await tick()
    const row = [...(list?.querySelectorAll<HTMLElement>('[data-path]') ?? [])].find((r) => r.dataset.path === path)
    row?.scrollIntoView({ block: 'center' })
    row?.querySelector('select')?.focus()
  }

  function touch(paths: string[]) {
    touched = [...new Set([...touched, ...paths])]
  }
  // The menu's value: a source, NONE (left out on purpose) or '' (not matched yet, a placeholder).
  const NONE = '-'
  function menuValue(e: MatchEntry): string {
    return e.source ?? (e.reason === 'manual' ? NONE : '')
  }
  function setSource(e: MatchEntry, value: string) {
    if (!value || value === menuValue(e)) return
    assign = { ...assign, [e.path]: value === NONE ? null : value }
    touch([e.path])
  }
  function undo(path: string) {
    const { [path]: _, ...rest } = assign
    assign = rest
    touch([path])
  }
  function apply(matches: Record<string, string>) {
    assign = { ...assign, ...matches }
    touch(Object.keys(matches))
  }
  function undoAll() {
    touch(Object.keys(assign))
    assign = {}
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="flex max-h-[90vh] flex-col gap-3 sm:max-w-5xl">
    <Dialog.Header>
      <Dialog.Title class="flex items-center gap-2"
        >Review matches{#if matching}<LoaderCircleIcon
            class="size-4 animate-spin text-muted-foreground"
            aria-label="Matching"
          />{/if}</Dialog.Title
      >
      <Dialog.Description>
        Pick the source each file goes to, or No source to leave it out. Your changes win over matching by name, and go
        with Add.
      </Dialog.Description>
    </Dialog.Header>

    <div class="flex flex-wrap items-center gap-2">
      <ToggleGroup.Root
        type="single"
        variant="outline"
        spacing={1}
        aria-label="Show"
        value={view}
        onValueChange={(v) => v && (view = v as 'look' | 'all')}
      >
        <ToggleGroup.Item value="look" class="px-3 data-[state=on]:bg-primary/15"
          >Needs a look · {lookCount}</ToggleGroup.Item
        >
        <ToggleGroup.Item value="all" class="px-3 data-[state=on]:bg-primary/15"
          >All files · {entries.length}</ToggleGroup.Item
        >
      </ToggleGroup.Root>
      <Input
        class="h-8 min-w-0 basis-full sm:w-56 sm:basis-auto"
        placeholder="Filter by name"
        aria-label="Filter by name"
        bind:value={query}
      />
      <span class="flex-1"></span>
      {#if mine}
        <Button size="sm" variant="ghost" onclick={undoAll}><Undo2Icon />Undo my matches · {mine}</Button>
      {/if}
    </div>

    {#if Object.keys(learned).length}
      <div
        class="flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/10 px-3 py-2 text-sm"
      >
        <WandSparklesIcon class="size-4 shrink-0 text-primary" />
        <span class="flex-1"
          >{Object.keys(learned).length} more file{Object.keys(learned).length === 1 ? '' : 's'} named like the one you matched.</span
        >
        <Button size="sm" onclick={() => apply(learned)}>Match them the same way</Button>
      </div>
    {:else if Object.keys(suggested).length}
      <div class="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm">
        <SparklesIcon class="size-4 shrink-0 text-warning" />
        <span class="flex-1"
          >{Object.keys(suggested).length} unmatched file{Object.keys(suggested).length === 1 ? ' has' : 's have'} a suggested
          source.</span
        >
        <Button size="sm" variant="outline" onclick={() => apply(suggested)}>Use the suggestions</Button>
      </div>
    {/if}

    <div class="min-h-40 flex-1 overflow-auto rounded-lg border" bind:this={list}>
      {#if !shown.length}
        <p class="p-6 text-center text-sm text-muted-foreground">
          {#if query}No file matches “{query}”.{:else if view === 'look'}Every file is matched by name or by you.
            <button class="underline underline-offset-2" onclick={() => (view = 'all')}>Show all files</button>{:else}No
            files to match.{/if}
        </p>
      {:else}
        <ul class="divide-y divide-border/60 text-sm" aria-label="Files">
          {#each shown as e (e.path)}
            {@const note = e.reason ? MATCH_NOTE[e.reason] : null}
            {@const Icon = e.reason ? MATCH_ICONS[e.reason] : TriangleAlertIcon}
            {@const name = e.source
              ? nameParts(basename(e.path), basename(e.source))
              : { shared: '', rest: basename(e.path) }}
            {@const picked = e.path in assign}
            <li
              class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2 gap-y-1 px-3 py-2 sm:grid-cols-[auto_minmax(0,1fr)_minmax(14rem,22rem)]"
              data-path={e.path}
            >
              <Tip text={note ? note.text : 'Not matched to any source'}>
                <Icon
                  role="img"
                  aria-label={note ? note.text : 'Not matched to any source'}
                  class="size-4 shrink-0 {e.reason ? matchTone(e.reason, note?.sure ?? false) : 'text-warning'}"
                />
              </Tip>
              <div class="min-w-0">
                <Tip text={e.path}
                  ><span class="[overflow-wrap:anywhere]"
                    ><span class="text-muted-foreground">{name.shared}</span>{name.rest}</span
                  ></Tip
                >
                <div class="text-xs text-muted-foreground">
                  {[
                    KIND[e.kind],
                    e.source !== null ? '' : e.reason === 'manual' ? 'set to no source by you' : 'not matched',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </div>
              <div class="col-span-2 flex min-w-0 items-center gap-1 sm:col-span-1">
                <NativeSelect
                  size="sm"
                  class="w-full min-w-0 flex-1"
                  aria-label="Source for {basename(e.path)}"
                  value={menuValue(e)}
                  onchange={(ev) => setSource(e, ev.currentTarget.value)}
                >
                  {#if !menuValue(e)}<option value="" disabled>Choose a source…</option>{/if}
                  <option value={NONE}>No source (leave it out)</option>
                  {#if e.suggestions.length}
                    <optgroup label="Suggested">
                      {#each e.suggestions as s (s.source)}<option value={s.source}
                          >{basename(s.source)}{s.why === 'pattern' ? ' (like your match)' : ''}</option
                        >{/each}
                    </optgroup>
                  {/if}
                  <optgroup label="Sources">
                    {#each sources as s (s)}<option value={s}>{basename(s)}</option>{/each}
                  </optgroup>
                </NativeSelect>
                <span class="w-7 shrink-0">
                  {#if picked}
                    <Tip text="Undo your change">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label="Undo match: {basename(e.path)}"
                        onclick={() => undo(e.path)}><XIcon /></Button
                      >
                    </Tip>
                  {/if}
                </span>
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <Dialog.Footer>
      <Button onclick={() => (open = false)}>Done</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
