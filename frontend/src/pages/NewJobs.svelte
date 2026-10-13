<script lang="ts">
  // New jobs: profile + language, input slots, output folder, live match preview, Add to queue.
  import { onMount } from 'svelte'
  import Icon from '../components/Icon.svelte'
  import PathSlot from '../components/PathSlot.svelte'
  import { api } from '../lib/api'
  import { basename, debounce, LANGUAGES } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { app } from '../lib/state.svelte'
  import type { MatchResult } from '../lib/types'

  let profile = $state('')
  let language = $state('')
  let sources = $state<string[]>([])
  let encodes = $state<string[]>([])
  let subtitles = $state<string[]>([])
  let chapters = $state<string[]>([])
  let output = $state<string[]>([])
  let result = $state<MatchResult | null>(null)
  let matching = $state(false)
  let error = $state('')
  let adding = $state(false)
  // Indexes into the preset choices; 0 is the profile's defaults (sent as nothing).
  let videoPreset = $state(0)
  let encoderPreset = $state(0)
  const videoChoices = $derived(app.presetChoices('video', profile))
  const encoderChoices = $derived(app.presetChoices('encoder', profile))

  const takesSubs = $derived(app.profiles.find(p => p.id === profile)?.external_subtitles ?? true)

  onMount(async () => {
    profile = app.defaultProfile?.id ?? ''
    const s = await api.settings().catch(() => null)
    if (s?.output_dir) output = [s.output_dir]
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

  const rematch = debounce(async () => {
    if (!sources.length) {
      result = null
      matching = false
      return
    }
    try {
      result = await api.match(slots())
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      result = null
    } finally {
      matching = false
    }
  }, 250)

  $effect(() => {
    // re-run when any slot or the profile changes
    void [sources.length, encodes.length, subtitles.length, chapters.length, profile, takesSubs]
    matching = sources.length > 0
    rematch()
  })

  async function add() {
    adding = true
    error = ''
    try {
      const r = await api.addJobs({
        ...slots(),
        original_language: language || null,
        output_dir: output[0] ?? null,
        video: videoPreset ? $state.snapshot(videoChoices[videoPreset]?.data) : undefined,
        encoder: encoderPreset ? $state.snapshot(encoderChoices[encoderPreset]?.data) : undefined,
      })
      for (const name of r.skipped) app.addLog(`Skipped ${name}: it is queued or running`)
      for (const p of r.unmatched) app.addLog(`Not matched to any source: ${p}`)
      sources = encodes = subtitles = chapters = []
      result = null
      await app.refreshJobs()
      router.go('queue', r.added[0] ?? null)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      adding = false
    }
  }
</script>

<div class="flex h-full flex-col gap-4 overflow-auto p-6">
  <header class="flex items-center gap-3">
    <h1 class="text-xl font-semibold">New jobs</h1>
    <span class="text-sm text-muted">One job per source; a folder of episodes makes a batch.</span>
  </header>

  <section class="panel space-y-3 p-4">
    <div class="grid grid-cols-[8rem_1fr] items-center gap-3">
      <div class="text-sm text-muted">Profile</div>
      <div class="flex flex-wrap items-center gap-3">
        <select class="field" bind:value={profile}>
          {#each app.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
        </select>
        <label class="flex items-center gap-2 text-sm text-muted">
          Original language
          <input class="field w-44" list="languages" placeholder="Guess from audio" bind:value={language} />
        </label>
        <datalist id="languages">
          {#each LANGUAGES as [tag, name] (tag)}<option value={tag}>{name}</option>{/each}
        </datalist>
      </div>
      <div class="text-sm text-muted">Presets</div>
      <div class="flex flex-wrap items-center gap-3 text-sm text-muted">
        <label class="flex items-center gap-2">
          Video
          <select class="field" bind:value={videoPreset}>
            {#each videoChoices as c, i (i)}<option value={i}>{c.name}</option>{/each}
          </select>
        </label>
        <label class="flex items-center gap-2">
          Encoder
          <select class="field" bind:value={encoderPreset}>
            {#each encoderChoices as c, i (i)}<option value={i}>{c.name}</option>{/each}
          </select>
        </label>
      </div>
    </div>
    <PathSlot label="Sources" hint="Remux MKVs, or a folder of them" bind:paths={sources} extensions={['.mkv']} />
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
  </section>

  <section class="panel flex min-h-48 flex-1 flex-col">
    <div class="flex items-center gap-3 border-b border-line px-4 py-2">
      <h2 class="font-medium">Matched files</h2>
      <span class="text-sm text-muted">
        {#if matching}Matching…{:else if result}{result.jobs.length} job(s){result.unmatched.length
            ? ` · ${result.unmatched.length} unmatched`
            : ''}{:else}Add a source to see the jobs{/if}
      </span>
    </div>
    <div class="min-h-0 flex-1 overflow-auto">
      {#if result}
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-panel text-left text-xs text-muted uppercase">
            <tr><th class="px-4 py-2">Source</th><th>Video</th><th>Subtitles</th><th>Chapters</th></tr>
          </thead>
          <tbody>
            {#each result.jobs as j (j.source)}
              <tr class="border-t border-line/60">
                <td class="px-4 py-1.5" title={j.source}>{basename(j.source)}</td>
                <td class={j.encode ? (j.encode_state === 'in_progress' ? 'text-warn' : '') : 'text-accent'}>
                  {j.encode ? basename(j.encode) + (j.encode_state === 'in_progress' ? ' (still encoding)' : '') : 'encode with VapourSynth'}
                </td>
                <td class="text-muted">{j.subtitles.map(basename).join(', ') || '—'}</td>
                <td class="text-muted">{j.chapters ? basename(j.chapters) : 'AutoQPF'}</td>
              </tr>
            {/each}
            {#each result.unmatched as p (p)}
              <tr class="border-t border-line/60 text-muted">
                <td class="px-4 py-1.5" colspan="4">Not matched to any source: {basename(p)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <footer class="flex items-center gap-3">
    {#if error}<span class="text-sm text-bad">{error}</span>{/if}
    <button class="btn ml-auto" onclick={() => (sources = encodes = subtitles = chapters = [])}>Clear</button>
    <button class="btn-primary" disabled={!result?.jobs.length || adding || !output.length} onclick={add}>
      <Icon name="new" />Add {result?.jobs.length ? `${result.jobs.length} job(s)` : ''} to queue
    </button>
  </footer>
</div>
