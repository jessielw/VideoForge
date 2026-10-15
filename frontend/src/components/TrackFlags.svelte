<script lang="ts">
  // A template's track flags, with no source track to look at: each one cycles the source's -> on ->
  // off -> the source's (a missing key = the source's).
  import CheckIcon from '@lucide/svelte/icons/check'
  import XIcon from '@lucide/svelte/icons/x'
  import { Toggle } from '$lib/components/ui/toggle'
  import type { TrackProperty } from '../lib/types'

  let {
    value,
    onchange,
    flags,
    disabled = false,
  }: {
    value: Record<string, boolean>
    onchange: (v: Record<string, boolean>) => void
    flags: TrackProperty[]
    disabled?: boolean
  } = $props()

  function cycle(key: string) {
    const next = { ...value }
    const now = next[key]
    if (now === undefined) next[key] = true
    else if (now) next[key] = false
    else delete next[key]
    onchange(next)
  }
</script>

<div class="flex flex-wrap gap-1" role="group" aria-label="Flags">
  {#each flags as f (f.key)}
    {@const state = value[f.key]}
    <Toggle
      variant="outline"
      size="sm"
      class="h-6 rounded-full px-2 text-xs font-normal text-muted-foreground data-[state=on]:border-primary data-[state=on]:bg-primary/15
        data-[state=on]:text-primary {state === false ? 'line-through decoration-destructive' : ''}"
      pressed={state === true}
      {disabled}
      title="{f.label}: {state === undefined ? "the source's" : state ? 'on' : 'off'} (click to change). {f.help}"
      onPressedChange={() => cycle(f.key)}
      >{#if state === true}<CheckIcon class="size-3" />{:else if state === false}<XIcon class="size-3" />{/if}{f.label}</Toggle
    >
  {/each}
</div>
