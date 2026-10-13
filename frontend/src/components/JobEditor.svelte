<script lang="ts">
  // One job, StaxRip-style: issues on top, then Video | Encoder | Tracks | Output | Log.
  // Changes save straight away (the server replans); a queued or running job is read-only.
  import { api, type SpecChanges } from '../lib/api'
  import { basename, SEVERITY_TONE, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import type { CommandStep, EncoderSettings, JobDetail } from '../lib/types'
  import EncoderPanel from './EncoderPanel.svelte'
  import Icon from './Icon.svelte'
  import FileBrowser from './FileBrowser.svelte'
  import TracksTab from './TracksTab.svelte'
  import JobLog from './JobLog.svelte'
  import VideoTab from './VideoTab.svelte'

  let { jobId }: { jobId: string } = $props()

  type Tab = 'video' | 'encoder' | 'tracks' | 'output' | 'log'
  let tab = $state<Tab>('video')
  let job = $state<JobDetail | null>(null)
  let error = $state('')
  let commands = $state<CommandStep[]>([])
  let showInfo = $state(false)
  let browsing = $state(false)

  async function load() {
    try {
      job = await api.job(jobId)
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  $effect(() => {
    void jobId
    void app.versions[jobId]
    load()
  })

  $effect(() => {
    if (tab === 'encoder' && job?.plan) {
      void job.spec.encoder
      api.commands(jobId).then(c => (commands = c)).catch(() => (commands = []))
    }
  })

  async function save(changes: SpecChanges) {
    try {
      job = await api.update(jobId, changes)
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  async function resetEncoder() {
    const p = app.profiles.find(x => x.id === job?.profile)
    if (p) await save({ encoder: structuredClone($state.snapshot(p.defaults.encoder)) as EncoderSettings })
  }

  const editable = $derived(!!job && !['queued', 'running'].includes(job.status))
  const TABS: { id: Tab; label: string }[] = [
    { id: 'video', label: 'Video' },
    { id: 'encoder', label: 'Encoder' },
    { id: 'tracks', label: 'Audio & subtitles' },
    { id: 'output', label: 'Output' },
    { id: 'log', label: 'Log' },
  ]
  const problems = $derived((job?.issues ?? []).filter(i => i.severity !== 'info'))
</script>

{#if !job}
  <div class="p-6 text-muted">{error || 'Loading…'}</div>
{:else}
  <div class="flex h-full min-h-0 flex-col">
    <header class="space-y-2 border-b border-line px-5 py-3">
      <div class="flex items-center gap-3">
        <h2 class="truncate text-lg font-semibold" title={job.source}>{job.name}</h2>
        <span class="text-sm {STATUS_TONE[job.status]}">{STATUS_LABEL[job.status]}</span>
        <span class="text-sm text-muted">· {job.profile} · {job.encoder}{job.plan ? ` · ${job.plan.resolution}` : ''}</span>
        {#if !editable}<span class="rounded bg-info/15 px-2 py-0.5 text-xs text-info">locked while {job.status}</span>{/if}
      </div>
      {#if job.progress && job.status === 'running'}
        <div class="flex items-center gap-3 text-xs text-muted">
          <div class="h-1.5 flex-1 overflow-hidden rounded bg-raised">
            <div class="h-full bg-info transition-[width]" style="width:{job.progress.overall * 100}%"></div>
          </div>
          <span>{job.progress.step} · {(job.progress.fraction * 100).toFixed(1)}%</span>
        </div>
      {/if}
      {#if problems.length}
        <button class="w-full text-left text-sm" onclick={() => (showInfo = !showInfo)}>
          {#each problems.slice(0, showInfo ? problems.length : 2) as i, n (n)}
            <div class={SEVERITY_TONE[i.severity]}>
              <Icon name="alert" size={13} class="mr-1 inline" />{i.message}
              <span class="text-xs text-muted">{i.code}</span>
            </div>
          {/each}
          {#if !showInfo && problems.length > 2}<div class="text-xs text-muted">+{problems.length - 2} more…</div>{/if}
        </button>
      {/if}
      {#if (job.status === 'failed' || job.status === 'invalid') && tab !== 'log'}
        <button class="text-xs text-accent underline" onclick={() => (tab = 'log')}>Open the failed step in the Log tab</button>
      {/if}
      {#if error}<div class="text-sm text-bad">{error}</div>{/if}
      <nav class="-mb-3 flex gap-1">
        {#each TABS as t (t.id)}
          <button
            class="border-b-2 px-3 py-2 text-sm {tab === t.id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}"
            onclick={() => (tab = t.id)}>{t.label}</button
          >
        {/each}
      </nav>
    </header>

    <div class="min-h-0 flex-1 overflow-auto p-5">
      {#if tab === 'video'}
        {#if job.spec.inputs.encode}
          <p class="text-muted">This job reuses an existing encode ({basename(job.spec.inputs.encode)}); there is no video step.</p>
        {:else}
          <VideoTab {job} {editable} save={video => save({ video })} />
        {/if}
      {:else if tab === 'encoder'}
        <div class="grid max-w-5xl gap-6 xl:grid-cols-[1fr_1fr]">
          <div>
            <EncoderPanel value={job.spec.encoder} disabled={!editable} onchange={encoder => save({ encoder })} />
            <button class="btn mt-4" disabled={!editable} onclick={resetEncoder}><Icon name="refresh" />Profile defaults</button>
          </div>
          <div class="space-y-2">
            <span class="label">Commands this job runs</span>
            {#each commands as c (c.id)}
              <div class="rounded-md border border-line bg-black/30 p-2">
                <div class="text-xs text-accent">{c.label}</div>
                <code class="block text-[11px] break-all text-muted">{c.command}</code>
              </div>
            {:else}
              <p class="text-sm text-muted">Available once the source is probed.</p>
            {/each}
          </div>
        </div>
      {:else if tab === 'tracks'}
        <TracksTab {job} {editable} save={overrides => save({ overrides })} />
      {:else if tab === 'output'}
        <div class="max-w-3xl space-y-5">
          <div class="grid grid-cols-[8rem_1fr] items-center gap-3 text-sm">
            <span class="text-muted">Output folder</span>
            <div class="flex gap-2">
              <input
                class="field flex-1 font-mono text-xs"
                value={job.spec.output_dir ?? ''}
                disabled={!editable}
                onchange={e => save({ output_dir: (e.target as HTMLInputElement).value.trim() || null })}
              />
              <button class="btn" disabled={!editable} onclick={() => (browsing = true)}><Icon name="folder" />Browse…</button>
            </div>
            <span class="text-muted">Chapters</span>
            <label class="flex items-center gap-2">
              <input type="checkbox" checked={job.spec.qpf} disabled={!editable} onchange={e => save({ qpf: (e.target as HTMLInputElement).checked })} />
              AutoQPF: chapters from the source (or every 5%) and keyframes on them
            </label>
            <span class="text-muted">Profile</span>
            <select class="field w-48" value={job.profile} disabled={!editable} onchange={e => save({ profile: (e.target as HTMLSelectElement).value })}>
              {#each app.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
            </select>
            <span class="text-muted">Work folder</span>
            <code class="text-xs break-all text-muted">{job.source}_tmp</code>
            <span class="text-muted">Output</span>
            <code class="text-xs break-all text-muted">{job.output ?? '(after the run)'}</code>
          </div>
          {#if Object.keys(job.steps).length}
            <div>
              <span class="label">Finished steps (reused on the next run if nothing they depend on changed)</span>
              <ul class="mt-2 space-y-1 text-sm">
                {#each Object.values(job.steps) as s (s.id)}
                  <li class="flex gap-3"><Icon name="check" class="text-ok" /><span class="w-28">{s.id}</span><span class="text-muted">{s.seconds}s</span></li>
                {/each}
              </ul>
            </div>
          {/if}
        </div>
      {:else}
        <JobLog {jobId} running={job.status === 'running'} />
      {/if}
    </div>
  </div>
{/if}

{#if browsing && job}
  <FileBrowser
    title="Output folder"
    mode="folder"
    start={job.spec.output_dir ?? ''}
    onpick={paths => {
      browsing = false
      if (paths[0]) save({ output_dir: paths[0] })
    }}
    onclose={() => (browsing = false)}
  />
{/if}
