<script lang="ts">
  // New jobs: profile + language, input slots, output folder, live match preview, Add to queue.
  import { onDestroy, onMount, untrack } from 'svelte'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Card from '$lib/components/ui/card'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import PathSlot from '../components/PathSlot.svelte'
  import EncoderPresetMenu from '../components/EncoderPresetMenu.svelte'
  import { api } from '../lib/api'
  import { drafts } from '../lib/drafts'
  import { basename, LANGUAGES } from '../lib/format'
  import { LatestRequest } from '../lib/latestRequest'
  import { router } from '../lib/router.svelte'
  import { app } from '../lib/state.svelte'
  import { ENCODERS, type EncoderSettings, type MatchResult } from '../lib/types'

  type ImportResult = Awaited<ReturnType<typeof api.addJobs>>
  type Draft = { profile: string; language: string; sources: string[]; encodes: string[]; subtitles: string[]; chapters: string[]; output: string[]; templateName: string | null; encoder: EncoderSettings | null; container: string; completion?: ImportResult | null }
  const restored = drafts.read<Draft>('new-jobs')
  let profile = $state(restored?.profile ?? '')
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
  // The template (by name; the profile's starred one first) and the container it sets, which can
  // be changed here.
  let templateName = $state<string | null>(restored?.templateName ?? null)
  let encoder = $state<EncoderSettings | null>(restored?.encoder ?? null)
  let container = $state(restored?.container ?? '')
  const templateChoices = $derived(app.presetChoices('template', profile))
  const template = $derived(templateChoices.find(c => c.name === (templateName ?? app.defaultTemplate(profile))) ?? templateChoices[0])
  const templateKey = $derived(JSON.stringify([profile, templateName ?? app.defaultTemplate(profile)]))
  let previousProfile = restored?.profile ?? ''
  let appliedKey = restored ? JSON.stringify([restored.profile, restored.templateName]) : ''

  function persist() {
    drafts.write('new-jobs', $state.snapshot({ profile, language, sources, encodes, subtitles, chapters, output,
      templateName: template?.name ?? templateName, encoder, container, completion }))
  }
  onDestroy(persist)
  const containers = $derived(app.profiles.find(p => p.id === profile)?.containers ?? [])

  $effect(() => {
    // A manual selection survives preset saves; a profile switch starts on its default.
    if (profile !== previousProfile) { previousProfile = profile; templateName = null }
  })
  $effect(() => {
    // Switching templates resets the override, but saving/renaming an encoder preset does not.
    if (!template || template.name !== (templateName ?? app.defaultTemplate(profile)) || templateKey === appliedKey) return
    appliedKey = templateKey
    untrack(() => {
      encoder = template ? structuredClone($state.snapshot(template.data.encoder)) : null
      const own = template?.data.mux.container
      container = containers.some(c => c.id === own) ? own! : (containers[0]?.id ?? '')
    })
  })

  const takesSubs = $derived(app.profiles.find(p => p.id === profile)?.external_subtitles ?? true)

  onMount(async () => {
    if (!profile) profile = app.defaultProfile?.id ?? ''
    const s = await api.settings().catch(() => null)
    if (s?.output_dir && !output.length) output = [s.output_dir]
  })

  $effect(() => {
    if (!profile && app.defaultProfile) profile = app.defaultProfile.id
  })

  const slots = () => ({
    sources,
    encodes,
    subtitles: takesSubs ? subtitles : [],
    chapters,
    profile,
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
      if ('value' in response) { result = response.value; settledKey = key; error = '' }
      else error = response.error
      matching = false
    }, 250)
    return () => { clearTimeout(timer); matches.invalidate() }
  })

  async function add() {
    if (adding || matching || !result?.jobs.length || settledKey !== inputKey) return
    adding = true
    const submittedKey = settledKey
    error = ''
    try {
      const r = await api.addJobs({
        ...JSON.parse(settledKey),
        replace_existing: replacements,
        original_language: language || null,
        output_dir: output[0] ?? null,
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

<div class="flex h-full flex-col gap-4 overflow-auto p-6">
  <header class="flex shrink-0 flex-wrap items-center gap-3">
    <h1 class="text-xl font-semibold">New jobs</h1>
    <span class="text-sm text-muted-foreground">One job per source; a folder of episodes makes a batch.</span>
  </header>

  {#if completion}
    <section class="shrink-0 space-y-2 rounded-lg border p-4 text-sm" aria-label="Import results">
      <p role="status" class="font-medium">Added {completion.added.length} · Kept existing {completion.skipped.length} · Unmatched {completion.unmatched.length}</p>
      {#if completion.skipped.length || completion.unmatched.length || !completion.added.length}
        <p class="text-muted-foreground">Your input draft is retained below. Review existing jobs or correct unmatched files before trying again.</p>
      {/if}
      {#if completion.kept.length || completion.unmatched.length}
        <details open={!completion.added.length}>
          <summary class="cursor-pointer">Review skipped and unmatched files</summary>
          <ul class="mt-2 space-y-2">
            {#each completion.kept as kept}
              <li><span title={kept.source}>{kept.name}: {kept.reason}.</span>
                {#if kept.id}<Button size="sm" variant="link" onclick={() => router.go('queue', kept.id)}>Open existing job</Button>{/if}
              </li>
            {/each}
            {#each completion.unmatched as path}
              <li class="break-all">{path}: no matching source. Add its source or correct the filename.</li>
            {/each}
          </ul>
        </details>
      {/if}
      <Button size="sm" onclick={() => router.go('queue', completion?.added[0] ?? null)}>Open queue</Button>
      <Button size="sm" variant="ghost" onclick={() => { completion = null; persist() }}>Dismiss results</Button>
    </section>
  {/if}

  <Card.Root class="@container/import shrink-0 gap-3 p-4">
    <div class="grid grid-cols-[minmax(0,1fr)] items-center gap-3 @min-[40rem]/import:grid-cols-[8rem_minmax(0,1fr)]">
      <div class="text-sm text-muted-foreground">Profile</div>
      <div class="flex flex-wrap items-center gap-3">
        <NativeSelect bind:value={profile} aria-label="Profile">
          {#each app.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
        </NativeSelect>
        <label class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          Original language
          <Input class="w-44" list="languages" placeholder="Guess from audio" bind:value={language} />
        </label>
        <datalist id="languages">
          {#each LANGUAGES as [tag, name] (tag)}<option value={tag}>{name}</option>{/each}
        </datalist>
      </div>
      <div class="text-sm text-muted-foreground">Template</div>
      <div class="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
        <NativeSelect class="min-w-0 max-w-full" aria-label="Template" value={template?.name ?? ''} onchange={e => (templateName = e.currentTarget.value)}>
          {#each templateChoices as c (`${c.builtin}:${c.name}`)}
            <option value={c.name}>{c.name}{c.name === app.defaultTemplate(profile) ? ' (default)' : ''}</option>
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
      {#if encoder}
        <div class="text-sm text-muted-foreground">Encoder preset</div>
        <div class="min-w-0 space-y-2">
          <div class="flex flex-wrap items-center gap-3">
            <EncoderPresetMenu {profile} current={encoder} apply={value => { encoder = value }} />
            <span class="text-xs text-muted-foreground">{ENCODERS.find(([id]) => id === encoder?.encoder)?.[1]} · {encoder.depth}-bit</span>
            <button class="text-xs underline underline-offset-2" onclick={() => { encoder = structuredClone($state.snapshot(template.data.encoder)) }}>Use template settings</button>
          </div>
          <p class="text-xs text-muted-foreground">Changes encoder settings only. Resize and filters come from the template.</p>
        </div>
      {/if}
    </div>
    <PathSlot
      label="Sources"
      hint="MKV, MP4 or M2TS / TS files, or a folder of them"
      bind:paths={sources}
      extensions={['.mkv', '.mp4', '.m4v', '.m2ts', '.mts', '.ts']}
    />
    <PathSlot
      label="Encodes"
      hint="Optional: existing encodes (e.g. StaxRip) to mux instead of encoding the video"
      bind:paths={encodes}
      extensions={['.mkv', '.h264', '.264', '.hevc', '.265', '.h265', '.avc']}
    />
    {#if takesSubs}
      <PathSlot
        label="Subtitles"
        hint="SRTs or folders, matched by name or SxxEyy (plus those next to the source)"
        bind:paths={subtitles}
        extensions={['.srt', '.ass', '.ssa', '.sup']}
      />
    {/if}
    <PathSlot label="Chapters" hint="Optional; otherwise AutoQPF reads or makes them" bind:paths={chapters} extensions={['.txt', '.xml']} />
    <PathSlot label="Output folder" hint="Where the muxed releases go" bind:paths={output} mode="folder" />
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
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-card text-left text-xs text-muted-foreground uppercase">
            <tr><th class="px-4 py-2">Source</th><th>Video</th><th>Subtitles</th><th>Chapters</th></tr>
          </thead>
          <tbody>
            {#each result.jobs as j (j.source)}
              <tr class="border-t border-border/60">
                <td class="px-4 py-1.5" title={j.source}>
                  {basename(j.source)}
                  {#if j.existing_id}
                    <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <button class="underline" onclick={() => router.go('queue', j.existing_id)}>Open existing job</button>
                      {#if ['queued', 'running', 'indexing'].includes(j.existing_status ?? '')}
                        <span>Kept: {j.existing_status}</span>
                      {:else}
                        <label class="flex items-center gap-1"><Checkbox checked={replacements.includes(j.existing_id)}
                          onCheckedChange={on => { replacements = on ? [...replacements, j.existing_id!] : replacements.filter(id => id !== j.existing_id) }} />Replace and reset its edits</label>
                      {/if}
                    </div>
                  {/if}
                </td>
                <td class={j.encode ? (j.encode_state === 'in_progress' ? 'text-warning' : '') : 'text-primary'}>
                  {j.encode ? basename(j.encode) + (j.encode_state === 'in_progress' ? ' (still encoding)' : '') : 'encode with VapourSynth'}
                </td>
                <td class="text-muted-foreground">{j.subtitles.map(basename).join(', ') || '—'}</td>
                <td class="text-muted-foreground">{j.chapters ? basename(j.chapters) : 'AutoQPF'}</td>
              </tr>
            {/each}
            {#each result.unmatched as p (p)}
              <tr class="border-t border-border/60 text-muted-foreground">
                <td class="px-4 py-1.5" colspan="4">Not matched to any source: {basename(p)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </Card.Root>

  <footer class="flex shrink-0 flex-wrap items-center gap-3">
    {#if error}<span class="text-sm text-destructive">{error}</span>{/if}
    <Button variant="outline" class="ml-auto" onclick={() => (sources = encodes = subtitles = chapters = [])}>Clear</Button>
    <Button disabled={!result?.jobs.length || matching || settledKey !== inputKey || adding || !output.length} onclick={add}>
      <PlusIcon />Add {result?.jobs.length ? `${result.jobs.length} job(s)` : ''} to queue
    </Button>
  </footer>
</div>
