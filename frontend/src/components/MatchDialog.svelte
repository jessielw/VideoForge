<script lang="ts">
  // Review matches: every file of the batch (unmatched ones first, then each source's video, chapters and
  // subtitles) with the source it goes to, how it matched, and a menu to change that: any source, or none.
  // "Needs a look" shows the unmatched files and the guesses (closest name, numbered set, the only source);
  // a file changed here stays in that view until the dialog closes. Matching one file of a numbered set offers
  // the rest of the set the same way. Each change matches the batch again, so the list shows the result. Each
  // row says what a guess went on and what clashes with it (a second chapters file or encode for one source,
  // subtitles alike). A set matched by hand is remembered when its jobs are added; a file matched that way can
  // forget its pattern, and the footer forgets them all. Rows can be ticked (Shift for a range, or every row
  // shown) to move them all to one source, or none, at once. A text subtitle whose last line ends well past
  // its source, or well before it, is flagged (a warning only); one tagged synced or matched by hand isn't.
  import { tick } from 'svelte'
  import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
  import SparklesIcon from '@lucide/svelte/icons/sparkles'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import Undo2Icon from '@lucide/svelte/icons/undo-2'
  import WandSparklesIcon from '@lucide/svelte/icons/wand-sparkles'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import { api } from '../lib/api'
  import { basename } from '../lib/format'
  import { MATCH_NOTE, nameParts } from '../lib/matchCheck'
  import { MATCH_ICONS, matchTone } from '../lib/matchIcons'
  import {
    filterEntries,
    matchEntries,
    needsLook,
    rangeOf,
    suggestedMatches,
    type MatchEntry,
    type MatchKind,
  } from '../lib/matchReview'
  import type { MatchResult, SubtitleTiming } from '../lib/types'
  import Tip from './Tip.svelte'

  let {
    open = $bindable(false),
    result,
    matching = false,
    assign = $bindable({}),
    focus = null,
    timing = {},
    checkingTiming = false,
    onforget,
  }: {
    open?: boolean
    result: MatchResult | null
    matching?: boolean
    assign?: Record<string, string | null>
    focus?: string | null // a file to show and put the cursor on when the dialog opens
    timing?: Record<string, SubtitleTiming> // subtitle timing checks, by timingKey
    checkingTiming?: boolean
    onforget?: () => void // remembered patterns changed: match the batch again
  } = $props()

  const KIND: Record<MatchKind, string> = { video: 'Video', subtitles: 'Subtitles', chapters: 'Chapters' }

  const entries = $derived(result ? matchEntries(result, timing) : [])
  const sources = $derived(result?.jobs.map((j) => j.source) ?? [])
  const lookCount = $derived(entries.filter(needsLook).length)
  let view = $state<'look' | 'all'>('look')
  let autoView = false // opened on All files only because nothing needed a look then
  let query = $state('')
  let touched = $state<string[]>([]) // changed since the dialog opened: kept in "Needs a look"
  let list = $state<HTMLElement>()

  const shown = $derived(
    filterEntries(view === 'look' ? entries.filter((e) => needsLook(e) || touched.includes(e.path)) : entries, query),
  )
  const learned = $derived(suggestedMatches(entries, 'pattern'))
  const suggested = $derived(suggestedMatches(entries))
  const mine = $derived(Object.keys(assign).length)
  let remembered = $state(0) // name patterns remembered from earlier batches
  let forgetError = $state('')

  async function countPatterns() {
    remembered = (await api.matchPatterns().catch(() => [])).length
  }
  async function forget(shape?: string) {
    forgetError = ''
    try {
      await api.forgetMatchPatterns(shape)
    } catch (e) {
      forgetError = e instanceof Error ? e.message : String(e)
      return
    }
    await countPatterns()
    onforget?.()
  }

  // Each opening starts afresh: "Needs a look" when something does, all files otherwise or to show one file.
  let wasOpen = false
  $effect(() => {
    if (open && !wasOpen) {
      query = ''
      touched = []
      ticked = []
      anchor = null
      view = focus || !lookCount ? 'all' : 'look'
      autoView = !focus && !lookCount
      forgetError = ''
      void countPatterns()
      if (focus) void reveal(focus)
    }
    wasOpen = open
  })
  // Opened on All files with nothing to check, then something turned up (a subtitle timing check answered):
  // show it, unless the user has picked a view or changed a match since.
  $effect(() => {
    if (open && autoView && lookCount && !touched.length) {
      view = 'look'
      autoView = false
    }
  })
  function pickView(v: 'look' | 'all') {
    view = v
    autoView = false
  }

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
  // Ticked rows, for moving several at once; Shift ticks (or unticks) the range from the last row ticked.
  let ticked = $state<string[]>([])
  let anchor: string | null = null
  let shift = false
  const tickedNow = $derived(ticked.filter((p) => entries.some((e) => e.path === p)))
  const allShown = $derived(shown.length > 0 && shown.every((e) => ticked.includes(e.path)))
  const someShown = $derived(!allShown && shown.some((e) => ticked.includes(e.path)))
  function toggleTicked(path: string) {
    const on = !ticked.includes(path)
    const paths =
      shift && anchor
        ? rangeOf(
            shown.map((e) => e.path),
            anchor,
            path,
          )
        : [path]
    ticked = on ? [...new Set([...ticked, ...paths])] : ticked.filter((p) => !paths.includes(p))
    anchor = path
  }
  function tickShown(on: boolean) {
    const paths = shown.map((e) => e.path)
    ticked = on ? [...new Set([...ticked, ...paths])] : ticked.filter((p) => !paths.includes(p))
  }
  function moveTicked(value: string) {
    if (!value) return
    const moves = Object.fromEntries(
      entries
        .filter((e) => tickedNow.includes(e.path) && menuValue(e) !== value)
        .map((e) => [e.path, value === NONE ? null : value]),
    )
    assign = { ...assign, ...moves }
    touch(tickedNow)
  }
  function undoTicked() {
    assign = Object.fromEntries(Object.entries(assign).filter(([p]) => !tickedNow.includes(p)))
    touch(tickedNow)
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
        onValueChange={(v) => v && pickView(v as 'look' | 'all')}
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
      {#if checkingTiming}
        <span class="flex items-center gap-1 text-xs text-muted-foreground"
          ><LoaderCircleIcon class="size-3 animate-spin" />Checking subtitle timing…</span
        >
      {/if}
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
        <Button size="sm" variant="outline" onclick={() => apply(learned)}>Match them the same way</Button>
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

    {#if shown.length}
      <div class="flex min-h-8 flex-wrap items-center gap-2 px-3 text-sm">
        <Checkbox
          checked={allShown}
          indeterminate={someShown}
          aria-label="Select every file shown"
          onCheckedChange={(on) => tickShown(on === true)}
        />
        {#if tickedNow.length}
          <span class="font-medium">{tickedNow.length} selected</span>
          <NativeSelect
            size="sm"
            class="min-w-0"
            aria-label="Move the selected files to"
            value=""
            onchange={(ev) => {
              moveTicked(ev.currentTarget.value)
              ev.currentTarget.value = ''
            }}
          >
            <option value="" disabled>Move to…</option>
            <option value={NONE}>No source (leave them out)</option>
            <optgroup label="Sources">
              {#each sources as s (s)}<option value={s}>{basename(s)}</option>{/each}
            </optgroup>
          </NativeSelect>
          {#if tickedNow.some((p) => p in assign)}
            <Button size="sm" variant="ghost" onclick={undoTicked}><Undo2Icon />Undo their changes</Button>
          {/if}
          <Button size="sm" variant="ghost" onclick={() => (ticked = [])}>Clear selection</Button>
        {:else}
          <span class="text-muted-foreground">Select files to move several at once (Shift+click for a range)</span>
        {/if}
      </div>
    {/if}

    <div class="min-h-40 flex-1 overflow-auto rounded-lg border" bind:this={list}>
      {#if !shown.length}
        <p class="p-6 text-center text-sm text-muted-foreground">
          {#if query}No file matches “{query}”.{:else if view === 'look'}Every file is matched by name or by you.
            <button class="underline underline-offset-2" onclick={() => pickView('all')}>Show all files</button
            >{:else}No files to match.{/if}
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
              class="grid grid-cols-[auto_auto_minmax(0,1fr)] items-center gap-x-2 gap-y-1 px-3 py-2 sm:grid-cols-[auto_auto_minmax(0,1fr)_minmax(14rem,22rem)] {ticked.includes(
                e.path,
              )
                ? 'bg-primary/5'
                : ''}"
              data-path={e.path}
            >
              <Checkbox
                checked={ticked.includes(e.path)}
                aria-label="Select {basename(e.path)}"
                onpointerdown={(ev: PointerEvent) => (shift = ev.shiftKey)}
                onkeydown={(ev: KeyboardEvent) => (shift = ev.shiftKey)}
                onCheckedChange={() => toggleTicked(e.path)}
              />
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
                    e.source !== null
                      ? e.detail
                      : e.reason === 'manual'
                        ? 'set to no source by you'
                        : e.conflict
                          ? ''
                          : 'not matched',
                  ]
                    .filter(Boolean)
                    .join(' · ')}{#if e.pattern}
                    · <button
                      class="underline underline-offset-2 hover:text-foreground"
                      onclick={() => forget(e.pattern ?? undefined)}>Forget this pattern</button
                    >{/if}
                </div>
                {#if e.conflict}<div class="text-xs text-warning">{e.conflict}</div>{/if}
                {#if e.timing}<div class="text-xs text-warning">{e.timing}</div>{/if}
              </div>
              <div class="col-span-3 flex min-w-0 items-center gap-1 sm:col-span-1">
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
                      {#each e.suggestions as s (s.source)}<option value={s.source} title={s.detail}
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

    <Dialog.Footer class="items-center">
      {#if forgetError}<span class="text-sm text-destructive">{forgetError}</span>{/if}
      {#if remembered}
        <span class="mr-auto text-xs text-muted-foreground"
          >Sets you matched by hand are remembered for later batches · {remembered}
          <button class="underline underline-offset-2 hover:text-foreground" onclick={() => forget()}>Forget all</button
          ></span
        >
      {/if}
      <Button onclick={() => (open = false)}>Done</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
