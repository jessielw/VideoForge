<script lang="ts">
  // New jobs: rule set + language, input slots, output folder, live match preview, Add to queue.
  import { onDestroy, onMount, untrack } from 'svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
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
  import MatchTable from '../components/MatchTable.svelte'
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

  // Paths pasted anywhere in the app, or picked with "Add files…".
  $effect(() => {
    if (!incoming.pending.length) return
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

  function clearAll() {
    sources = encodes = subtitles = chapters = []
    replacements = []
    completion = null
    error = ''
  }

  const newJobs = $derived((result?.jobs.filter((j) => !j.existing_id).length ?? 0) + replacements.length)
  const cropWillRun = $derived(autoCrop && template?.data.crop_mode !== 'fixed')
  // What pressing Add will do, in words.
  const summary = $derived.by(() => {
    if (!sources.length) return 'Paste file paths anywhere, or Browse…'
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
  <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-6">
    <header class="flex shrink-0 flex-wrap items-center gap-3">
      <h1 class="text-xl font-semibold">New jobs</h1>
      <span class="text-sm text-muted-foreground"
        >Paste file paths anywhere, or Browse. One job per source; a folder of episodes makes a batch.</span
      >
    </header>

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
            hint="Optional: existing encodes (e.g. StaxRip) to mux instead of encoding the video"
            bind:paths={encodes}
            extensions={['.mkv', '.h264', '.264', '.hevc', '.265', '.h265', '.avc']}
          />
          {#if takesSubs}
            <PathSlot
              label="Subtitles"
              hint="Subtitle files or folders, matched by name or SxxEyy (plus those next to the source)"
              bind:paths={subtitles}
              extensions={['.srt', '.ass', '.ssa', '.sup', '.idx']}
            />
          {/if}
          <PathSlot
            label="Chapters"
            hint="Optional; otherwise AutoQPF reads or makes them"
            bind:paths={chapters}
            extensions={['.txt', '.xml']}
          />
        </div>
      </details>
      <PathSlot label="Output folder" hint="Where the muxed releases go" bind:paths={output} mode="folder">
        {#snippet actions()}<OutputFolderMenu onpick={(path) => (output = [path])} />{/snippet}
      </PathSlot>
      <div class="grid grid-cols-[minmax(0,1fr)] items-center gap-3 @min-[40rem]/import:grid-cols-[8rem_minmax(0,1fr)]">
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
        <div class="text-sm text-muted-foreground">After adding</div>
        <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <label class="flex items-center gap-2">
            <Checkbox checked={autoIndex} onCheckedChange={(v) => (autoIndex = v === true)} />Index
          </label>
          <label class="flex items-center gap-2">
            <Checkbox checked={autoCrop} onCheckedChange={(v) => (autoCrop = v === true)} />Auto-crop
            <span class="text-xs text-muted-foreground">(indexes first)</span>
          </label>
          <span class="text-xs text-muted-foreground">For this batch; defaults are in Settings.</span>
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

    <Card.Root class="min-h-48 flex-1 shrink-0 gap-0 py-0">
      <div class="flex shrink-0 flex-wrap items-center gap-3 border-b px-4 py-2">
        <h2 class="font-medium">Matched files</h2>
        <span class="text-sm text-muted-foreground">
          {#if matching}Matching…{:else if result}{result.jobs.length} job(s){result.unmatched.length
              ? ` · ${result.unmatched.length} unmatched`
              : ''}{:else}Add a source to see the jobs{/if}
        </span>
      </div>
      <div class="min-h-0 flex-1 overflow-auto">
        {#if result}
          <MatchTable {result} bind:replacements />
        {/if}
      </div>
    </Card.Root>
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
          <li class="break-all">{path}: no matching source. Add its source or correct the filename.</li>
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
        <p class="min-w-0 flex-1 truncate text-sm {sources.length ? '' : 'text-muted-foreground'}" title={summary}>
          {summary}
        </p>
        {#if error}<span class="text-sm text-destructive">{error}</span>{/if}
        {#if sources.length}<Button variant="outline" onclick={clearAll}>Clear</Button>{/if}
        <Button disabled={!newJobs || matching || settledKey !== inputKey || adding || !output.length} onclick={add}>
          <PlusIcon />Add {newJobs ? `${newJobs} job${newJobs === 1 ? '' : 's'}` : ''} to queue
        </Button>
      {/if}
    </div>
  </footer>
</div>
