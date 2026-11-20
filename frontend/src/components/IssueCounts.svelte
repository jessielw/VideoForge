<script lang="ts">
  // A job's errors and warnings as counts, each with its icon (the Queue row, the job header); the job's Issues tab
  // lists them. The words say which kind, so the icons are only for the eye.
  import CircleXIcon from '@lucide/svelte/icons/circle-x'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import { issueCounts } from '../lib/format'

  let { counts }: { counts: { block: number; warn: number } } = $props()
  const errors = $derived(issueCounts({ block: counts.block, warn: 0 })[0])
  const warnings = $derived(issueCounts({ block: 0, warn: counts.warn })[0])
</script>

{#if errors}<span class="whitespace-nowrap"
    ><CircleXIcon aria-hidden="true" class="mr-1 inline size-3.5 align-[-2px] text-destructive" />{errors}</span
  >{/if}{#if errors && warnings}{' · '}{/if}{#if warnings}<span class="whitespace-nowrap"
    ><TriangleAlertIcon aria-hidden="true" class="mr-1 inline size-3.5 align-[-2px] text-warning" />{warnings}</span
  >{/if}
