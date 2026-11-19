<script lang="ts">
  // New jobs: rule set + language, input slots, output folder, live match preview, Add to queue.
  import { flushSync, onDestroy, onMount, untrack } from 'svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
  import ListChecksIcon from '@lucide/svelte/icons/list-checks'
  import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Card from '$lib/components/ui/card'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import OutputFolderMenu from '../components/OutputFolderMenu.svelte'
  import PathSlot from '../components/PathSlot.svelte'
  import EncoderPresetMenu from '../components/EncoderPresetMenu.svelte'
  import { api } from '../lib/api'
  import { incoming } from '../lib/incoming.svelte'
  import { drafts } from '../lib/drafts'
  import { LatestRequest } from '../lib/latestRequest'
  import { router } from '../lib/router.svelte'
  import { app } from '../lib/state.svelte'
  import { groupByFolder } from '../lib/templateFolders'
  import { ENCODERS, type EncoderSettings, type MatchResult } from '../lib/types'
  import LanguagePicker from '../components/LanguagePicker.svelte'
  import MatchDialog from '../components/MatchDialog.svelte'
  import MatchTable from '../components/MatchTable.svelte'
  import { matchEntries, needsLook as needsLookAt } from '../lib/matchReview'
  import { oddSubtitleRows, oddSummary, wrongEpisodeCount } from '../lib/matchCheck'
  import Tip from '../components/Tip.svelte'

  type ImportResult = Awaited<ReturnType<typeof api.addJobs>>
  type Draft = {
    ruleSet: string
    language: string
    sources: string[]
    encodes: string[]
    subtitles: string[]
    chapters: string[]
    output: string[]
    templateName: string | null
    encoder: EncoderSettings | null
    container: string
    autoIndex?: boolean
    autoCrop?: boolean
    completion?: ImportResult | null
    assign?: Record<string, string | null>
  }
  const restored = drafts.read<Draft>('new-jobs')
  let ruleSet = $state(restored?.ruleSet ?? '')
  let language = $state(restored?.language ?? '')
  let sources = $state<string[]>(restored?.sources ?? [])
  let encodes = $state<string[]>(restored?.encodes ?? [])
  let subtitles = $state<string[]>(restored?.subtitles ?? [])
  let chapters = $state<string[]>(restored?.chapters ?? [])
  let output = $state<string[]>(restored?.output ?? [])
  let result = $state<MatchResult | null>(null)
  let matching = $state(false)
  let error = $state('')
  let adding = $state(false)
  let replacements = $state<string[]>([])
  let excluded = $state<string[]>([]) // subtitles unticked in Matched files
  let assign = $state<Record<string, string | null>>(restored?.assign ?? {}) // file -> source (null: none), by hand
  // Review matches: open, on which file, and the last match result, shown while the batch matches again.
  let reviewing = $state(false)
  let rematch = $state(0)
  let reviewFocus = $state<string | null>(null)
  let shownResult = $state<MatchResult | null>(null)
  $effect(() => {
    if (result) shownResult = result
    else if (!sources.length) shownResult = null
  })
  const needsLook = $derived(shownResult ? matchEntries(shownResult).filter(needsLookAt).length : 0)
  function review(path: string | null = null) {
    reviewFocus = path
    reviewing = true
  }
  const odd = $derived(result ? oddSubtitleRows(result.jobs, excluded) : new Map())
  const wrongEpisode = $derived(result ? wrongEpisodeCount(result.jobs, excluded) : 0)
  let completion = $state<ImportResult | null>(restored?.completion ?? null)
  // The template (by name; the rule set's starred one first) and the container it sets, which can
  // be changed here.
  let templateName = $state<string | null>(restored?.templateName ?? null)
  let encoder = $state<EncoderSettings | null>(restored?.encoder ?? null)
  let container = $state(restored?.container ?? '')
  // Index / crop for this batch; they start from Settings' values (see onMount) and are kept with the draft.
  let autoIndex = $state(restored?.autoIndex ?? true)
  let autoCrop = $state(restored?.autoCrop ?? true)
  const templateChoices = $derived(app.presetChoices('template', ruleSet))
  const templateGroups = $derived(groupByFolder(templateChoices, (c) => c.name))
  const template = $derived(
    templateChoices.find((c) => c.name === (templateName ?? app.defaultTemplate(ruleSet))) ?? templateChoices[0],
  )
  const templateKey = $derived(JSON.stringify([ruleSet, templateName ?? app.defaultTemplate(ruleSet)]))
  let previousRuleSet = restored?.ruleSet ?? ''
  let appliedKey = restored ? JSON.stringify([restored.ruleSet, restored.templateName]) : ''

  function persist() {
    drafts.write(
      'new-jobs',
      $state.snapshot({
        ruleSet,
        language,
        sources,
        encodes,
        subtitles,
        chapters,
        output,
        templateName: template?.name ?? templateName,
        encoder,
        container,
        autoIndex,
        autoCrop,
        completion,
        assign,
      }),
    )
  }
  onDestroy(persist)
  const containers = $derived(app.ruleSets.find((p) => p.id === ruleSet)?.containers ?? [])

  $effect(() => {
    // A manual selection survives preset saves; a rule set switch starts on its default.
    if (ruleSet !== previousRuleSet) {
      previousRuleSet = ruleSet
      templateName = null
    }
  })
  $effect(() => {
    // Switching templates resets the override, but saving/renaming an encoder preset does not.
    if (!template || template.name !== (templateName ?? app.defaultTemplate(ruleSet)) || templateKey === appliedKey)
      return
    appliedKey = templateKey
    untrack(() => {
      encoder = template ? structuredClone($state.snapshot(template.data.encoder)) : null
      const own = template?.data.mux.container
      container = containers.some((c) => c.id === own) ? own! : (containers[0]?.id ?? '')
    })
  })

  // Paths pasted anywhere in the app, or picked with "Add files…"; held while Add runs.
  $effect(() => {
    if (!incoming.pending.length || adding) return
    const known = new Set(sources.map((p) => p.toLowerCase()))
    sources = [...sources, ...incoming.pending.filter((p) => !known.has(p.toLowerCase()))]
    incoming.pending = []
  })

  const takesSubs = $derived(app.ruleSets.find((p) => p.id === ruleSet)?.external_subtitles ?? true)

  onMount(async () => {
    if (!ruleSet) ruleSet = app.defaultRuleSet?.id ?? ''
    const s = await api.settings().catch(() => null)
    const first = s?.output_default || s?.output_dir
    if (first && !output.length) output = [first]
    if (!restored) {
      const c = await api.config().catch(() => null)
      if (c) {
        autoIndex = c.auto_index
        autoCrop = c.auto_crop
      }
    }
  })

  $effect(() => {
    if (!ruleSet && app.defaultRuleSet) ruleSet = app.defaultRuleSet.id
  })

  const slots = () => ({
    sources,
    encodes,
    subtitles: takesSubs ? subtitles : [],
    chapters,
    rule_set: ruleSet,
    assign,
    rematch, // bumped to match again with the same inputs (remembered patterns changed)
  })

  const matches = new LatestRequest()
  let settledKey = $state('')
  const inputKey = $derived(JSON.stringify(slots()))

  $effect(() => {
    const key = inputKey
    const snapshot = JSON.parse(key)
    result = null
    settledKey = ''
    matching = sources.length > 0
    const timer = setTimeout(async () => {
      if (!snapshot.sources.length) return
      const response = await matches.run(() => api.match(snapshot))
      if (!response) return
      if ('value' in response) {
        result = response.value
        settledKey = key
        error = ''
      } else error = response.error
      matching = false
    }, 250)
    return () => {
      clearTimeout(timer)
      matches.invalidate()
    }
  })

  // The result of the last Add stays in the bottom bar until the inputs change.
  let completionKey: string | null = null
  $effect(() => {
    const key = inputKey
    untrack(() => {
      if (!completion) return
      if (completionKey === null) completionKey = key
      else if (key !== completionKey) completion = null
    })
  })

  // Matched files' height, dragged by the grip on its bottom edge (arrow keys too) and remembered; 0 fills
  // what's left of the page. Held below the page, the page scrolls and the card keeps growing, up to the
  // height that shows every row. Grabbing the grip never scrolls the page by itself.
  const MATCH_MIN = 192
  let matchH = $state(readMatchH())
  let scroller = $state<HTMLElement>()
  let matchCard = $state<HTMLElement | null>(null)
  let matchList = $state<HTMLElement>()
  let matchGrip = $state<HTMLElement>()
  // y and h at the press; at: the pointer now; scrolled: how far the page has scrolled to follow it
  let pull: { y: number; h: number; at: number; scrolled: number; max: number; frame: number } | null = null
  function readMatchH(): number {
    try {
      const n = Number(localStorage.getItem('videoforge.matchedH'))
      return n > MATCH_MIN ? n : 0
    } catch {
      return 0
    }
  }
  function saveMatchH() {
    try {
      localStorage.setItem('videoforge.matchedH', String(matchH))
    } catch {
      // storage blocked: the height lasts until reload
    }
  }
  function fullMatchH(): number {
    if (!matchCard || !matchList) return MATCH_MIN
    return matchCard.offsetHeight - matchList.clientHeight + matchList.scrollHeight // every row showing
  }
  function setMatchH(h: number, max = fullMatchH()) {
    matchH = h <= MATCH_MIN ? 0 : Math.round(Math.min(h, Math.max(MATCH_MIN, max)))
  }
  function pullFrame() {
    if (!pull || !scroller) return
    const past = pull.at - scroller.getBoundingClientRect().bottom
    if (past > 0) {
      const p = pull
      const step = Math.min(24, Math.ceil(past / 4))
      flushSync(() => setMatchH(p.h + p.at - p.y + p.scrolled + step, p.max))
      const before = scroller.scrollTop
      scroller.scrollTop += step
      p.scrolled += scroller.scrollTop - before
    }
    pull.frame = requestAnimationFrame(pullFrame)
  }
  function pullDown(e: PointerEvent) {
    e.preventDefault()
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    const h = matchCard?.offsetHeight ?? MATCH_MIN
    pull = { y: e.clientY, h, at: e.clientY, scrolled: 0, max: fullMatchH(), frame: 0 }
    pull.frame = requestAnimationFrame(pullFrame)
  }
  function pullMove(e: PointerEvent) {
    if (!pull) return
    pull.at = e.clientY
    setMatchH(pull.h + pull.at - pull.y + pull.scrolled, pull.max)
  }
  function pullUp() {
    if (!pull) return
    cancelAnimationFrame(pull.frame)
    pull = null
    saveMatchH()
  }
  function pullKey(e: KeyboardEvent) {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    e.preventDefault()
    flushSync(() => setMatchH((matchCard?.offsetHeight ?? MATCH_MIN) + (e.key === 'ArrowDown' ? 48 : -48)))
    matchGrip?.scrollIntoView({ block: 'nearest' })
    saveMatchH()
  }

  function clearAll() {
    sources = encodes = subtitles = chapters = []
    replacements = []
    excluded = []
    assign = {}
    completion = null
    error = ''
  }

  const newJobs = $derived((result?.jobs.filter((j) => !j.existing_id).length ?? 0) + replacements.length)
  const cropWillRun = $derived(autoCrop && template?.data.crop_mode !== 'fixed')
  // What pressing Add will do, in words.
  const summary = $derived.by(() => {
    if (!sources.length) return 'Paste file paths on any page, or Browse…'
    if (matching || !result) return 'Matching…'
    const after = cropWillRun ? 'index and auto-crop' : autoIndex ? 'index' : 'neither index nor crop'
    return [
      `${newJobs} job${newJobs === 1 ? '' : 's'}`,
      template?.name ?? 'no template',
      `will ${after}`,
      output[0] ? `saved to ${output[0]}` : 'choose an output folder',
    ].join(' · ')
  })

  async function add() {
    if (adding || matching || !newJobs || settledKey !== inputKey || !output.length) return
    adding = true
    const submittedKey = settledKey
    error = ''
    try {
      const r = await api.addJobs({
        ...JSON.parse(settledKey),
        replace_existing: replacements,
        exclude_subtitles: excluded,
        original_language: language || null,
        output_dir: output[0] ?? null,
        auto_index: autoIndex,
        auto_crop: autoCrop,
        template: template && {
          ...$state.snapshot(template.data),
          encoder: $state.snapshot(encoder ?? template.data.encoder),
          mux: { ...template.data.mux, container },
        },
      })
      for (const name of r.skipped) app.addLog(`Kept existing job: ${name}`)
      for (const p of r.unmatched) app.addLog(`Not matched to any source: ${p}`)
      completion = r
      if (r.added.length && !r.skipped.length && !r.unmatched.length && inputKey === submittedKey) {
        sources = encodes = subtitles = chapters = []
        result = null
        excluded = []
        assign = {}
      }
      replacements = []
      completionKey = inputKey
      persist()
      await app.refreshJobs()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      adding = false
    }
  }
