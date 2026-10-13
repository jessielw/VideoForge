<script lang="ts">
  // A job's last run, step by step: status, command line, exit code, time, error and output.
  // The running step and a failed one open by themselves; the others on click. "Full log"
  // shows every line of the job as one text, as before.
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import type { StepRun, StepStatus } from '../lib/types'
  import Icon, { type IconName } from './Icon.svelte'

  let { jobId, running }: { jobId: string; running: boolean } = $props()

  const SHOWN = 500 // lines per step on screen; the rest behind "show all"
  let view = $state<'steps' | 'full'>('steps')
  let base = $state<Record<string, string[]>>({}) // each step's lines in the snapshot
  let partial = $state<Record<string, boolean>>({})
  let since = $state(0) // app.logSeq when the snapshot arrived
  let loaded = $state(false)
  let open = $state<Record<string, boolean>>({})
  let showAll = $state<Record<string, boolean>>({})
  let full = $state<string[]>([])
  let fullSince = $state(0)
  let copied = $state('')

  // The snapshot: on opening a job, and when a run ends. During a run the step events keep
  // app.runs current, and a refetch could overwrite them with an older list.
  async function load(id: string) {
    const steps = await api.steps(id).catch(() => null)
    if (!steps || id !== jobId) return
    since = app.logSeq
    base = Object.fromEntries(steps.map(s => [s.id, s.lines]))
    partial = Object.fromEntries(steps.map(s => [s.id, s.partial]))
    app.runs[id] = steps.map(({ lines: _l, partial: _p, ...s }) => s)
    loaded = true
  }

  $effect(() => {
    const id = jobId
    if (!running) load(id)
  })

  $effect(() => {
    if (view === 'full') {
      const id = jobId
      api.log(id).then(r => {
        full = r.lines
        fullSince = app.logSeq
      })
    }
  })

  // A run that started after the snapshot replaces it: its lines all come live.
  const runStart = $derived(app.runStarts[jobId] ?? 0)
  const fresh = $derived(runStart > since)
  const steps = $derived((app.runs[jobId] ?? []).filter((s): s is StepRun => !!s))

  const live = $derived.by(() => {
    const from = fresh ? runStart : since
    const out: Record<string, string[]> = {}
    for (const l of app.log) {
      if (l.seq > from && l.job === jobId && l.step) (out[l.step] ??= []).push(l.line)
    }
    return out
  })

  function linesOf(id: string): string[] {
    return [...(fresh ? [] : (base[id] ?? [])), ...(live[id] ?? [])]
  }

  const fullLines = $derived(
    view === 'full' ? [...full, ...app.log.filter(l => l.job === jobId && l.seq > fullSince).map(l => l.line)] : [],
  )

  const LOOK: Record<StepStatus, { icon: IconName; tone: string; text: string }> = {
    pending: { icon: 'pause', tone: 'text-muted', text: 'waiting' },
    running: { icon: 'play', tone: 'text-info', text: 'running' },
    done: { icon: 'check', tone: 'text-ok', text: 'done' },
    reused: { icon: 'refresh', tone: 'text-ok', text: 'reused' },
    failed: { icon: 'x', tone: 'text-bad', text: 'failed' },
    cancelled: { icon: 'stop', tone: 'text-warn', text: 'cancelled' },
  }

  function outcome(s: StepRun): string {
    const parts = []
    if (s.exit_code !== null) parts.push(`exit ${s.exit_code}`)
    if (s.status !== 'pending' && s.status !== 'running') parts.push(`${s.seconds}s`)
    return parts.join(' · ')
  }

  async function copy(s: StepRun) {
    try {
      await navigator.clipboard.writeText(s.command)
      copied = s.id
      setTimeout(() => (copied = ''), 1500)
    } catch {
      /* no clipboard (e.g. not a secure context) */
    }
  }

  // Keep a growing output scrolled to the end, unless the user scrolled up to read.
  function follow(node: HTMLElement, _content: unknown) {
    let stick = true
    const onscroll = () => (stick = node.scrollHeight - node.scrollTop - node.clientHeight < 40)
    node.addEventListener('scroll', onscroll)
    node.scrollTop = node.scrollHeight
    return {
      update() {
        if (stick) node.scrollTop = node.scrollHeight
      },
      destroy() {
        node.removeEventListener('scroll', onscroll)
      },
    }
  }
</script>

