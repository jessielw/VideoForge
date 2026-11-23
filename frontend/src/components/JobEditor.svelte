<script lang="ts">
  // One job, StaxRip-style: Video | Encoder | Audio | Subtitles | Output | Log, and Issues when it has any (the header
  // counts them).
  // Changes save straight away (the server replans); a queued, running or indexing job is read-only.
  // Queue (top left, and the tick on its queue row) locks the job for the run: the queue runs it.
  import { api, type SpecChanges } from '../lib/api'
  import { reuseQuestion } from '../lib/reuse.svelte'
  import { saves } from '../lib/saves'
  import { basename, bytes, duration, percent, sizeLabel, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { queueable } from '../lib/queueView'
  import { app } from '../lib/state.svelte'
  import { layout } from '../lib/layout.svelte'
  import { openSettings } from '../lib/settingsLink'
  import type { CommandStep, JobDetail } from '../lib/types'
  import Advanced from './Advanced.svelte'
  import EncoderPanel from './EncoderPanel.svelte'
  import IssueCounts from './IssueCounts.svelte'
  import OutputFolderMenu from './OutputFolderMenu.svelte'
  import NameSettings from './NameSettings.svelte'
  import SampleCard from './SampleCard.svelte'
  import CrfSearchCard from './CrfSearchCard.svelte'
  import { videoView } from '../lib/videoView.svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
  import CircleXIcon from '@lucide/svelte/icons/circle-x'
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import InfoIcon from '@lucide/svelte/icons/info'
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
  import Tip from './Tip.svelte'
  import FileBrowser from './FileBrowser.svelte'
  import { pastedPaths, pathDrop } from '../lib/dropPaths.svelte'
  import TrackEditor from './TrackEditor.svelte'
  import TracksTab from './TracksTab.svelte'
  import JobLog from './JobLog.svelte'
  import MediaInfoDialog from './MediaInfoDialog.svelte'
  import VideoTab from './VideoTab.svelte'

  let { jobId }: { jobId: string } = $props()

  type Tab = 'video' | 'encoder' | 'audio' | 'subs' | 'output' | 'log' | 'issues'
  let tab = $state<Tab>('video')
  let job = $state<JobDetail | null>(null)
  let error = $state('')
  let commands = $state<CommandStep[]>([])
  let browsing = $state<'output' | 'chapters' | null>(null)
  let mediainfo = $state(false)

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
      // A phone is for checking on runs: a job that has one opens on its log, not the video.
      if (!job && layout.small && ['running', 'failed', 'invalid', 'done'].includes(fresh.status)) tab = 'log'
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

  // A phone scrolls the tab strip: keep the open tab in sight (a run opens on Log, the last one).
  let tabList = $state<HTMLElement | null>(null)
  $effect(() => {
    void tab
    tabList?.querySelector('[data-state="active"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  })

  let commandsSeq = 0
  $effect(() => {
    if ((tab === 'encoder' || tab === 'output') && job?.plan && !pending) {
      const seq = ++commandsSeq
      api
        .commands(jobId)
        .then((c) => seq === commandsSeq && (commands = c))
        .catch(() => seq === commandsSeq && (commands = []))
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
      (reply) => {
        if (--pending === 0) job = reply
      },
      (e) => {
        toast.error("Couldn't save the change", { description: e instanceof Error ? e.message : String(e) })
        if (--pending === 0) load()
      },
    )
  }

  const editable = $derived(!!job && !['queued', 'running', 'indexing', 'sampling'].includes(job.status))
  const queued = $derived(job?.status === 'queued' || job?.status === 'running')

  async function setQueued(on: boolean) {
    try {
      await saves.flush()
      // A running queue takes it at once: ask about an earlier run's files first (null: cancelled).
      const reuse = on ? await reuseQuestion.ask([jobId], 'queue') : {}
      if (!on) await api.dequeue([jobId])
      else if (reuse && !(await api.enqueue([jobId], reuse)).enqueued.length)
        toast.warning("Couldn't queue the job", {
          description:
            "It changed in the meantime. A job can't be queued while VideoForge reads its tracks, indexes it, crops it or runs a test encode or CRF search, or while it's blocked.",
        })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
    load()
  }
  // The queue row's copy: progress events update it live (the detail reloads on job changes only).
  const live = $derived(app.jobs.find((j) => j.id === jobId))
  const TABS: { id: Tab; label: string }[] = [
    { id: 'video', label: 'Video' },
    { id: 'encoder', label: 'Encoder' },
    { id: 'audio', label: 'Audio' },
    { id: 'subs', label: 'Subtitles' },
    { id: 'output', label: 'Output' },
    { id: 'log', label: 'Log' },
  ]
  const problems = $derived((job?.issues ?? []).filter((i) => i.severity !== 'info'))
  const counts = $derived({
    block: problems.filter((i) => i.severity === 'block').length,
    warn: problems.filter((i) => i.severity === 'warn').length,
  })
  // There while the job has errors or warnings, and while it's open: the last one going leaves it saying so.
  const issuesTab = $derived(problems.length > 0 || tab === 'issues')
  // The server's messages end without a period (its issue code used to follow them)
  const sentence = (message: string) => (/[.!?]$/.test(message) ? message : `${message}.`)
  const ruleSet = $derived(app.ruleSets.find((p) => p.id === job?.rule_set))
  const containers = $derived(ruleSet?.containers ?? [])
  const container = $derived(containers.find((c) => c.id === job?.spec.mux.container) ?? containers[0])
  const muxCommands = $derived(commands.filter((c) => c.id === 'mux' || c.id === 'chapters.mp4'))
</script>

{#if !job}
  <div class="p-6 text-muted-foreground">{error || 'Loading…'}</div>
{:else}
  <Tabs.Root bind:value={tab} class="h-full min-h-0 gap-0">
    <!-- A narrow header (a phone, or 200% zoom) gives the job's name a line of its own. -->
    <header class="@container/job-header space-y-2 border-b px-5 pt-3 max-sm:px-3">
      <div
        class="flex items-center gap-3 @max-[44rem]/job-header:flex-wrap @max-[44rem]/job-header:gap-x-2 @max-[44rem]/job-header:gap-y-1"
      >
        <Tip
          class="shrink-0"
          text={job.status === 'running'
            ? 'Running. You can edit it again when it finishes.'
            : queued
              ? "Queued, so it can't be edited. Start queue runs it, or a running queue picks it up in its turn. Untick it to make changes, and the queue skips it."
              : queueable(job.status)
                ? "Tick it when the job is set up, to queue it. Start queue runs it, or a running queue picks it up in its turn. You can't edit it until you untick it."
                : `Can't be queued while its status is ${STATUS_LABEL[job.status]}`}
        >
          <label
            class="flex items-center gap-2 rounded-md border px-2.5 py-1 text-sm font-medium has-disabled:opacity-60
              {queued ? 'border-info/40 bg-info/10 text-info' : 'border-border'}"
          >
            <Checkbox
              bind:checked={() => queued, setQueued}
              disabled={job.status === 'running' || (!queued && !queueable(job.status))}
            />
            {queued ? 'Queued · locked' : 'Queue'}
          </label>
        </Tip>
        <Tip class="min-w-0 @max-[44rem]/job-header:order-first @max-[44rem]/job-header:basis-full" text={job.source}>
          <h2 class="truncate text-lg font-semibold">{job.name}</h2>
        </Tip>
        {#if job.label}<Tip class="shrink-0" text="Label (Output tab)"><Badge variant="outline">{job.label}</Badge></Tip
          >{/if}
        <span class="text-sm {STATUS_TONE[job.status]}">{STATUS_LABEL[job.status]}</span>
        {#if job.status === 'indexing' || job.status === 'sampling'}<Badge
            variant="outline"
            class="border-info/40 bg-info/10 text-info"
            >locked {job.status === 'indexing' ? 'while indexing' : 'during its test encode'}</Badge
          >{/if}
        <TemplateMenu
          ruleSet={job.rule_set}
          spec={job.spec}
          audioKeys={(job.tracks?.audio ?? [])
            .filter((t) => !t.external_path && !t.key.includes('+'))
            .map((t) => t.key)}
          disabled={!editable}
          apply={(template) => save({ template })}
        />
        <Tip class="shrink-0" text="MediaInfo of the source and the job's other files">
          <Button variant="outline" size="sm" onclick={() => (mediainfo = true)}><InfoIcon />MediaInfo</Button>
        </Tip>
      </div>
      <!-- The job's facts under its name, so the name keeps the title row; then what a finished run made.
           One box per figure: a narrow window breaks the line between figures, never inside one. -->
      <div class="readout flex flex-wrap gap-x-1 text-xs text-muted-foreground *:whitespace-nowrap">
        <span>{app.ruleSets.find((r) => r.id === job!.rule_set)?.name ?? job.rule_set}</span>
        <span>· {job.encoder}</span>
        {#if job.plan}<span>· {sizeLabel(job.plan.resolution)}</span>{/if}
        {#if job.made && (job.status === 'done' || job.status === 'invalid')}
          {@const m = job.made}
          <span>· Made {bytes(m.output_bytes)}</span>
          {#if m.source_bytes}<span
              >· <Tip text="The source is {bytes(m.source_bytes)}"
                >{percent(m.output_bytes / m.source_bytes)} of the source</Tip
              ></span
            >{/if}
          {#if m.kbps != null}<span>· {m.kbps.toLocaleString()} kb/s</span>{/if}
          <span
            >· took {duration(m.seconds)}{#if m.reused}{' '}<Tip text="Steps taken from an earlier run, not made again"
                >({m.reused} reused)</Tip
              >{/if}</span
          >
        {/if}
      </div>
      {#if live?.progress && ['running', 'indexing', 'sampling'].includes(live.status)}
        {@const p = live.progress}
        <div class="flex items-center gap-3 text-xs text-muted-foreground max-sm:flex-wrap max-sm:gap-y-1">
          <div class="h-1.5 flex-1 overflow-hidden rounded bg-muted max-sm:basis-full">
            <div class="h-full bg-info transition-[width]" style="width:{p.overall * 100}%"></div>
          </div>
          <span class="readout">
            {#if app.queue.paused}<span class="text-info">Paused ·</span>{/if}
            {p.step} · {(p.fraction * 100).toFixed(1)}%{p.eta != null ? ` (${duration(p.eta)} left)` : ''}
            <Tip text="The bar and this number show the whole job. Each step counts for a set share of it."
              >· job {percent(p.overall)}</Tip
            >
            {#if p.fps != null}· {p.fps < 10 ? p.fps.toFixed(2) : p.fps.toFixed(1)} fps{/if}
            {#if p.elapsed != null}· {duration(p.elapsed)} elapsed{/if}
            {#if p.left != null}<Tip text="A guess from the job's pace so far">· job ~{duration(p.left)} left</Tip>{/if}
          </span>
        </div>
      {/if}
      {#if problems.length}
        <!-- the counts only: the Issues tab lists them, with their codes -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span><IssueCounts {counts} /></span>
          {#if tab !== 'issues'}
            <Button variant="link" size="xs" class="h-auto p-0" onclick={() => (tab = 'issues')}
              >Open the Issues tab</Button
            >
          {/if}
        </div>
      {/if}
      {#if (job.status === 'failed' || job.status === 'invalid') && tab !== 'log'}
        <Button variant="link" size="xs" class="h-auto p-0" onclick={() => (tab = 'log')}
          >Open the failed step in the Log tab</Button
        >
      {/if}
      {#if error}<div class="text-sm text-destructive">{error}</div>{/if}
      <Tabs.List
        bind:ref={tabList}
        variant="line"
        aria-label="Job sections"
        class="-mx-2 h-9 max-sm:max-w-[calc(100%+1rem)] max-sm:justify-start max-sm:overflow-x-auto max-sm:[scrollbar-width:none]"
      >
        {#each TABS as t (t.id)}
          <Tabs.Trigger value={t.id} id="job-tab-{t.id}" aria-controls="job-tab-panel" class="px-3"
            >{t.label}</Tabs.Trigger
          >
        {/each}
        {#if issuesTab}
          <!-- tinted in its worst issue's color, so it stands out (! beats the line tabs' own background and border);
               the words keep the text color: yellow on the yellow tint is too faint -->

          <Tabs.Trigger
            value="issues"
            id="job-tab-issues"
            aria-controls="job-tab-panel"
            class="px-3 {counts.block
              ? 'border-destructive/40! bg-destructive/10! text-foreground'
              : counts.warn
                ? 'border-warning/40! bg-warning/10! text-foreground'
                : ''}"
          >
            {#if counts.block}<CircleXIcon
                aria-hidden="true"
                class="text-destructive"
              />{:else if counts.warn}<TriangleAlertIcon aria-hidden="true" class="text-warning" />{/if}Issues
            {#if problems.length}<span class="readout">{problems.length}</span>{/if}
          </Tabs.Trigger>
        {/if}
      </Tabs.List>
    </header>

    <!-- One panel for every tab (the tabs swap what's in it), named by the tab that shows. -->
    <div
      id="job-tab-panel"
      role="tabpanel"
      aria-labelledby="job-tab-{tab}"
      class="@container/job-tab min-h-0 flex-1 overflow-auto p-5 max-sm:p-3"
    >
      {#if tab === 'video'}
        {#if job.spec.inputs.encode}
          <p class="text-muted-foreground">
            This job uses an existing encode ({basename(job.spec.inputs.encode)}), so VideoForge doesn't encode the
            video and there's nothing to set here.
          </p>
        {:else}
          {#key job.id}<VideoTab {job} {editable} save={(video) => save({ video })} />{/key}
        {/if}
      {:else if tab === 'encoder'}
        <div class="grid max-w-6xl gap-6 2xl:grid-cols-2">
          <div class="space-y-4">
            <EncoderPanel
              ruleSet={job.rule_set}
              value={job.spec.encoder}
              disabled={!editable}
              colorArgs={job.color_args}
              hdr10plus={job.tracks ? !!job.tracks.video?.hdr?.hdr10plus : null}
              dv={job.tracks ? (job.tracks.video?.hdr ?? false) : null}
              budget={job.target}
              onchange={(encoder) => save({ encoder })}
            />
          </div>
          <div class="space-y-4">
            {#if !job.spec.inputs.encode}
              <SampleCard
                {job}
                {editable}
                oncompare={() => {
                  const v = videoView(jobId)
                  Object.assign(v, { compare: 'sample', shows: 'out', panel: 'settings' })
                  tab = 'video'
                }}
              />
              <CrfSearchCard
                {job}
                {editable}
                onapply={(crf) => job && save({ encoder: { ...job.spec.encoder, crf } })}
              />
            {/if}
            <div class="space-y-2">
              <span class="section-label">Commands this job runs</span>
              {#each commands as c (c.id)}
                <div class="rounded-lg border bg-muted/50 p-2">
                  <div class="text-xs font-medium text-foreground">{c.label}</div>
                  <code class="block text-xs break-all text-muted-foreground">{c.command}</code>
                </div>
              {:else}
                <p class="text-sm text-muted-foreground">Available once the source is probed.</p>
              {/each}
            </div>
          </div>
        </div>
      {:else if tab === 'audio' || tab === 'subs'}
        {@const kind = tab === 'audio' ? 'audio' : 'sub'}
        {#if app.ruleSets.find((p) => p.id === job?.rule_set)?.track_editor}
          <TrackEditor
            {job}
            {editable}
            {kind}
            save={(overrides) => save({ overrides })}
            saveInputs={(inputs) => save({ inputs })}
          />
        {:else}
          <TracksTab {job} {editable} {kind} save={(overrides) => save({ overrides })} />
        {/if}
      {:else if tab === 'output'}
        <div class="max-w-3xl space-y-5">
          <div class="grid grid-cols-[8rem_minmax(0,1fr)] items-baseline gap-3 text-sm">
            <span class="text-muted-foreground">Output folder</span>
            <div
              class="-m-1 flex gap-2 rounded-lg p-1 outline-none"
              role="group"
              aria-label="Output folder (drop or paste a folder)"
              use:pathDrop={{
                rule: { mode: 'folder', label: 'Output folder' },
                accept: (paths) => save({ output_dir: paths[0] }),
                disabled: !editable,
              }}
            >
              <Input
                class="flex-1 font-mono text-xs"
                aria-label="Output folder"
                value={job.spec.output_dir ?? ''}
                disabled={!editable}
                onchange={(e) => save({ output_dir: pastedPaths((e.target as HTMLInputElement).value)[0] || null })}
              />
              <Button variant="outline" disabled={!editable} onclick={() => (browsing = 'output')}
                ><FolderOpenIcon />Browse…</Button
              >
              <OutputFolderMenu disabled={!editable} onpick={(path) => save({ output_dir: path })} />
            </div>
            <span class="text-muted-foreground">Output name</span>
            <Tip
              class="grid"
              text="The output's file name, without its extension. Leave it empty to use the name template when it names the file, or else the rule set's name, which is normally the source's. The label, the name suffix and the extension go after it, as in Show.S01E01.dubbed.mkv."
            >
              <Input
                aria-label="Output name"
                placeholder="Default name"
                value={job.spec.output_name}
                disabled={!editable}
                onchange={(e) => save({ output_name: (e.target as HTMLInputElement).value.trim() })}
              />
            </Tip>
            <label for="output-policy" class="text-muted-foreground">Existing output</label>
            <div class="space-y-1">
              <NativeSelect
                id="output-policy"
                disabled={!editable}
                value={job.spec.output_policy}
                onchange={(e) => save({ output_policy: e.currentTarget.value as JobDetail['spec']['output_policy'] })}
              >
                <option value="stop">Stop and keep the existing file</option>
                <option value="skip">Skip this job</option>
                <option value="rename">Use a new numbered filename</option>
                <option value="replace">Replace after validation</option>
              </NativeSelect>
              <p class="text-xs text-muted-foreground">
                This applies when the output file already exists and this job didn't make it. If a file appears or
                changes there while the job runs, it isn't replaced. The job fails and keeps its new output beside it as
                an .unpublished copy.
              </p>
            </div>
            <span class="text-muted-foreground">Label</span>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Tip
                text="Tells jobs from the same source apart. It's added to the output name and saved in the job record."
              >
                <Input
                  class="w-48"
                  aria-label="Label"
                  placeholder="e.g. dubbed"
                  value={job.spec.label}
                  disabled={!editable}
                  onchange={(e) => save({ label: (e.target as HTMLInputElement).value.trim() })}
                />
              </Tip>
              {#if job.output_name}
                <Tip class="block font-mono text-xs break-all text-muted-foreground" text="The file this job writes"
                  >{job.output_name}</Tip
                >
              {/if}
            </div>
            <NameSettings
              mux={job.spec.mux}
              mkv={container?.id === 'mkv'}
              disabled={!editable}
              title={job.output_title}
              ruleSetName={app.ruleSets.find((r) => r.id === job?.rule_set)?.name}
              onchange={(mux) => save({ mux })}
            />
            <span class="text-muted-foreground">Container</span>
            {#if containers.length > 1}
              <ToggleGroup.Root
                type="single"
                variant="outline"
                spacing={1}
                class="w-fit max-w-full flex-wrap"
                disabled={!editable}
                value={container?.id}
                onValueChange={(v) => v && save({ mux: { ...job!.spec.mux, container: v } })}
              >
                {#each containers as c (c.id)}
                  <ToggleGroup.Item
                    value={c.id}
                    class="px-4 data-[state=on]:border-primary data-[state=on]:bg-primary/15 data-[state=on]:text-foreground"
                    >{c.label}</ToggleGroup.Item
                  >
                {/each}
              </ToggleGroup.Root>
            {:else}
              <span>{container?.label ?? job.spec.mux.container}</span>
            {/if}
            <span class="text-muted-foreground">Chapters</span>
            <div
              class="-m-1 flex flex-wrap items-center gap-2 rounded-lg p-1 outline-none"
              role="group"
              aria-label="Chapters (drop or paste a file)"
              use:pathDrop={{
                rule: { mode: 'file', extensions: ['.xml', '.txt'], label: 'Chapters' },
                accept: (paths) => save({ inputs: { chapters: paths[0] } }),
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
                <Button
                  variant="ghost"
                  size="sm"
                  class="hover:text-destructive"
                  disabled={!editable}
                  onclick={() => save({ inputs: { chapters: null } })}>Remove</Button
                >
              {/if}
            </div>
            <span></span>
            <label class="flex items-center gap-2">
              <Checkbox checked={job.spec.qpf} disabled={!editable} onCheckedChange={(v) => save({ qpf: v })} />
              AutoQPF: chapters from the source (or every 5%) and keyframes on them
            </label>
            {#if app.ruleSets.length > 1}
              <!-- with one rule set installed there's nothing to choose; the header's facts line names it -->
              <span class="text-muted-foreground">Rule set</span>
              <NativeSelect
                class="w-48"
                aria-label="Rule set"
                value={job.rule_set}
                disabled={!editable}
                onchange={(e) => save({ rule_set: e.currentTarget.value })}
              >
                {#each app.ruleSets as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
              </NativeSelect>
            {/if}
            <span class="text-muted-foreground">Output</span>
            <code class="text-xs break-all text-muted-foreground">{job.output ?? '(after the run)'}</code>
          </div>
          <!-- counts the extra arguments and PGS compression, which are off by default -->
          <Advanced
            area="output"
            title="Advanced"
            count={(job.spec.mux.extra ? 1 : 0) + (container?.id === 'mkv' && job.spec.mux.pgs_zlib ? 1 : 0)}
          >
            <div class="grid grid-cols-[8rem_minmax(0,1fr)] items-baseline gap-3 text-sm">
              {#if container?.id === 'mkv'}
                <!-- self-start: the row starts with a checkbox, whose baseline moves with its tick; its first line is at the top -->
                <span class="self-start text-muted-foreground">PGS compression</span>
                <label class="flex items-center gap-2">
                  <Checkbox
                    checked={job.spec.mux.pgs_zlib ?? false}
                    disabled={!editable}
                    onCheckedChange={(v) => save({ mux: { ...job!.spec.mux, pgs_zlib: v } })}
                  />
                  Compress PGS subtitles with zlib
                </label>
              {/if}
              <span class="text-muted-foreground">Extra arguments</span>
              <Input
                class="font-mono text-xs placeholder:font-sans"
                aria-label="Extra arguments for {container?.tool ?? 'the output'}"
                placeholder="added to the {container?.tool ?? 'output'} command as typed"
                value={job.spec.mux.extra}
                disabled={!editable}
                onchange={(e) =>
                  save({ mux: { ...job!.spec.mux, extra: (e.target as HTMLInputElement).value.trim() } })}
              />
              <span class="text-muted-foreground">Work folder</span>
              <code class="text-xs break-all text-muted-foreground">{job.source}_tmp</code>
            </div>
            {#if muxCommands.length}
              <div class="space-y-2">
                <span class="section-label">Commands that build the output file</span>
                {#each muxCommands as c (c.id)}
                  <div class="rounded-lg border bg-muted/50 p-2">
                    <div class="text-xs font-medium text-foreground">{c.label}</div>
                    <code class="block text-xs break-all text-muted-foreground">{c.command}</code>
                  </div>
                {/each}
              </div>
            {/if}
            {#if Object.keys(job.steps).length}
              <div>
                <span class="section-label"
                  >Finished steps (reused on the next run if nothing they depend on changed)</span
                >
                <ul class="mt-2 space-y-1 text-sm">
                  {#each Object.values(job.steps) as s (s.id)}
                    <li class="flex gap-3">
                      <CheckIcon class="size-4 text-success" /><span class="w-28">{s.id}</span><span
                        class="text-muted-foreground">{s.seconds}s</span
                      >
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}
          </Advanced>
        </div>
      {:else if tab === 'issues'}
        <div class="max-w-3xl space-y-5">
          {#each [['block', 'Errors', 'Error:'], ['warn', 'Warnings', 'Warning:']] as const as [severity, heading, spoken] (severity)}
            {@const list = problems.filter((i) => i.severity === severity)}
            {#if list.length}
              <section class="space-y-2">
                <h3 class="section-label">{heading}</h3>
                <ul class="space-y-2 text-sm">
                  {#each list as i, n (n)}
                    <!-- the tab where it's fixed, from the server's table; Settings › Tools is a page of its own -->
                    {@const goes = TABS.find((t) => t.id === i.tab)}
                    <li class="flex gap-2">
                      {#if severity === 'block'}<CircleXIcon
                          aria-hidden="true"
                          class="mt-0.5 size-4 shrink-0 text-destructive"
                        />{:else}<TriangleAlertIcon
                          aria-hidden="true"
                          class="mt-0.5 size-4 shrink-0 text-warning"
                        />{/if}
                      <span class="min-w-0"
                        ><span class="sr-only">{`${spoken} `}</span><span>{sentence(i.message)}</span
                        >{' '}{#if goes}<Button
                            variant="link"
                            size="xs"
                            class="h-auto p-0"
                            onclick={() => (tab = goes.id)}>Go to the {goes.label} tab</Button
                          >{' '}{:else if i.tab === 'tools'}<Button
                            variant="link"
                            size="xs"
                            class="h-auto p-0"
                            onclick={() => openSettings('tools')}>Go to Settings › Tools</Button
                          >{' '}{/if}<code class="font-mono text-xs break-all text-muted-foreground">{i.code}</code
                        ></span
                      >
                    </li>
                  {/each}
                </ul>
              </section>
            {/if}
          {/each}
          {#if !problems.length}<p class="text-sm text-muted-foreground">No issues left.</p>{/if}
        </div>
      {:else}
        <JobLog {jobId} running={job.status === 'running'} />
      {/if}
    </div>
  </Tabs.Root>
{/if}

{#if job}<MediaInfoDialog bind:open={mediainfo} {job} />{/if}

{#if browsing === 'output' && job}
  <FileBrowser
    title="Output folder"
    mode="folder"
    start={job.spec.output_dir ?? ''}
    onpick={(paths) => {
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
    onpick={(paths) => {
      browsing = null
      if (paths[0]) save({ inputs: { chapters: paths[0] } })
    }}
    onclose={() => (browsing = null)}
  />
{/if}
