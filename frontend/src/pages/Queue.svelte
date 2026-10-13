<script lang="ts">
  // The queue: jobs on the left (click, Ctrl/Shift-click to select several), the selected
  // job's editor on the right, or a batch panel when several are selected.
  import EncoderPanel from '../components/EncoderPanel.svelte'
  import Icon from '../components/Icon.svelte'
  import JobEditor from '../components/JobEditor.svelte'
  import { api } from '../lib/api'
  import { percent, STATUS_LABEL, STATUS_TONE } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { layout } from '../lib/layout.svelte'
  import { app } from '../lib/state.svelte'
  import type { EncoderSettings, JobDetail } from '../lib/types'

  let selected = $state<string[]>([])
  let anchor = $state<string | null>(null)
  let message = $state('')

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
      message = ''
    } catch (e) {
      message = e instanceof Error ? e.message : String(e)
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
      if (r.removed.length < selected.length) message = 'Queued or running jobs were kept'
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
      message = `Encoder applied to ${r.updated.length} job(s)` + (r.skipped.length ? `, ${r.skipped.length} busy` : '')
    })
  }

  async function applyCrop() {
    if (!batchSource) return
    const crop = batchSource.spec.video.crop
    await act(async () => {
      const jobs = await Promise.all(selected.map(id => api.job(id)))
      for (const j of jobs) if (j.spec.inputs.encode === null) await api.update(j.id, { video: { ...j.spec.video, crop } })
      message = `Crop ${crop.left}/${crop.top}/${crop.right}/${crop.bottom} applied to ${jobs.length} job(s)`
    })
  }
</script>

