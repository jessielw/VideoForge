<script lang="ts">
  // A job's last run, step by step: status, command line, exit code, time, error and output.
  // The running step and a failed one open by themselves; the others on click. "Full log"
  // shows every line of the job as one text, as before.
  import { api } from '../lib/api'
  import { mergeSteps } from '../lib/logSnapshot'
  import { app } from '../lib/state.svelte'
  import type { StepRun, StepStatus } from '../lib/types'
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
  import CopyIcon from '@lucide/svelte/icons/copy'
  import LoaderIcon from '@lucide/svelte/icons/loader-circle'
  import PauseIcon from '@lucide/svelte/icons/pause'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import SquareIcon from '@lucide/svelte/icons/square'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import * as Tabs from '$lib/components/ui/tabs'

  let { jobId, running }: { jobId: string; running: boolean } = $props()

  const SHOWN = 500 // lines per step on screen; the rest behind "show all"
  let view = $state('steps') // 'steps' | 'full'
  let base = $state<Record<string, string[]>>({}) // each step's lines in the snapshot
  let partial = $state<Record<string, boolean>>({})
  let since = $state(0) // app.logSeq when the snapshot arrived
  let loaded = $state(false)
  let open = $state<Record<string, boolean>>({})
  let showAll = $state<Record<string, boolean>>({})
  let full = $state<string[]>([])
  let cursor = $state(0)
  let error = $state('')
  let requestSeq = 0
  let copied = $state('')

  // The snapshot: on opening a job, and when a run ends. During a run the step events keep
  // app.runs current, and a refetch could overwrite them with an older list.
  async function load(id: string) {
    const request = ++requestSeq
    const started = app.logSeq
    let snapshot
    try {
      snapshot = await api.logSnapshot(id)
    } catch (e) {
      if (request === requestSeq) error = e instanceof Error ? e.message : String(e)
      return
    }
    if (request !== requestSeq || id !== jobId) return
    if ((app.runStarts[id] ?? 0) > started) {
      void load(id)
      return
    }
    const { steps } = snapshot
    since = app.logSeq
    cursor = snapshot.seq
    full = snapshot.lines
    error = ''
    base = Object.fromEntries(steps.map((s) => [s.id, s.lines]))
    partial = Object.fromEntries(steps.map((s) => [s.id, s.partial]))
    app.runs[id] = mergeSteps(steps, app.runs[id] ?? [], app.stepVersions[id] ?? {}, cursor)
    loaded = true
  }

  $effect(() => {
    const id = jobId
    void running
    void app.connectionVersion
    loaded = false
    void load(id)
  })

  // A run that started after the snapshot replaces it: its lines all come live.
  const runStart = $derived(app.runStarts[jobId] ?? 0)
  const fresh = $derived(runStart > since)
  const steps = $derived((app.runs[jobId] ?? []).filter((s): s is StepRun => !!s))

  const live = $derived.by(() => {
    const from = fresh ? runStart : since
    const out: Record<string, string[]> = {}
    for (const l of app.log) {
      if ((fresh ? l.seq > from : (l.remoteSeq ?? 0) > cursor) && l.job === jobId && l.step)
        (out[l.step] ??= []).push(l.line)
    }
    return out
  })

  function linesOf(id: string): string[] {
    return [...(fresh ? [] : (base[id] ?? [])), ...(live[id] ?? [])]
  }

  const fullLines = $derived(
    view === 'full'
      ? [...full, ...app.log.filter((l) => l.job === jobId && (l.remoteSeq ?? 0) > cursor).map((l) => l.line)]
      : [],
  )

  const LOOK: Record<StepStatus, { icon: typeof CheckIcon; tone: string; text: string }> = {
    pending: { icon: PauseIcon, tone: 'text-muted-foreground', text: 'waiting' },
    running: { icon: LoaderIcon, tone: 'text-info', text: 'running' },
    done: { icon: CheckIcon, tone: 'text-success', text: 'done' },
    reused: { icon: RefreshCwIcon, tone: 'text-success', text: 'reused' },
    failed: { icon: XIcon, tone: 'text-destructive', text: 'failed' },
    cancelled: { icon: SquareIcon, tone: 'text-warning', text: 'cancelled' },
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
  {#if error}<div role="alert" class="text-sm text-destructive">
      Couldn't load the log: {error}
      <Button size="sm" onclick={() => load(jobId)}>Retry</Button>
    </div>{/if}
  <div class="flex flex-wrap items-center gap-3 max-sm:gap-x-2 max-sm:gap-y-1">
    <Tabs.Root bind:value={view}>
      <Tabs.List>
        <Tabs.Trigger value="steps" class="px-3">Steps</Tabs.Trigger>
        <Tabs.Trigger value="full" class="px-3">Full log</Tabs.Trigger>
      </Tabs.List>
    </Tabs.Root>
    {#if view === 'steps' && steps.length}
      <span class="text-xs text-muted-foreground">
        {steps.filter((s) => s.status === 'done' || s.status === 'reused').length}/{steps.length} steps done
      </span>
      <Button
        variant="ghost"
        size="sm"
        class="ml-auto"
        onclick={() => (open = Object.fromEntries(steps.map((s) => [s.id, true])))}>Open all</Button
      >
      <Button variant="ghost" size="sm" onclick={() => (open = Object.fromEntries(steps.map((s) => [s.id, false])))}
        >Close all</Button
      >
    {/if}
  </div>

  {#if view === 'full'}
    <pre
      class="min-h-0 flex-1 overflow-auto rounded-lg border bg-card p-3 font-mono text-xs leading-relaxed max-sm:p-2 max-sm:wrap-anywhere max-sm:whitespace-pre-wrap"
      use:follow={fullLines.length}>{fullLines.join('\n') || 'No output yet.'}</pre>
  {:else if !steps.length}
    <p class="text-sm text-muted-foreground">
      {loaded
        ? 'No run yet. Each step shows up here when the job runs (the Encoder tab lists their commands).'
        : 'Loading…'}
    </p>
  {:else}
    <div class="min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      {#each steps as s, i (s.id)}
        {@const look = LOOK[s.status]}
        {@const isOpen = open[s.id] ?? (s.status === 'running' || s.status === 'failed')}
        <section
          class="overflow-hidden rounded-lg border bg-card {s.status === 'failed' ? 'border-destructive/60' : ''}"
        >
          <button
            class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-accent/50 max-sm:gap-2 max-sm:px-2"
            aria-expanded={isOpen}
            onclick={() => (open[s.id] = !isOpen)}
          >
            {#if isOpen}<ChevronDownIcon class="size-3.5 shrink-0 text-muted-foreground" />{:else}<ChevronRightIcon
                class="size-3.5 shrink-0 text-muted-foreground"
              />{/if}
            <span class="w-10 shrink-0 text-xs text-muted-foreground max-sm:hidden">{i + 1}/{steps.length}</span>
            <span class="min-w-0 flex-1 truncate {s.status === 'pending' ? 'text-muted-foreground' : ''}"
              >{s.label}</span
            >
            <span class="flex shrink-0 items-center gap-1 text-xs {look.tone}">
              <look.icon class="size-3.5 {s.status === 'running' ? 'animate-spin' : ''}" />{look.text}
            </span>
            <span class="w-24 shrink-0 text-right text-xs text-muted-foreground max-sm:w-auto">{outcome(s)}</span>
          </button>
          {#if isOpen}
            {@const lines = linesOf(s.id)}
            {@const shown = showAll[s.id] ? lines : lines.slice(-SHOWN)}
            <div class="space-y-2 border-t p-3">
              {#if s.command}
                <div class="flex items-start gap-2">
                  <code class="min-w-0 flex-1 rounded-md bg-muted px-2 py-1 font-mono text-[11px] break-all"
                    >{s.command}</code
                  >
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    class="shrink-0"
                    title="Copy the command line"
                    aria-label="Copy the command line"
                    onclick={() => copy(s)}
                  >
                    {#if copied === s.id}<CheckIcon />{:else}<CopyIcon />{/if}
                  </Button>
                </div>
              {:else}
                <p class="text-xs text-muted-foreground">Runs inside VideoForge (no external command).</p>
              {/if}
              {#if s.error}
                <pre
                  class="rounded-lg border border-destructive/50 bg-destructive/10 p-2 text-xs whitespace-pre-wrap text-destructive">{s.error}</pre>
              {/if}
              {#if lines.length}
                {#if lines.length > shown.length}
                  <Button variant="ghost" size="sm" onclick={() => (showAll[s.id] = true)}
                    >Show all {lines.length} lines ({lines.length - shown.length} hidden)</Button
                  >
                {:else if !fresh && partial[s.id]}
                  <p class="text-xs text-muted-foreground">
                    The last lines only (the full output is in the work folder's videoforge.log).
                  </p>
                {/if}
                <pre
                  class="max-h-96 overflow-auto rounded-lg border bg-background p-2 font-mono text-[11px] leading-relaxed max-sm:wrap-anywhere max-sm:whitespace-pre-wrap"
                  use:follow={lines.length}>{shown.join('\n')}</pre>
              {:else if s.status !== 'pending'}
                <p class="text-xs text-muted-foreground">No output.</p>
              {/if}
            </div>
          {/if}
        </section>
      {/each}
    </div>
  {/if}
</div>
