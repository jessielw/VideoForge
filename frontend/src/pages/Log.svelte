<script lang="ts">
  // Everything the jobs printed since the page opened, optionally one job only.
  import { tick } from 'svelte'
  import { app } from '../lib/state.svelte'

  let filter = $state<string>('')
  let follow = $state(true)
  let box = $state<HTMLPreElement>()

  const lines = $derived(filter ? app.log.filter(l => l.job === filter) : app.log)
  const jobs = $derived([...new Set(app.log.map(l => l.job).filter((j): j is string => !!j))])

  function tone(line: string): string {
    const low = line.toLowerCase()
    if (/error|failed|traceback|invalid/.test(low)) return 'text-bad'
    if (/warn|skipped|cancel/.test(low)) return 'text-warn'
    if (line.startsWith('== ') || line.startsWith('### ')) return 'font-semibold text-accent'
    return ''
  }

  $effect(() => {
    void lines.length
    if (follow) tick().then(() => box && (box.scrollTop = box.scrollHeight))
  })
</script>

<div class="flex h-full flex-col gap-3 p-6">
  <header class="flex items-center gap-3">
    <h1 class="text-xl font-semibold">Log</h1>
    <select class="field" bind:value={filter}>
      <option value="">All jobs</option>
      {#each jobs as id (id)}<option value={id}>{app.jobName(id)}</option>{/each}
    </select>
    <label class="flex items-center gap-2 text-sm text-muted"><input type="checkbox" bind:checked={follow} />Follow</label>
    <button class="btn ml-auto" onclick={() => (app.log = [])}>Clear</button>
  </header>
  <pre bind:this={box} class="min-h-0 flex-1 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-xs leading-relaxed">{#each lines as l, i (i)}<div class={tone(l.line)}>{filter ? '' : `${app.jobName(l.job)}: `}{l.line}</div>{:else}<span class="text-muted">Output from probes and runs appears here.</span>{/each}</pre>
</div>
