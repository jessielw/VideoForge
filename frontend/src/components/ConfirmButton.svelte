<script lang="ts">
  // Two-click button: the first click arms it ("Confirm?") and a second click within
  // `seconds` runs onconfirm; otherwise it reverts to its normal label.
  import type { Snippet } from 'svelte'
  import { onDestroy } from 'svelte'
  import { Button } from '$lib/components/ui/button'

  let {
    onconfirm,
    children,
    seconds = 4,
    confirmLabel = 'Confirm?',
    variant = 'ghost',
    class: className = '',
    disabled = false,
  }: {
    onconfirm: () => void
    children: Snippet
    seconds?: number
    confirmLabel?: string
    variant?: 'ghost' | 'outline' | 'destructive'
    class?: string
    disabled?: boolean
  } = $props()

  let armed = $state(false)
  let timer: ReturnType<typeof setTimeout> | undefined

  function disarm() {
    armed = false
    clearTimeout(timer)
  }

  function click() {
    if (armed) {
      disarm()
      onconfirm()
      return
    }
    armed = true
    timer = setTimeout(disarm, seconds * 1000)
  }

  onDestroy(() => clearTimeout(timer))
</script>

<Button
  variant={armed ? 'destructive' : variant}
  class={armed ? '' : className}
  {disabled}
  onclick={click}
  onblur={disarm}
>
  {#if armed}{confirmLabel}{:else}{@render children()}{/if}
</Button>
