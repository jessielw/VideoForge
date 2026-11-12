<script lang="ts">
  // MediaInfo's text report of one of the job's files: the source, its encode, added audio and subtitles.
  // The server parses it when asked (and keeps it while the file is unchanged), so a click waits here.
  import CheckIcon from '@lucide/svelte/icons/check'
  import CopyIcon from '@lucide/svelte/icons/copy'
  import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
  import RotateCwIcon from '@lucide/svelte/icons/rotate-cw'
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import * as Dialog from '$lib/components/ui/dialog'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { api } from '../lib/api'
  import { basename } from '../lib/format'
  import { LatestRequest } from '../lib/latestRequest'
  import type { JobDetail } from '../lib/types'

  let { open = $bindable(false), job }: { open?: boolean; job: JobDetail } = $props()

  const files = $derived.by(() => {
    const i = job.spec.inputs
    return [
      { path: i.source, label: `Source · ${basename(i.source)}` },
      ...(i.encode ? [{ path: i.encode, label: `Encode · ${basename(i.encode)}` }] : []),
      ...(i.audio ?? []).map((p) => ({ path: p, label: `Audio · ${basename(p)}` })),
      ...(i.subtitles ?? []).map((p) => ({ path: p, label: `Subtitles · ${basename(p)}` })),
    ]
  })

  let path = $state('')
  let text = $state('')
  let error = $state('')
  let loading = $state(false)
  let slow = $state(false) // the spinner shows only past a moment: a cached report just appears
  let copied = $state(false)
  let timer: ReturnType<typeof setTimeout> | undefined
  const latest = new LatestRequest()

  // The job's object is replaced on every save: these change only when their value does, so no reload.
  const id = $derived(job.id)
  const source = $derived(job.spec.inputs.source)

  // Each opening starts on the source, with nothing left from the last one.
  $effect(() => {
    if (open) {
      path = source
      text = error = ''
    } else {
      latest.invalidate()
      clearTimeout(timer)
      loading = slow = false
    }
  })

  $effect(() => {
    if (open && path) load(id, path)
  })

  async function load(id: string, file: string) {
    loading = true
    error = ''
    clearTimeout(timer)
    timer = setTimeout(() => (slow = true), 150)
    const result = await latest.run(() => api.mediainfo(id, file))
    if (!result) return // a newer request (or closing) took over
    clearTimeout(timer)
    loading = slow = false
    if ('error' in result) {
      text = ''
      error = result.error
    } else text = result.value.text
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      copied = true
      setTimeout(() => (copied = false), 1500)
    } catch {
      toast.error('Could not copy the report')
    }
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="flex max-h-[90vh] flex-col sm:max-w-4xl">
    <Dialog.Header>
      <Dialog.Title>MediaInfo</Dialog.Title>
      <Dialog.Description class="truncate">{basename(path)}</Dialog.Description>
    </Dialog.Header>
    <div class="flex items-center gap-2">
      {#if files.length > 1}
        <NativeSelect class="min-w-0 flex-1" aria-label="File" bind:value={path}>
          {#each files as f (f.path)}<option value={f.path}>{f.label}</option>{/each}
        </NativeSelect>
      {:else}
        <span class="flex-1"></span>
      {/if}
      <Button variant="outline" size="sm" disabled={loading || !text} onclick={copy}>
        {#if copied}<CheckIcon />Copied{:else}<CopyIcon />Copy{/if}
      </Button>
    </div>
    <div class="relative min-h-64 overflow-hidden rounded-lg border bg-muted/50">
      {#if error}
        <div class="flex h-64 flex-col items-center justify-center gap-3 p-4 text-center">
          <p class="text-destructive">{error}</p>
          <Button variant="outline" size="sm" onclick={() => load(id, path)}><RotateCwIcon />Try again</Button>
        </div>
      {:else}
        <pre
          class="h-[60vh] overflow-auto p-3 font-mono text-xs leading-relaxed whitespace-pre select-text
            transition-opacity {slow ? 'opacity-30' : ''}">{text}</pre>
        {#if slow}
          <div class="absolute inset-0 flex items-center justify-center gap-2 text-muted-foreground" aria-live="polite">
            <LoaderCircleIcon class="size-5 animate-spin" />Reading MediaInfo…
          </div>
        {/if}
      {/if}
    </div>
  </Dialog.Content>
</Dialog.Root>