<div class="flex h-full min-h-0 flex-col gap-3">
  <div class="flex items-center gap-3">
    <div class="flex rounded-md border border-line p-0.5">
      {#each [['steps', 'Steps'], ['full', 'Full log']] as [id, label] (id)}
        <button
          class="rounded px-3 py-1 text-sm {view === id ? 'bg-raised text-accent' : 'text-muted'}"
          onclick={() => (view = id as 'steps' | 'full')}>{label}</button
        >
      {/each}
    </div>
    {#if view === 'steps' && steps.length}
      <span class="text-xs text-muted">
        {steps.filter(s => s.status === 'done' || s.status === 'reused').length}/{steps.length} steps done
      </span>
      <button class="btn-ghost ml-auto text-xs" onclick={() => (open = Object.fromEntries(steps.map(s => [s.id, true])))}
        >Open all</button
      >
      <button class="btn-ghost text-xs" onclick={() => (open = Object.fromEntries(steps.map(s => [s.id, false])))}
        >Close all</button
      >
    {/if}
  </div>

  {#if view === 'full'}
    <pre
      class="min-h-0 flex-1 overflow-auto rounded-md border border-line bg-panel p-3 font-mono text-xs leading-relaxed"
      use:follow={fullLines.length}>{fullLines.join('\n') || 'No output yet.'}</pre>
  {:else if !steps.length}
    <p class="text-sm text-muted">
      {loaded ? 'No run yet. Each step shows up here when the job runs (the Encoder tab lists their commands).' : 'Loading…'}
    </p>
  {:else}
    <div class="min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      {#each steps as s, i (s.id)}
        {@const look = LOOK[s.status]}
        {@const isOpen = open[s.id] ?? (s.status === 'running' || s.status === 'failed')}
        <section class="rounded-md border {s.status === 'failed' ? 'border-bad/60' : 'border-line'}">
          <button
            class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-raised/50"
            aria-expanded={isOpen}
            onclick={() => (open[s.id] = !isOpen)}
          >
            <Icon name={isOpen ? 'down' : 'right'} size={14} class="shrink-0 text-muted" />
            <span class="w-10 shrink-0 text-xs text-muted">{i + 1}/{steps.length}</span>
            <span class="min-w-0 flex-1 truncate {s.status === 'pending' ? 'text-muted' : ''}">{s.label}</span>
            <span class="flex shrink-0 items-center gap-1 text-xs {look.tone}">
              <Icon name={look.icon} size={13} />{look.text}
            </span>
            <span class="w-24 shrink-0 text-right text-xs text-muted">{outcome(s)}</span>
          </button>
          {#if isOpen}
            {@const lines = linesOf(s.id)}
            {@const shown = showAll[s.id] ? lines : lines.slice(-SHOWN)}
            <div class="space-y-2 border-t border-line p-3">
              {#if s.command}
                <div class="flex items-start gap-2">
                  <code class="min-w-0 flex-1 rounded bg-raised px-2 py-1 font-mono text-[11px] break-all">{s.command}</code>
                  <button class="btn-ghost shrink-0 px-2 text-xs" title="Copy the command line" onclick={() => copy(s)}>
                    <Icon name={copied === s.id ? 'check' : 'copy'} size={13} />
                  </button>
                </div>
              {:else}
                <p class="text-xs text-muted">Runs inside VideoForge (no external command).</p>
              {/if}
              {#if s.error}
                <pre class="rounded-md border border-bad/50 bg-bad/10 p-2 text-xs whitespace-pre-wrap text-bad">{s.error}</pre>
              {/if}
              {#if lines.length}
                {#if lines.length > shown.length}
                  <button class="btn-ghost text-xs" onclick={() => (showAll[s.id] = true)}
                    >Show all {lines.length} lines ({lines.length - shown.length} hidden)</button
                  >
                {:else if !fresh && partial[s.id]}
                  <p class="text-xs text-muted">The last lines only (the full output is in the work folder's videoforge.log).</p>
                {/if}
                <pre
                  class="max-h-96 overflow-auto rounded-md border border-line bg-panel p-2 font-mono text-[11px] leading-relaxed"
                  use:follow={lines.length}>{shown.join('\n')}</pre>
              {:else if s.status !== 'pending'}
                <p class="text-xs text-muted">No output.</p>
              {/if}
            </div>
          {/if}
        </section>
      {/each}
    </div>
  {/if}
</div>
