<script lang="ts">
  // One job, StaxRip-style: issues on top, then Video | Encoder | Audio | Subtitles | Output | Log.
  // Changes save straight away (the server replans); a queued, running or indexing job is read-only.
  // Queue (top left, and the tick on its queue row) locks the job for the run: the queue runs it.
  import { api, type SpecChanges } from '../lib/api'
  import { saves } from '../lib/saves'
  import { basename, duration, SEVERITY_TONE, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { queueable } from '../lib/queueView'
  import { app } from '../lib/state.svelte'
  import type { CommandStep, JobDetail } from '../lib/types'
  import EncoderPanel from './EncoderPanel.svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import { toast } from 'svelte-sonner'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as Tabs from '$lib/components/ui/tabs'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import TemplateMenu from './TemplateMenu.svelte'
  import FileBrowser from './FileBrowser.svelte'
  import { pastedPaths, pathDrop } from '../lib/dropPaths.svelte'
  import TrackEditor from './TrackEditor.svelte'
  import TracksTab from './TracksTab.svelte'
  import JobLog from './JobLog.svelte'
  import VideoTab from './VideoTab.svelte'

  let { jobId }: { jobId: string } = $props()

  type Tab = 'video' | 'encoder' | 'audio' | 'subs' | 'output' | 'log'
  let tab = $state<Tab>('video')
  let job = $state<JobDetail | null>(null)
  let error = $state('')
  let commands = $state<CommandStep[]>([])
  let showInfo = $state(false)
  let browsing = $state<'output' | 'chapters' | null>(null)

  // Saves: each change applies to `job.spec` at once, so the next edit builds on it, and goes
  // out after the one before. Replies (and refetches) that land while saves are still pending
  // are dropped: they'd undo the newer edits. The last reply is the job.
  let pending = $state(0)
  let edits = 0
  let loadSeq = 0

  async function load() {
    const request = ++loadSeq
    const id = jobId
    const at = edits
    try {
      const fresh = await api.job(id)
      if (request !== loadSeq || id !== jobId || pending || at !== edits) return
      job = fresh
      error = ''
    } catch (e) {
      if (request === loadSeq && id === jobId) error = e instanceof Error ? e.message : String(e)
    }
  }

  $effect(() => {
    void jobId
    void app.versions[jobId]
    load()
  })

  let commandsSeq = 0
  $effect(() => {
    if ((tab === 'encoder' || tab === 'output') && job?.plan && !pending) {
      const seq = ++commandsSeq
      api.commands(jobId).then(c => seq === commandsSeq && (commands = c)).catch(() => seq === commandsSeq && (commands = []))
    }
  })

  function save(changes: SpecChanges): Promise<void> {
    if (job) {
      // A template or a container alone isn't a spec field: the reply brings what they changed.
      const { inputs, template: _t, container: _c, ...rest } = changes
      job = { ...job, spec: { ...job.spec, ...rest, inputs: { ...job.spec.inputs, ...inputs } } }
    }
    edits++
    pending++
    const id = jobId
    const snapshot = structuredClone($state.snapshot(changes))
    const send = saves.add(() => api.update(id, snapshot))
    return send.then(
      reply => {
        if (--pending === 0) job = reply
      },
      e => {
        toast.error("Couldn't save the change", { description: e instanceof Error ? e.message : String(e) })
        if (--pending === 0) load()
      },
    )
  }

  const editable = $derived(!!job && !['queued', 'running', 'indexing'].includes(job.status))
  const queued = $derived(job?.status === 'queued' || job?.status === 'running')

  async function setQueued(on: boolean) {
    try {
      await saves.flush()
      if (!on) await api.dequeue([jobId])
      else if (!(await api.enqueue([jobId])).enqueued.length) toast.warning("Couldn't queue the job", { description: 'It changed meanwhile: it is being probed or indexed, or is blocked.' })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
    load()
  }
  // The queue row's copy: progress events update it live (the detail reloads on job changes only).
  const live = $derived(app.jobs.find(j => j.id === jobId))
  const TABS: { id: Tab; label: string }[] = [
    { id: 'video', label: 'Video' },
    { id: 'encoder', label: 'Encoder' },
    { id: 'audio', label: 'Audio' },
    { id: 'subs', label: 'Subtitles' },
    { id: 'output', label: 'Output' },
    { id: 'log', label: 'Log' },
  ]
  const problems = $derived((job?.issues ?? []).filter(i => i.severity !== 'info'))
  const profile = $derived(app.profiles.find(p => p.id === job?.profile))
  const containers = $derived(profile?.containers ?? [])
  const container = $derived(containers.find(c => c.id === job?.spec.mux.container) ?? containers[0])
  const muxCommands = $derived(commands.filter(c => c.id === 'mux' || c.id === 'chapters.mp4'))
</script>

{#if !job}
  <div class="p-6 text-muted-foreground">{error || 'Loading…'}</div>
{:else}
  <Tabs.Root bind:value={tab} class="h-full min-h-0 gap-0">
    <header class="space-y-2 border-b px-5 pt-3">
      <div class="flex items-center gap-3">
        <label
          class="flex shrink-0 items-center gap-2 rounded-md border px-2.5 py-1 text-sm font-medium has-disabled:opacity-60
            {queued ? 'border-info/40 bg-info/10 text-info' : 'border-border'}"
          title={job.status === 'running'
            ? 'Running: locked until it finishes'
            : queued
              ? 'Queued: locked, and the queue runs it (a running queue too). Untick to edit it; the queue leaves it out.'
              : queueable(job.status)
                ? 'Tick when the job is set up: it locks, and the queue runs it'
                : `Can't be queued while ${STATUS_LABEL[job.status].toLowerCase()}`}
        >
          <Checkbox checked={queued} disabled={job.status === 'running' || (!queued && !queueable(job.status))} onCheckedChange={setQueued} />
          {queued ? 'Queued · locked' : 'Queue'}
        </label>
        <h2 class="truncate text-lg font-semibold" title={job.source}>{job.name}</h2>
        {#if job.label}<Badge variant="outline" class="shrink-0" title="Label (Output tab)">{job.label}</Badge>{/if}
        <span class="text-sm {STATUS_TONE[job.status]}">{STATUS_LABEL[job.status]}</span>
        <span class="text-sm text-muted-foreground">· {job.profile} · {job.encoder}{job.plan ? ` · ${job.plan.resolution}` : ''}</span>
        {#if job.status === 'indexing'}<Badge variant="outline" class="border-info/40 bg-info/10 text-info">locked while indexing</Badge>{/if}
        <TemplateMenu
          profile={job.profile}
          spec={job.spec}
          audioKeys={(job.tracks?.audio ?? []).filter(t => !t.external_path && !t.key.includes('+')).map(t => t.key)}
          disabled={!editable}
          apply={template => save({ template })}
        />
      </div>
      {#if live?.progress && (live.status === 'running' || live.status === 'indexing')}
        {@const p = live.progress}
        <div class="flex items-center gap-3 text-xs text-muted-foreground">
          <div class="h-1.5 flex-1 overflow-hidden rounded bg-muted">
            <div class="h-full bg-info transition-[width]" style="width:{p.overall * 100}%"></div>
          </div>
          <span class="tabular-nums">
            {#if app.queue.paused}<span class="text-warning">Paused ·</span>{/if}
            {p.step} · {(p.fraction * 100).toFixed(1)}%{p.eta != null ? ` (${duration(p.eta)} left)` : ''}
            {#if p.fps != null}· {p.fps < 10 ? p.fps.toFixed(2) : p.fps.toFixed(1)} fps{/if}
            {#if p.elapsed != null}· {duration(p.elapsed)} elapsed{/if}
            {#if p.left != null}<span title="A guess from the job's pace so far">· job ~{duration(p.left)} left</span>{/if}
          </span>
        </div>
      {/if}
      {#if problems.length}
        <button class="w-full text-left text-sm" onclick={() => (showInfo = !showInfo)}>
          {#each problems.slice(0, showInfo ? problems.length : 2) as i, n (n)}
            <div class={SEVERITY_TONE[i.severity]}>
              <TriangleAlertIcon class="mr-1 inline size-3.5 align-[-2px]" />{i.message}
              <span class="text-xs text-muted-foreground">{i.code}</span>
            </div>
          {/each}
          {#if !showInfo && problems.length > 2}<div class="text-xs text-muted-foreground">+{problems.length - 2} more…</div>{/if}
        </button>
      {/if}
      {#if (job.status === 'failed' || job.status === 'invalid') && tab !== 'log'}
        <Button variant="link" size="xs" class="h-auto p-0" onclick={() => (tab = 'log')}>Open the failed step in the Log tab</Button>
      {/if}
      {#if error}<div class="text-sm text-destructive">{error}</div>{/if}
      <Tabs.List variant="line" class="-mx-2 h-9">
        {#each TABS as t (t.id)}
          <Tabs.Trigger value={t.id} class="px-3">{t.label}</Tabs.Trigger>
        {/each}
      </Tabs.List>
    </header>

    <div class="min-h-0 flex-1 overflow-auto p-5">
      {#if tab === 'video'}
        {#if job.spec.inputs.encode}
          <p class="text-muted-foreground">This job reuses an existing encode ({basename(job.spec.inputs.encode)}); there is no video step.</p>
        {:else}
          {#key job.id}<VideoTab {job} {editable} save={video => save({ video })} />{/key}
        {/if}
      {:else if tab === 'encoder'}
        <div class="grid max-w-6xl gap-6 2xl:grid-cols-2">
          <div class="space-y-4">
            <EncoderPanel profile={job.profile} value={job.spec.encoder} disabled={!editable} colorArgs={job.color_args} hdr10plus={job.tracks ? !!job.tracks.video?.hdr?.hdr10plus : null} dv={job.tracks ? (job.tracks.video?.hdr ?? false) : null} budget={job.target} onchange={encoder => save({ encoder })} />
          </div>
          <div class="space-y-2">
            <span class="section-label">Commands this job runs</span>
            {#each commands as c (c.id)}
              <div class="rounded-lg border bg-muted/50 p-2">
                <div class="text-xs text-primary">{c.label}</div>
                <code class="block text-[11px] break-all text-muted-foreground">{c.command}</code>
              </div>
            {:else}
              <p class="text-sm text-muted-foreground">Available once the source is probed.</p>
            {/each}
          </div>
        </div>
      {:else if tab === 'audio' || tab === 'subs'}
        {@const kind = tab === 'audio' ? 'audio' : 'sub'}
        {#if app.profiles.find(p => p.id === job?.profile)?.track_editor}
          <TrackEditor {job} {editable} {kind} save={overrides => save({ overrides })} saveInputs={inputs => save({ inputs })} />
        {:else}
          <TracksTab {job} {editable} {kind} save={overrides => save({ overrides })} />
        {/if}
      {:else if tab === 'output'}
        <div class="max-w-3xl space-y-5">
          <div class="grid grid-cols-[8rem_minmax(0,1fr)] items-center gap-3 text-sm">
            <span class="text-muted-foreground">Output folder</span>
            <div
              class="-m-1 flex gap-2 rounded-lg p-1 outline-none"
              role="group"
              aria-label="Output folder (drop or paste a folder)"
              use:pathDrop={{
                rule: { mode: 'folder', label: 'Output folder' },
                accept: paths => save({ output_dir: paths[0] }),
                disabled: !editable,
              }}
            >
              <Input
                class="flex-1 font-mono text-xs"
                aria-label="Output folder"
                value={job.spec.output_dir ?? ''}
                disabled={!editable}
                onchange={e => save({ output_dir: pastedPaths((e.target as HTMLInputElement).value)[0] || null })}
              />
              <Button variant="outline" disabled={!editable} onclick={() => (browsing = 'output')}><FolderOpenIcon />Browse…</Button>
            </div>
            <span class="text-muted-foreground">Output name</span>
            <Input
              aria-label="Output name"
              placeholder="Default name"
              title="The output's file name, without its extension; empty = the profile's name for it (the source's). The label and the container's extension go after it"
              value={job.spec.output_name}
              disabled={!editable}
              onchange={e => save({ output_name: (e.target as HTMLInputElement).value.trim() })}
            />
            <label for="output-policy" class="text-muted-foreground">Existing output</label>
            <div class="space-y-1">
              <NativeSelect id="output-policy" disabled={!editable} value={job.spec.output_policy}
                onchange={e => save({ output_policy: e.currentTarget.value as JobDetail['spec']['output_policy'] })}>
                <option value="stop">Stop and keep the existing file</option>
                <option value="skip">Skip this job</option>
                <option value="rename">Use a new numbered filename</option>
                <option value="replace">Replace after validation</option>
              </NativeSelect>
              <p class="text-xs text-muted-foreground">Applies to files outside this job's verified results. An output changed during a run is always kept.</p>
            </div>
            <span class="text-muted-foreground">Label</span>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Input
                class="w-48"
                aria-label="Label"
                placeholder="e.g. dubbed"
                title="Tells runs of one source apart: added to the output name, and kept in the job record"
                value={job.spec.label}
                disabled={!editable}
                onchange={e => save({ label: (e.target as HTMLInputElement).value.trim() })}
              />
              {#if job.output_name}
                <span class="font-mono text-xs break-all text-muted-foreground" title="The file this job writes">{job.output_name}</span>
              {/if}
            </div>
            <span class="text-muted-foreground">Container</span>
            {#if containers.length > 1}
              <ToggleGroup.Root
                type="single"
                variant="outline"
                spacing={1}
                class="w-fit max-w-full flex-wrap"
                disabled={!editable}
                value={container?.id}
                onValueChange={v => v && save({ mux: { ...job!.spec.mux, container: v } })}
              >
                {#each containers as c (c.id)}
                  <ToggleGroup.Item value={c.id} class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{c.label}</ToggleGroup.Item>
                {/each}
              </ToggleGroup.Root>
            {:else}
              <span>{container?.label ?? job.spec.mux.container}</span>
            {/if}
            {#if container?.id === 'mkv'}
              <span class="text-muted-foreground">PGS compression</span>
              <label class="flex items-center gap-2">
                <Checkbox
                  checked={job.spec.mux.pgs_zlib ?? false}
                  disabled={!editable}
                  onCheckedChange={v => save({ mux: { ...job!.spec.mux, pgs_zlib: v } })}
                />
                Compress PGS subtitles with zlib
              </label>
            {/if}
            <span class="text-muted-foreground">Extra arguments</span>
            <Input
              class="font-mono text-xs"
              aria-label="Extra muxer arguments"
              placeholder="added to the {container?.tool ?? 'muxer'} command as typed"
              value={job.spec.mux.extra}
              disabled={!editable}
              onchange={e => save({ mux: { ...job!.spec.mux, extra: (e.target as HTMLInputElement).value.trim() } })}
            />
            <span class="text-muted-foreground">Chapters</span>
            <div
              class="-m-1 flex flex-wrap items-center gap-2 rounded-lg p-1 outline-none"
              role="group"
              aria-label="Chapters (drop or paste a file)"
              use:pathDrop={{
                rule: { mode: 'file', extensions: ['.xml', '.txt'], label: 'Chapters' },
                accept: paths => save({ inputs: { chapters: paths[0] } }),
                disabled: !editable,
              }}
            >
              <span>
                {job.spec.inputs.chapters
                  ? basename(job.spec.inputs.chapters)
                  : job.plan?.chapters_path
                    ? `${basename(job.plan.chapters_path)} (AutoQPF)`
                    : job.tracks?.has_chapters
                      ? 'From the source'
                      : 'None'}
              </span>
              <Button variant="ghost" size="sm" disabled={!editable} onclick={() => (browsing = 'chapters')}>
                {job.spec.inputs.chapters ? 'Change…' : 'Use a file…'}
              </Button>
              {#if job.spec.inputs.chapters}
                <Button variant="ghost" size="sm" class="hover:text-destructive" disabled={!editable} onclick={() => save({ inputs: { chapters: null } })}
                  >Remove</Button
                >
              {/if}
            </div>
            <span></span>
            <label class="flex items-center gap-2">
              <Checkbox checked={job.spec.qpf} disabled={!editable} onCheckedChange={v => save({ qpf: v })} />
              AutoQPF: chapters from the source (or every 5%) and keyframes on them
            </label>
            <span class="text-muted-foreground">Profile</span>
            <NativeSelect class="w-48" value={job.profile} disabled={!editable} onchange={e => save({ profile: e.currentTarget.value })}>
              {#each app.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
            </NativeSelect>
            <span class="text-muted-foreground">Work folder</span>
            <code class="text-xs break-all text-muted-foreground">{job.source}_tmp</code>
            <span class="text-muted-foreground">Output</span>
            <code class="text-xs break-all text-muted-foreground">{job.output ?? '(after the run)'}</code>
          </div>
          {#if muxCommands.length}
            <div class="space-y-2">
              <span class="section-label">Mux command</span>
              {#each muxCommands as c (c.id)}
                <div class="rounded-lg border bg-muted/50 p-2">
                  <div class="text-xs text-primary">{c.label}</div>
                  <code class="block text-[11px] break-all text-muted-foreground">{c.command}</code>
                </div>
              {/each}
            </div>
          {/if}
          {#if Object.keys(job.steps).length}
            <div>
              <span class="section-label">Finished steps (reused on the next run if nothing they depend on changed)</span>
              <ul class="mt-2 space-y-1 text-sm">
                {#each Object.values(job.steps) as s (s.id)}
                  <li class="flex gap-3"><CheckIcon class="size-4 text-success" /><span class="w-28">{s.id}</span><span class="text-muted-foreground">{s.seconds}s</span></li>
                {/each}
              </ul>
            </div>
          {/if}
        </div>
      {:else}
        <JobLog {jobId} running={job.status === 'running'} />
      {/if}
    </div>
  </Tabs.Root>
{/if}

{#if browsing === 'output' && job}
  <FileBrowser
    title="Output folder"
    mode="folder"
    start={job.spec.output_dir ?? ''}
    onpick={paths => {
      browsing = null
      if (paths[0]) save({ output_dir: paths[0] })
    }}
    onclose={() => (browsing = null)}
  />
{:else if browsing === 'chapters' && job}
  <FileBrowser
    title="Chapters file"
    extensions={['.xml', '.txt']}
    start={job.spec.inputs.source.replace(/[\\/][^\\/]*$/, '')}
    onpick={paths => {
      browsing = null
      if (paths[0]) save({ inputs: { chapters: paths[0] } })
    }}
    onclose={() => (browsing = null)}
  />
{/if}
