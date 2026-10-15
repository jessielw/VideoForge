<script lang="ts">
  // The queue: jobs on the left (click, Ctrl/Shift-click to select several), the selected
  // job's editor on the right, or a batch panel when several are selected.
  import EncoderPanel from '../components/EncoderPanel.svelte'
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import CropIcon from '@lucide/svelte/icons/crop'
  import LayoutTemplateIcon from '@lucide/svelte/icons/layout-template'
  import PanelLeftCloseIcon from '@lucide/svelte/icons/panel-left-close'
  import PanelLeftOpenIcon from '@lucide/svelte/icons/panel-left-open'
  import PauseIcon from '@lucide/svelte/icons/pause'
  import PlayIcon from '@lucide/svelte/icons/play'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import SquareIcon from '@lucide/svelte/icons/square'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import * as Card from '$lib/components/ui/card'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import JobEditor from '../components/JobEditor.svelte'
  import { api } from '../lib/api'
  import { percent, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { layout } from '../lib/layout.svelte'
  import { app } from '../lib/state.svelte'
  import type { EncoderSettings, JobDetail } from '../lib/types'

  let selected = $state<string[]>([])
  let anchor = $state<string | null>(null)

  // The routed job is selected once it's in the list (the prune below would undo it otherwise).
  $effect(() => {
    const id = router.jobId
    if (id && !selected.includes(id) && app.jobs.some(j => j.id === id)) selected = [id]
  })

  // Forget jobs that are gone.
  $effect(() => {
    const ids = new Set(app.jobs.map(j => j.id))
    if (selected.some(id => !ids.has(id))) selected = selected.filter(id => ids.has(id))
  })

  function click(e: MouseEvent, id: string) {
    if (e.shiftKey && anchor) {
      const ids = app.jobs.map(j => j.id)
      const [a, b] = [ids.indexOf(anchor), ids.indexOf(id)].sort((x, y) => x - y)
      selected = ids.slice(a, b + 1)
    } else if (e.ctrlKey || e.metaKey) {
      selected = selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]
      anchor = id
    } else {
      selected = [id]
      anchor = id
    }
    router.go('queue', selected.length === 1 ? selected[0] : null)
  }

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }

  async function move(step: number) {
    const ids = app.jobs.map(j => j.id)
    const sel = new Set(selected)
    const order = step < 0 ? ids : [...ids].reverse()
    for (let i = 1; i < order.length; i++) {
      if (sel.has(order[i]) && !sel.has(order[i - 1])) [order[i - 1], order[i]] = [order[i], order[i - 1]]
    }
    await act(() => api.reorder(step < 0 ? order : order.reverse()))
  }

  async function remove() {
    await act(async () => {
      const r = await api.remove(selected)
      if (r.removed.length < selected.length) toast.info('Queued or running jobs were kept')
      selected = []
      router.go('queue')
    })
  }

  const single = $derived(selected.length === 1 ? selected[0] : null)
  const runnable = $derived(app.jobs.some(j => ['ready', 'warn', 'queued'].includes(j.status)))

  // --- batch panel ---
  let batchSource = $state<JobDetail | null>(null)
  $effect(() => {
    if (selected.length > 1) api.job(selected[0]).then(j => (batchSource = j))
    else batchSource = null
  })

  async function applyEncoder(encoder: EncoderSettings) {
    if (!batchSource) return
    batchSource.spec.encoder = encoder
    await act(async () => {
      const r = await api.apply(selected, { encoder })
      toast.success(`Encoder applied to ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
    })
  }

  // A template (by name) for the whole batch, from the first job's profile's choices.
  let batchTemplate = $state('')
  const batchTemplates = $derived(batchSource ? app.presetChoices('template', batchSource.profile) : [])
  const picked = $derived(batchTemplates.find(c => c.name === batchTemplate) ?? batchTemplates[0])
  const batchContainers = $derived(app.profiles.find(p => p.id === batchSource?.profile)?.containers ?? [])

  async function applyTemplate() {
    if (!picked) return
    const name = picked.name
    await act(async () => {
      const r = await api.apply(selected, { template: $state.snapshot(picked.data) })
      toast.success(`Template ${name} applied to ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
      batchSource = await api.job(selected[0])
    })
  }

  async function applyContainer(container: string) {
    if (!batchSource) return
    batchSource.spec.mux.container = container
    await act(async () => {
      const r = await api.apply(selected, { container })
      const label = batchContainers.find(c => c.id === container)?.label ?? container
      toast.success(`${label} for ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : ''))
    })
  }

  async function applyCrop() {
    if (!batchSource) return
    const crop = batchSource.spec.video.crop
    await act(async () => {
      const jobs = await Promise.all(selected.map(id => api.job(id)))
      for (const j of jobs) if (j.spec.inputs.encode === null) await api.update(j.id, { video: { ...j.spec.video, crop } })
      toast.success(`Crop ${crop.left}/${crop.top}/${crop.right}/${crop.bottom} applied to ${jobs.length} job(s)`)
    })
  }
</script>

<div class="flex h-full">
  {#if layout.queueCollapsed}
    <!-- The list as a rail: one chip per job (its place, coloured by status). -->
    <section class="flex w-14 shrink-0 flex-col items-center border-r border-border">
      <Button variant="ghost" size="icon" class="my-2" onclick={() => (layout.queueCollapsed = false)} title="Show the queue list">
        <PanelLeftOpenIcon />
      </Button>
      <div class="flex min-h-0 w-full flex-1 flex-col items-center gap-1 overflow-auto border-t border-border py-2">
        {#each app.jobs as job, i (job.id)}
          <button
            class="relative flex h-9 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border text-xs
              {selected.includes(job.id) ? 'border-primary bg-primary/15' : 'hover:bg-accent'}
              {STATUS_TONE[job.status]}"
            onclick={e => click(e, job.id)}
            title="{job.name}: {STATUS_LABEL[job.status]}{job.issue ? ` (${job.issue})` : ''}"
          >
            {i + 1}
            {#if job.status === 'running' && job.progress}
              <span class="absolute inset-x-0 bottom-0 h-1 bg-muted">
                <span class="block h-full bg-info" style="width:{job.progress.overall * 100}%"></span>
              </span>
            {/if}
          </button>
        {/each}
      </div>
    </section>
  {:else}
  <section class="flex w-[28rem] shrink-0 flex-col border-r border-border">
    <div class="flex flex-wrap items-center gap-1 border-b border-border p-2">
      <Button variant="ghost" size="icon" onclick={() => (layout.queueCollapsed = true)} title="Collapse the list, for more room">
        <PanelLeftCloseIcon />
      </Button>
      {#if app.queue.running}
        <Button variant="outline" onclick={() => act(api.stop)} title="Finish the current job, then stop">
          <PauseIcon />{app.queue.stop_after_current ? 'Stopping…' : 'Stop after current'}
        </Button>
        <Button variant="outline" onclick={() => act(api.cancel)} title="Cancel the running job"><SquareIcon />Cancel</Button>
      {:else}
        <Button disabled={!runnable} onclick={() => act(() => api.start())} title="Run every ready job in order">
          <PlayIcon />Start queue
        </Button>
      {/if}
      <Button variant="outline" disabled={!selected.length} onclick={() => act(() => api.start(selected))} title="Queue the selected jobs and start">
        <PlayIcon />Run selected
      </Button>
      <span class="flex-1"></span>
      <Button variant="ghost" size="icon" disabled={!selected.length} onclick={() => move(-1)} title="Move up"><ArrowUpIcon /></Button>
      <Button variant="ghost" size="icon" disabled={!selected.length} onclick={() => move(1)} title="Move down"><ArrowDownIcon /></Button>
      <Button variant="ghost" size="icon" disabled={!selected.length} onclick={() => act(() => api.reprobe(selected))} title="Probe again">
        <RefreshCwIcon />
      </Button>
      <Button variant="ghost" size="icon" class="hover:text-destructive" disabled={!selected.length} onclick={remove} title="Remove"
        ><Trash2Icon /></Button
      >
    </div>

    <div class="min-h-0 flex-1 overflow-auto">
      {#each app.jobs as job (job.id)}
        <button
          class="block w-full border-b border-border/60 px-3 py-2 text-left
            {selected.includes(job.id) ? 'bg-primary/15' : 'hover:bg-accent'}"
          onclick={e => click(e, job.id)}
        >
          <div class="flex items-center gap-2">
            <span class="truncate font-medium" title={job.source}>{job.name}</span>
            <span class="ml-auto shrink-0 text-xs {STATUS_TONE[job.status]}">{STATUS_LABEL[job.status]}</span>
          </div>
          <div class="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{job.encoder}</span>
            {#if job.custom_script}
              <span>· custom script</span>
            {:else if job.crop && (job.crop.top || job.crop.bottom || job.crop.left || job.crop.right)}
              <span>· crop {job.crop.left}/{job.crop.top}/{job.crop.right}/{job.crop.bottom}</span>
            {/if}
            <span>· {job.audio.length} audio · {job.subs} subs</span>
          </div>
          {#if job.status === 'running' && job.progress}
            <div class="mt-1.5 flex items-center gap-2 text-xs text-info">
              <div class="h-1 flex-1 overflow-hidden rounded bg-muted">
                <div class="h-full bg-info" style="width:{job.progress.overall * 100}%"></div>
              </div>
              {percent(job.progress.overall)}
            </div>
            <div class="truncate text-xs text-muted-foreground">{job.progress.step}</div>
          {:else if job.issue}
            <div class="mt-0.5 truncate text-xs {['blocked', 'error', 'failed', 'invalid'].includes(job.status) ? 'text-destructive' : 'text-warning'}">
              {job.issue}
            </div>
          {/if}
        </button>
      {:else}
        <div class="p-6 text-center text-muted-foreground">
          No jobs yet. <Button variant="link" class="h-auto p-0" onclick={() => router.go('new')}>Add some</Button>.
        </div>
      {/each}
    </div>
  </section>
  {/if}

  <section class="min-w-0 flex-1">
    {#if single}
      {#key single}<JobEditor jobId={single} />{/key}
    {:else if selected.length > 1}
      <div class="max-w-3xl space-y-6 p-6">
        <h2 class="text-lg font-semibold">{selected.length} jobs selected</h2>
        <p class="text-sm text-muted-foreground">
          Settings here apply to every selected job (queued or running ones are skipped). Starting values are the first
          job's. Audio and subtitle choices stay per job unless the template sets them.
        </p>
        {#if batchSource}
          <Card.Root class="gap-2 p-4">
            <div class="flex flex-wrap items-center gap-3">
              <span class="text-sm">Template</span>
              <NativeSelect aria-label="Template for the selected jobs" value={picked?.name ?? ''} onchange={e => (batchTemplate = e.currentTarget.value)}>
                {#each batchTemplates as c (`${c.builtin}:${c.name}`)}<option value={c.name}>{c.name}</option>{/each}
              </NativeSelect>
              <Button class="ml-auto" onclick={applyTemplate} disabled={!picked}><LayoutTemplateIcon />Apply to {selected.length} jobs</Button>
            </div>
            <p class="text-xs text-muted-foreground">
              Sets video, encoder, container, AutoQPF{picked?.data.audio ? ', audio' : ''}{picked?.data.crop_mode === 'auto'
                ? '; the crop is detected for each job'
                : picked?.data.crop_mode === 'fixed'
                  ? `; crop ${picked.data.video.crop.left}/${picked.data.video.crop.top}/${picked.data.video.crop.right}/${picked.data.video.crop.bottom} on every job`
                  : '; each job keeps its crop'}. Save templates from a job's Template menu.
            </p>
          </Card.Root>
          {#if batchContainers.length > 1}
            <Card.Root class="flex-row items-center gap-3 p-4">
              <span class="text-sm">Container</span>
              <ToggleGroup.Root
                type="single"
                variant="outline"
                class="w-fit"
                value={batchSource.spec.mux.container || batchContainers[0].id}
                onValueChange={v => v && applyContainer(v)}
              >
                {#each batchContainers as c (c.id)}
                  <ToggleGroup.Item value={c.id} class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{c.label}</ToggleGroup.Item>
                {/each}
              </ToggleGroup.Root>
              <span class="text-xs text-muted-foreground">Each job keeps its extra muxer arguments.</span>
            </Card.Root>
          {/if}
          <Card.Root class="p-4">
            <EncoderPanel value={batchSource.spec.encoder} onchange={applyEncoder} />
          </Card.Root>
          <Card.Root class="flex-row items-center gap-3 p-4">
            <span class="text-sm">
              Crop from {batchSource.name}: {batchSource.spec.video.crop.left}/{batchSource.spec.video.crop.top}/{batchSource
                .spec.video.crop.right}/{batchSource.spec.video.crop.bottom}
            </span>
            <Button variant="outline" class="ml-auto" onclick={applyCrop}><CropIcon />Apply this crop to all</Button>
          </Card.Root>
        {/if}
      </div>
    {:else}
      <div class="flex h-full items-center justify-center text-muted-foreground">Select a job to edit it.</div>
    {/if}
  </section>
</div>
