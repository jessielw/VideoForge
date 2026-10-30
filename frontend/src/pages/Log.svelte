<script lang="ts">
  // Everything the jobs printed since the page opened, optionally one job only.
  import { tick } from 'svelte'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { app } from '../lib/state.svelte'

  let filter = $state<string>('')
  let follow = $state(true)
  let box = $state<HTMLPreElement>()

  const lines = $derived(filter ? app.log.filter((l) => l.job === filter) : app.log)
  const jobs = $derived([...new Set(app.log.map((l) => l.job).filter((j): j is string => !!j))])

  function tone(line: string): string {
    const low = line.toLowerCase()
    if (/error|failed|traceback|invalid/.test(low)) return 'text-destructive'
    if (/warn|skipped|cancel/.test(low)) return 'text-warning'
    if (line.startsWith('== ') || line.startsWith('### ')) return 'font-semibold text-primary'
    return ''
  }

  $effect(() => {
    void lines.length
    if (follow) tick().then(() => box && (box.scrollTop = box.scrollHeight))
  })
</script>

<div class="flex h-full flex-col gap-3 p-6 max-sm:p-3">
  <header class="flex items-center gap-3">
    <h1 class="text-xl font-semibold">Log</h1>
    <NativeSelect bind:value={filter} class="min-w-0" aria-label="Job">
      <option value="">All jobs</option>
      {#each jobs as id (id)}<option value={id}>{app.jobName(id)}</option>{/each}
    </NativeSelect>
    <label class="flex items-center gap-2 text-sm text-muted-foreground"><Checkbox bind:checked={follow} />Follow</label
    >
    <Button variant="outline" class="ml-auto" onclick={() => (app.log = [])}>Clear</Button>
  </header>
  <pre
    bind:this={box}
    class="min-h-0 flex-1 overflow-auto rounded-lg border bg-card p-3 font-mono text-xs leading-relaxed max-sm:p-2 max-sm:wrap-anywhere max-sm:whitespace-pre-wrap max-sm:[&>div]:pl-4 max-sm:[&>div]:-indent-4">{#each lines as l, i (i)}<div
        class={tone(l.line)}>{filter ? '' : `${app.jobName(l.job)}: `}{l.line}</div>{:else}<span
        class="text-muted-foreground">Output from probes and runs appears here.</span
      >{/each}</pre>
</div>
