<script lang="ts">
  // The settings most jobs leave alone, folded away. Closed, the title counts what in it differs from VideoForge's
  // defaults, and its warnings apart, so a closed section never hides a change or a warning.
  import type { Snippet } from 'svelte'
  import { advancedOpen, setAdvancedOpen } from '../lib/advanced.svelte'

  let {
    area,
    title,
    count = 0,
    warnings = 0,
    children,
  }: { area: string; title: string; count?: number; warnings?: number; children: Snippet } = $props()
  const open = $derived(!!advancedOpen[area])
</script>

<details {open} ontoggle={(e) => setAdvancedOpen(area, e.currentTarget.open)} class="rounded-lg border p-3">
  <summary class="cursor-pointer text-sm font-medium"
    >{title}{#if !open}{count ? ` (${count})` : ''}{#if warnings}<span class="text-warning"
          >{` · ${warnings} ${warnings === 1 ? 'warning' : 'warnings'}`}</span
        >{/if}{/if}</summary
  >
  <div class="space-y-4 pt-4">{@render children()}</div>
</details>
