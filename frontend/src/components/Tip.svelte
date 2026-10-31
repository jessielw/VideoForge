<script lang="ts">
  // A styled tooltip for what it wraps, in place of a title attribute. The wrapper is a span (out of the tab
  // order), so a disabled control still shows it and nothing is nested in a button; with no text it stays
  // in place, closed, so the wrapped control isn't remounted when its tooltip comes and goes.
  import type { Snippet } from 'svelte'
  import * as Tooltip from '$lib/components/ui/tooltip'

  let { text, class: className = '', children }: { text?: string | null; class?: string; children: Snippet } = $props()
</script>

<Tooltip.Root disabled={!text}>
  <Tooltip.Trigger tabindex={-1}>
    {#snippet child({ props })}
      <span {...props} class="inline-flex {className}">{@render children()}</span>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content class="whitespace-pre-line wrap-anywhere">{text}</Tooltip.Content>
</Tooltip.Root>