</script>

<svelte:window onbeforeunload={() => persist()} />

<div class="flex h-full flex-col">
  <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-6" bind:this={scroller}>
    <header class="flex shrink-0 flex-wrap items-center gap-3">
      <h1 class="text-xl font-semibold">New jobs</h1>
      <span class="text-sm text-muted-foreground"
        >Use Browse, or copy files as paths (Explorer: Ctrl+Shift+C) and paste them on any page, outside a text box.
        Each source file becomes one job. A folder adds a job for each source file in it, but not in its subfolders.</span
      >
    </header>

    <!-- Locked and dimmed while Add runs: a big batch on a network share can take a while. -->
    <fieldset class="contents {adding ? '[&>*]:opacity-60' : ''}" disabled={adding} aria-busy={adding}>
      <Card.Root class="@container/import shrink-0 gap-3 p-4">
        <PathSlot
          label="Sources"
          hint="MKV, MP4 or M2TS / TS files, or a folder of them"
          bind:paths={sources}
          extensions={['.mkv', '.mp4', '.m4v', '.m2ts', '.mts', '.ts']}
        />
        <details open={!!(encodes.length || subtitles.length || chapters.length)}>
          <summary class="cursor-pointer text-sm text-muted-foreground select-none">
            More inputs: encodes, subtitles, chapters
          </summary>
          <div class="mt-3 space-y-3">
            <PathSlot
              label="Encodes"
              hint="Optional. Video you've already encoded goes into the output instead of a new encode. Each one is matched to its source by name or SxxEyy."
              bind:paths={encodes}
              extensions={['.mkv', '.h264', '.264', '.hevc', '.265', '.h265', '.avc']}
            />
            {#if takesSubs}
              <PathSlot
                label="Subtitles"
                hint="Subtitle files or folders, matched to each source by name, SxxEyy or the closest name; Matched files lets you match the rest. With one source, they all go to it. A source you add none for gets the subtitles next to it, or one folder down."
                bind:paths={subtitles}
                extensions={['.srt', '.ass', '.ssa', '.sup', '.idx']}
              />
            {/if}
            <PathSlot
              label="Chapters"
              hint="Optional. Without a file, AutoQPF uses the source's chapters or adds one every 5%. You can turn AutoQPF off on the job's Output tab."
              bind:paths={chapters}
              extensions={['.txt', '.xml']}
            />
          </div>
        </details>
        <PathSlot label="Output folder" hint="Where finished files are saved" bind:paths={output} mode="folder">
          {#snippet actions()}<OutputFolderMenu onpick={(path) => (output = [path])} />{/snippet}
        </PathSlot>
        <div
          class="grid grid-cols-[minmax(0,1fr)] items-baseline gap-3 @min-[40rem]/import:grid-cols-[8rem_minmax(0,1fr)]"
        >
          <div class="text-sm text-muted-foreground">Rule set</div>
          <div class="flex flex-wrap items-center gap-3">
            <NativeSelect bind:value={ruleSet} aria-label="Rule set">
              {#each app.ruleSets as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
            </NativeSelect>
            <label class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              Original language
              <LanguagePicker
                class="w-48"
                aria-label="Original language"
                placeholder="Guess from audio"
                value={language}
                onchange={(v: string) => (language = v)}
              />
            </label>
            <p class="basis-full text-xs text-muted-foreground">
              The rule set picks each job's tracks and default settings, and checks the finished file. Manual keeps
              every track in source order for you to change.
            </p>
          </div>
          <div class="text-sm text-muted-foreground">Template</div>
          <div class="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            {#snippet templateOptions(items: { item: (typeof templateChoices)[number]; label: string }[])}
              {#each items as { item: c, label } (`${c.builtin}:${c.name}`)}
                <option value={c.name}>{label}{c.name === app.defaultTemplate(ruleSet) ? ' (default)' : ''}</option>
              {/each}
            {/snippet}
            <NativeSelect
              class="min-w-0 max-w-full"
              aria-label="Template"
              value={template?.name ?? ''}
              onchange={(e) => (templateName = e.currentTarget.value)}
            >
              {#each templateGroups as g (g.folder)}
                {#if g.folder}<optgroup label={g.folder}>{@render templateOptions(g.items)}</optgroup
                  >{:else}{@render templateOptions(g.items)}{/if}
              {/each}
            </NativeSelect>
            <button class="underline underline-offset-2" onclick={() => router.go('templates')}>Edit templates…</button>
            {#if containers.length > 1}
              <label class="flex flex-wrap items-center gap-2">
                Container
                <NativeSelect bind:value={container}>
                  {#each containers as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
                </NativeSelect>
              </label>
            {/if}
            {#if template?.data.crop_mode === 'auto'}
              <span>Crop detected per job after adding</span>
            {:else if template?.data.crop_mode === 'fixed'}
              {@const c = template.data.video.crop}
              <span>Crop {c.left}/{c.top}/{c.right}/{c.bottom} on every job</span>
            {/if}
          </div>
          <!-- self-start: the row starts with a checkbox, whose baseline moves with its tick; its first line is at the top -->
          <div class="self-start text-sm text-muted-foreground">After adding</div>
          <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span class="flex items-center gap-2">
              <label class="flex items-center gap-2">
                <Checkbox
                  checked={autoIndex}
                  aria-describedby="new-jobs-index-help"
                  onCheckedChange={(v) => (autoIndex = v === true)}
                />Index
              </label>
              <span id="new-jobs-index-help" class="text-xs text-muted-foreground"
                >(indexes each job in the background for its preview)</span
              >
            </span>
            <label class="flex items-center gap-2">
              <Checkbox checked={autoCrop} onCheckedChange={(v) => (autoCrop = v === true)} />Auto-crop
              <span class="text-xs text-muted-foreground">(indexes first)</span>
            </label>
            <span class="text-xs text-muted-foreground"
              >These two apply to this batch. Their defaults are in Settings › Queue & indexing.</span
            >
          </div>
          {#if encoder}
            <div class="text-sm text-muted-foreground">Encoder preset</div>
            <div class="min-w-0 space-y-2">
              <div class="flex flex-wrap items-center gap-3">
                <EncoderPresetMenu
                  {ruleSet}
                  current={encoder}
                  apply={(value) => {
                    encoder = value
                  }}
                />
                <span class="text-xs text-muted-foreground"
                  >{ENCODERS.find(([id]) => id === encoder?.encoder)?.[1]} · {encoder.depth}-bit</span
                >
                <button
                  class="text-xs underline underline-offset-2"
                  onclick={() => {
                    encoder = structuredClone($state.snapshot(template.data.encoder))
                  }}>Use template settings</button
                >
              </div>
              <p class="text-xs text-muted-foreground">
                Changes encoder settings only. Resize and filters come from the template.
              </p>
            </div>
          {/if}
        </div>
      </Card.Root>

      <!-- Grows with the matched jobs, and keeps its size while they match again; with no sources it's only its header line. -->
      <Card.Root
        bind:ref={matchCard}
        class="{result || matching ? 'min-h-48 flex-1' : ''} shrink-0 gap-0 py-0"
        style={(result || matching) && matchH ? `min-height:${matchH}px` : undefined}
      >
        <div class="flex shrink-0 flex-wrap items-center gap-3 px-4 py-2">
          <h2 class="font-medium">Matched files</h2>
          <span class="text-sm text-muted-foreground">
            {#if matching}Matching…{:else if result}{result.jobs.length} job(s){result.unmatched.length
                ? ` · ${result.unmatched.length} unmatched`
                : ''}{:else}Add a source to see the jobs{/if}
          </span>
          {#if result && !matching && odd.size}<span class="text-sm text-warning">{oddSummary(odd)}</span>{/if}
          {#if result && !matching && wrongEpisode}<span class="text-sm text-destructive"
              >{wrongEpisode} subtitle{wrongEpisode === 1 ? '' : 's'} named for another episode</span
            >{/if}
          {#if shownResult}
            <Button size="sm" variant="outline" class="ml-auto" onclick={() => review()}
              ><ListChecksIcon />Review matches{needsLook ? ` · ${needsLook} to check` : ''}</Button
            >
          {/if}
        </div>
        {#if result}
          <div class="min-h-0 flex-1 overflow-auto border-t" bind:this={matchList}>
            <MatchTable {result} bind:replacements bind:excluded bind:assign {odd} onreview={review} />
          </div>
          <!-- Drag down to show more rows (arrow keys too); double-click goes back to filling the page. A
             focusable separator is the window splitter pattern, which Svelte's a11y check doesn't know. -->
          <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
          <div
            bind:this={matchGrip}
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize Matched files"
            aria-valuenow={matchH || MATCH_MIN}
            aria-valuemin={MATCH_MIN}
            aria-valuetext={matchH ? `${matchH} pixels tall` : 'Fills the page'}
            tabindex="0"
            class="group flex h-3 shrink-0 cursor-row-resize touch-none items-center justify-center rounded-b-xl border-t outline-none select-none"
            onpointerdown={pullDown}
            onpointermove={pullMove}
            onpointerup={pullUp}
            onpointercancel={pullUp}
            onkeydown={pullKey}
            ondblclick={() => (setMatchH(0), saveMatchH())}
          >
            <div
              class="h-1 w-10 rounded-full bg-border transition-colors group-hover:bg-primary group-focus-visible:bg-primary"
            ></div>
          </div>
        {/if}
      </Card.Root>
    </fieldset>
    <MatchDialog
      bind:open={reviewing}
      result={shownResult}
      {matching}
      bind:assign
      focus={reviewFocus}
      onforget={() => rematch++}
    />
  </div>

  {#if completion && (completion.kept.length || completion.unmatched.length)}
    <details class="max-h-48 shrink-0 overflow-auto border-t bg-card px-6 py-2 text-sm" open={!completion.added.length}>
      <summary class="cursor-pointer">Review kept and unmatched files</summary>
      <ul class="mt-2 space-y-2">
        {#each completion.kept as kept}
          <li>
            <Tip text={kept.source}>{kept.name}: {kept.reason}.</Tip>
            {#if kept.id}<Button size="sm" variant="link" onclick={() => router.go('queue', kept.id)}
                >Open existing job</Button
              >{/if}
          </li>
        {/each}
        {#each completion.unmatched as path}
          <li class="break-all">{path} matches no source. Add its source, or pick one for it in Matched files.</li>
        {/each}
      </ul>
    </details>
  {/if}
  <footer class="h-(--bar-h) shrink-0 border-t bg-card" aria-label="Add to queue">
    <div class="flex h-full items-center gap-3 overflow-hidden px-6">
      {#if completion}
        <p role="status" class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium">
          {#if completion.added.length}<CheckIcon class="size-4 shrink-0 text-success" />{/if}
          <span class="truncate">
            {#if completion.added.length}Added {completion.added.length} job{completion.added.length === 1
                ? ''
                : 's'}{:else}Nothing added{/if}{completion.skipped.length
              ? ` · ${completion.skipped.length} already in the queue, kept`
              : ''}{completion.unmatched.length ? ` · ${completion.unmatched.length} unmatched` : ''}
          </span>
        </p>
        {#if sources.length}<Button variant="ghost" onclick={() => (completion = null)}>Keep editing</Button>{/if}
        <Button variant="outline" onclick={clearAll}>Add more</Button>
        {#if completion.added.length}
          <Button onclick={() => router.go('queue', completion?.added[0] ?? null)}>Open queue</Button>
        {/if}
      {:else}
        {#if adding}
          <p role="status" class="flex min-w-0 flex-1 items-center gap-2 text-sm">
            <LoaderCircleIcon class="size-4 shrink-0 animate-spin text-muted-foreground" />
            <span class="truncate">Adding {newJobs} job{newJobs === 1 ? '' : 's'} to the queue…</span>
          </p>
        {:else}
          <p class="min-w-0 flex-1 truncate text-sm {sources.length ? '' : 'text-muted-foreground'}" title={summary}>
            {summary}
          </p>
        {/if}
        {#if error}<span class="text-sm text-destructive">{error}</span>{/if}
        {#if sources.length}<Button variant="outline" disabled={adding} onclick={clearAll}>Clear all</Button>{/if}
        <Button disabled={!newJobs || matching || settledKey !== inputKey || adding || !output.length} onclick={add}>
          {#if adding}<LoaderCircleIcon class="animate-spin" />Adding…{:else}<PlusIcon />Add {newJobs
              ? `${newJobs} job${newJobs === 1 ? '' : 's'}`
              : ''} to queue{/if}
        </Button>
      {/if}
    </div>
  </footer>
</div>