<div class="flex h-full">
  {#if layout.queueCollapsed}
    <!-- The list as a rail: one chip per job (its place, coloured by status). -->
    <section class="flex w-14 shrink-0 flex-col items-center border-r border-line">
      <button class="btn-ghost my-2 px-2" onclick={() => (layout.queueCollapsed = false)} title="Show the queue list">
        <Icon name="right" />
      </button>
      <div class="flex min-h-0 w-full flex-1 flex-col items-center gap-1 overflow-auto border-t border-line py-2">
        {#each app.jobs as job, i (job.id)}
          <button
            class="relative flex h-9 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border text-xs
              {selected.includes(job.id) ? 'border-accent bg-accent-strong/15' : 'border-line hover:bg-raised'}
              {STATUS_TONE[job.status]}"
            onclick={e => click(e, job.id)}
            title="{job.name}: {STATUS_LABEL[job.status]}{job.issue ? ` (${job.issue})` : ''}"
          >
            {i + 1}
            {#if job.status === 'running' && job.progress}
              <span class="absolute inset-x-0 bottom-0 h-1 bg-raised">
                <span class="block h-full bg-info" style="width:{job.progress.overall * 100}%"></span>
              </span>
            {/if}
          </button>
        {/each}
      </div>
    </section>
  {:else}
  <section class="flex w-[28rem] shrink-0 flex-col border-r border-line">
    <div class="flex flex-wrap items-center gap-1 border-b border-line p-2">
      <button class="btn-ghost px-1" onclick={() => (layout.queueCollapsed = true)} title="Collapse the list, for more room">
        <Icon name="left" />
      </button>
      {#if app.queue.running}
        <button class="btn" onclick={() => act(api.stop)} title="Finish the current job, then stop">
          <Icon name="pause" />{app.queue.stop_after_current ? 'Stopping…' : 'Stop after current'}
        </button>
        <button class="btn" onclick={() => act(api.cancel)} title="Cancel the running job"><Icon name="stop" />Cancel</button>
      {:else}
        <button class="btn-primary" disabled={!runnable} onclick={() => act(() => api.start())} title="Run every ready job in order">
          <Icon name="play" />Start queue
        </button>
      {/if}
      <button class="btn" disabled={!selected.length} onclick={() => act(() => api.start(selected))} title="Queue the selected jobs and start">
        <Icon name="play" />Run selected
      </button>
      <span class="flex-1"></span>
      <button class="btn-ghost px-1.5" disabled={!selected.length} onclick={() => move(-1)} title="Move up"><Icon name="up" /></button>
      <button class="btn-ghost px-1.5" disabled={!selected.length} onclick={() => move(1)} title="Move down"><Icon name="down" /></button>
      <button class="btn-ghost px-1.5" disabled={!selected.length} onclick={() => act(() => api.reprobe(selected))} title="Probe again">
        <Icon name="refresh" />
      </button>
      <button class="btn-ghost px-1.5 hover:text-bad" disabled={!selected.length} onclick={remove} title="Remove"><Icon name="trash" /></button>
    </div>

    <div class="min-h-0 flex-1 overflow-auto">
      {#each app.jobs as job (job.id)}
        <button
          class="block w-full border-b border-line/60 px-3 py-2 text-left
            {selected.includes(job.id) ? 'bg-accent-strong/15' : 'hover:bg-raised'}"
          onclick={e => click(e, job.id)}
        >
          <div class="flex items-center gap-2">
            <span class="truncate font-medium" title={job.source}>{job.name}</span>
            <span class="ml-auto shrink-0 text-xs {STATUS_TONE[job.status]}">{STATUS_LABEL[job.status]}</span>
          </div>
          <div class="mt-0.5 flex items-center gap-2 text-xs text-muted">
            <span>{job.encoder}</span>
            {#if job.crop.top || job.crop.bottom || job.crop.left || job.crop.right}
              <span>· crop {job.crop.left}/{job.crop.top}/{job.crop.right}/{job.crop.bottom}</span>
            {/if}
            <span>· {job.audio.length} audio · {job.subs} subs</span>
          </div>
          {#if job.status === 'running' && job.progress}
            <div class="mt-1.5 flex items-center gap-2 text-xs text-info">
              <div class="h-1 flex-1 overflow-hidden rounded bg-raised">
                <div class="h-full bg-info" style="width:{job.progress.overall * 100}%"></div>
              </div>
              {percent(job.progress.overall)}
            </div>
            <div class="truncate text-xs text-muted">{job.progress.step}</div>
          {:else if job.issue}
            <div class="mt-0.5 truncate text-xs {['blocked', 'error', 'failed', 'invalid'].includes(job.status) ? 'text-bad' : 'text-warn'}">
              {job.issue}
            </div>
          {/if}
        </button>
      {:else}
        <div class="p-6 text-center text-muted">
          No jobs yet. <button class="text-accent underline" onclick={() => router.go('new')}>Add some</button>.
        </div>
      {/each}
    </div>
    {#if message}<div class="border-t border-line px-3 py-2 text-xs text-muted">{message}</div>{/if}
  </section>
  {/if}

  <section class="min-w-0 flex-1">
    {#if single}
      {#key single}<JobEditor jobId={single} />{/key}
    {:else if selected.length > 1}
      <div class="max-w-3xl space-y-6 p-6">
        <h2 class="text-lg font-semibold">{selected.length} jobs selected</h2>
        <p class="text-sm text-muted">
          Settings here apply to every selected job (queued or running ones are skipped). Starting values are the first
          job's. Audio and subtitle choices stay per job.
        </p>
        {#if batchSource}
          <div class="panel p-4">
            <EncoderPanel value={batchSource.spec.encoder} onchange={applyEncoder} />
          </div>
          <div class="panel flex items-center gap-3 p-4">
            <span class="text-sm">
              Crop from {batchSource.name}: {batchSource.spec.video.crop.left}/{batchSource.spec.video.crop.top}/{batchSource
                .spec.video.crop.right}/{batchSource.spec.video.crop.bottom}
            </span>
            <button class="btn ml-auto" onclick={applyCrop}><Icon name="crop" />Apply this crop to all</button>
          </div>
        {/if}
      </div>
    {:else}
      <div class="flex h-full items-center justify-center text-muted">Select a job to edit it.</div>
    {/if}
  </section>
</div>
