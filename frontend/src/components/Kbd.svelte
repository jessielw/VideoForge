<script lang="ts">
  // A key as a keycap, for the shortcuts dialog and hints that name keys.
  import type { Snippet } from 'svelte'

  let { children }: { children: Snippet } = $props()
</script>

<kbd class="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs whitespace-nowrap">{@render children()}</kbd>
