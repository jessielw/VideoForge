<script lang="ts">
  // Light, dark, or follow the system (mode-watcher remembers the choice in this browser).
  import MonitorIcon from '@lucide/svelte/icons/monitor'
  import MoonIcon from '@lucide/svelte/icons/moon'
  import SunIcon from '@lucide/svelte/icons/sun'
  import { setMode, userPrefersMode } from 'mode-watcher'
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu'
  import { buttonVariants } from '$lib/components/ui/button'
  import { cn } from '$lib/utils'
  import Tip from './Tip.svelte'

  let { compact = false }: { compact?: boolean } = $props()

  const MODES = [
    { id: 'light', label: 'Light', icon: SunIcon },
    { id: 'dark', label: 'Dark', icon: MoonIcon },
    { id: 'system', label: 'System', icon: MonitorIcon },
  ] as const
  let open = $state(false)
  const current = $derived(MODES.find((m) => m.id === userPrefersMode.current) ?? MODES[2])
</script>

<DropdownMenu.Root bind:open>
  <Tip side="right" class="grid" text={compact ? `Theme: ${current.label}` : undefined}>
    <DropdownMenu.Trigger
      class={cn(
        buttonVariants({ variant: 'ghost', size: compact ? 'icon' : 'default' }),
        'text-muted-foreground',
        compact ? '' : 'w-full justify-start gap-3 px-3',
      )}
      aria-label="Theme: {current.label}"
    >
      <current.icon />
      {#if !compact}Theme: {current.label}{/if}
    </DropdownMenu.Trigger>
  </Tip>
  <DropdownMenu.Content side={compact ? 'right' : 'top'} align="start" class="w-36">
    <DropdownMenu.RadioGroup
      value={current.id}
      onValueChange={(v) => {
        setMode(v as 'light' | 'dark' | 'system')
        open = false
      }}
    >
      {#each MODES as m (m.id)}
        <DropdownMenu.RadioItem value={m.id}><m.icon />{m.label}</DropdownMenu.RadioItem>
      {/each}
    </DropdownMenu.RadioGroup>
  </DropdownMenu.Content>
</DropdownMenu.Root>
