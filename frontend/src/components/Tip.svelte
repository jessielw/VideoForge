<script lang="ts">
  // A styled tooltip for what it wraps, in place of a title attribute. The wrapper is a span, so a disabled
  // control still shows it and nothing is nested in a button; it isn't focusable either, so a click on text
  // tipped inside a button still focuses the button. With no text it stays in place, closed, so the wrapped
  // control isn't remounted when its tooltip comes and goes. Its class is merged over inline-flex, so
  // "block truncate" or "min-w-0 flex-1" can take the wrapped element's place.
  import type { Snippet } from 'svelte'
  import * as Tooltip from '$lib/components/ui/tooltip'
  import { cn } from '$lib/utils'

  let {
    text,
    side = 'top',
    class: className = '',
    children,
  }: {
    text?: string | null
    side?: 'top' | 'right' | 'bottom' | 'left'
    class?: string
    children: Snippet
  } = $props()
</script>

<Tooltip.Root disabled={!text}>
  <Tooltip.Trigger>
    {#snippet child({ props })}
      {@const { tabindex: _, ...rest } = props}
      <span {...rest} class={cn('inline-flex', className)}>{@render children()}</span>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content {side} class="whitespace-pre-line wrap-anywhere">{text}</Tooltip.Content>
</Tooltip.Root>
