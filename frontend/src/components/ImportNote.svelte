<script lang="ts">
  // After an import entry's name: what the import does with it (nothing shown for a new one).
  import type { ImportAction } from '../lib/types'

  let { action, name, original }: { action: ImportAction | undefined; name: string | undefined; original: string } = $props()
</script>

{#if action === 'copy' || (name !== undefined && name !== original)}<span class="font-normal text-muted-foreground">{' → '}{name}</span>
{:else if action === 'replaced'}<span class="ml-1 rounded bg-warning/15 px-1.5 py-0.5 text-xs font-normal text-warning">replaces yours</span>
{:else if action === 'unchanged'}<span class="ml-1 rounded bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">already the same</span>{/if}
