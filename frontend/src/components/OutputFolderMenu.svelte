<script lang="ts">
  // A dropdown of the output folders used before (newest first) and the pinned ones; one pinned folder can be the
  // default that pre-fills New jobs. Saved on this machine, never in a template.
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import PinIcon from '@lucide/svelte/icons/pin'
  import PinOffIcon from '@lucide/svelte/icons/pin-off'
  import StarIcon from '@lucide/svelte/icons/star'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu'
  import { api } from '../lib/api'
  import type { OutputFolder } from '../lib/api'
  import { forget, togglePin } from '../lib/outputFolders'
  import Tip from './Tip.svelte'

  let { onpick, disabled = false }: { onpick: (path: string) => void; disabled?: boolean } = $props()

  let folders = $state<OutputFolder[]>([])
  let fallback = $state('')
  let filter = $state('')
  const SEARCH_AT = 8 // a filter box only once the list is long enough to need one

  async function load() {
    const s = await api.settings().catch(() => null)
    folders = s?.output_folders ?? []
    fallback = s?.output_default ?? ''
  }

  async function save(next: OutputFolder[], def = fallback) {
    const s = await api.saveSettings({ output_folders: next, output_default: def }).catch(() => null)
    if (s) {
      folders = s.output_folders
      fallback = s.output_default
    }
  }

  const shown = $derived(folders.filter((f) => f.path.toLowerCase().includes(filter.trim().toLowerCase())))
  const pinned = $derived(shown.filter((f) => f.pinned))
  const recent = $derived(shown.filter((f) => !f.pinned))
  const apply = (r: { folders: OutputFolder[]; fallback: string }) => save(r.folders, r.fallback)
  const toggle = (f: OutputFolder) => apply(togglePin(folders, f, fallback))
  const remove = (f: OutputFolder) => apply(forget(folders, f, fallback))
</script>

{#snippet row(f: OutputFolder)}
  <div class="flex items-center gap-1">
    <DropdownMenu.Item class="min-w-0 flex-1" onSelect={() => onpick(f.path)}>
      <Tip class="block min-w-0 flex-1 truncate font-mono text-xs" text={f.path}>{f.path}</Tip>
      {#if f.path === fallback}<StarIcon
          class="size-3.5 fill-current text-muted-foreground"
          aria-label="Default"
        />{/if}
    </DropdownMenu.Item>
    {#if f.pinned}
      <Tip text={f.path === fallback ? 'Default (click to clear)' : 'Make the default'}>
        <button
          class="rounded-sm p-1 text-muted-foreground hover:text-foreground"
          aria-label={f.path === fallback ? 'Clear default' : 'Make default'}
          onclick={() => save(folders, f.path === fallback ? '' : f.path)}
        >
          <StarIcon class="size-3.5 {f.path === fallback ? 'fill-current' : ''}" />
        </button>
      </Tip>
    {/if}
    <Tip text={f.pinned ? 'Unpin' : 'Pin'}>
      <button
        class="rounded-sm p-1 text-muted-foreground hover:text-foreground"
        aria-label={f.pinned ? 'Unpin' : 'Pin'}
        onclick={() => toggle(f)}
      >
        {#if f.pinned}<PinOffIcon class="size-3.5" />{:else}<PinIcon class="size-3.5" />{/if}
      </button>
    </Tip>
    <Tip text="Forget this folder">
      <button
        class="rounded-sm p-1 text-muted-foreground hover:text-destructive"
        aria-label="Forget"
        onclick={() => remove(f)}
      >
        <XIcon class="size-3.5" />
      </button>
    </Tip>
  </div>
{/snippet}

<DropdownMenu.Root
  onOpenChange={(open) => {
    filter = ''
    if (open) load()
  }}
>
  <DropdownMenu.Trigger {disabled}>
    {#snippet child({ props })}
      <Button {...props} variant="outline" aria-label="Saved output folders">
        Saved<ChevronDownIcon class="size-3.5 text-muted-foreground" />
      </Button>
    {/snippet}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="end" class="w-[min(32rem,90vw)]">
    {#if folders.length > SEARCH_AT}
      <!-- Keys stay in the box: the menu would otherwise type-ahead or move focus away. -->
      <Input
        class="mb-1 h-8 text-xs"
        placeholder="Filter folders…"
        aria-label="Filter saved folders"
        bind:value={filter}
        onkeydown={(e) => {
          if (e.key !== 'Escape') e.stopPropagation()
        }}
      />
    {/if}
    {#if !folders.length}
      <DropdownMenu.Label>Folders you add jobs to are saved here.</DropdownMenu.Label>
    {:else if !shown.length}
      <DropdownMenu.Label>No saved folder matches.</DropdownMenu.Label>
    {/if}
    {#if pinned.length}
      <DropdownMenu.Label>Pinned</DropdownMenu.Label>
      {#each pinned as f (f.path)}{@render row(f)}{/each}
    {/if}
    {#if pinned.length && recent.length}<DropdownMenu.Separator />{/if}
    {#if recent.length}
      <DropdownMenu.Label>Recent</DropdownMenu.Label>
      {#each recent as f (f.path)}{@render row(f)}{/each}
    {/if}
  </DropdownMenu.Content>
</DropdownMenu.Root>
