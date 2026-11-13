<script lang="ts">
  // Settings › Files & folders: the saved output folders New jobs offers (OutputFolderMenu), to pin, make the
  // default, or forget. They are the active profile's; the tab loads them each time it opens.
  import { onMount } from 'svelte'
  import PinIcon from '@lucide/svelte/icons/pin'
  import PinOffIcon from '@lucide/svelte/icons/pin-off'
  import StarIcon from '@lucide/svelte/icons/star'
  import XIcon from '@lucide/svelte/icons/x'
  import { toast } from 'svelte-sonner'
  import { api } from '../lib/api'
  import type { OutputFolder } from '../lib/api'
  import { forget, togglePin } from '../lib/outputFolders'
  import Tip from './Tip.svelte'

  let folders = $state<OutputFolder[] | null>(null)
  let fallback = $state('')

  onMount(async () => {
    const s = await api.settings().catch(() => null)
    folders = s?.output_folders ?? []
    fallback = s?.output_default ?? ''
  })

  async function save(next: OutputFolder[], def: string) {
    try {
      const s = await api.saveSettings({ output_folders: next, output_default: def })
      folders = s.output_folders
      fallback = s.output_default
    } catch (e) {
      toast.error("Couldn't save the folders", { description: e instanceof Error ? e.message : String(e) })
    }
  }
  const apply = (r: { folders: OutputFolder[]; fallback: string }) => save(r.folders, r.fallback)
</script>

{#snippet list(title: string, items: OutputFolder[])}
  {#if items.length}
    <div class="space-y-1">
      <h3 class="text-xs font-medium text-muted-foreground">{title}</h3>
      <ul class="divide-y rounded-md border">
        {#each items as f (f.path)}
          {@const isDefault = f.path === fallback}
          <li class="flex items-start gap-1 px-3 py-1.5">
            <span class="min-w-0 flex-1 py-1 font-mono text-xs break-all">{f.path}</span>
            {#if isDefault}<span class="py-1 text-xs text-muted-foreground">Default</span>{/if}
            {#if f.pinned}
              <Tip text={isDefault ? 'Default (click to clear)' : 'Make the default'}>
                <button
                  type="button"
                  class="rounded-sm p-1 text-muted-foreground hover:text-foreground"
                  aria-label={isDefault ? 'Clear the default' : `Make ${f.path} the default`}
                  onclick={() => save(folders!, isDefault ? '' : f.path)}
                >
                  <StarIcon class="size-3.5 {isDefault ? 'fill-current' : ''}" />
                </button>
              </Tip>
            {/if}
            <Tip text={f.pinned ? 'Unpin' : 'Pin'}>
              <button
                type="button"
                class="rounded-sm p-1 text-muted-foreground hover:text-foreground"
                aria-label="{f.pinned ? 'Unpin' : 'Pin'} {f.path}"
                onclick={() => apply(togglePin(folders!, f, fallback))}
              >
                {#if f.pinned}<PinOffIcon class="size-3.5" />{:else}<PinIcon class="size-3.5" />{/if}
              </button>
            </Tip>
            <Tip text="Forget this folder">
              <button
                type="button"
                class="rounded-sm p-1 text-muted-foreground hover:text-destructive"
                aria-label="Forget {f.path}"
                onclick={() => apply(forget(folders!, f, fallback))}
              >
                <XIcon class="size-3.5" />
              </button>
            </Tip>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
{/snippet}

<section class="col-span-full min-w-0 space-y-3" aria-label="Saved output folders">
  <h2 class="font-medium">Saved output folders</h2>
  {#if folders === null}
    <p class="text-xs text-muted-foreground">Loading…</p>
  {:else if folders.length}
    <p class="text-xs text-muted-foreground">
      Folders you add jobs to are saved here. Pinned folders stay; only the 10 newest others are kept. The default one
      fills in the output folder on New jobs.
    </p>
    {@render list(
      'Pinned',
      folders.filter((f) => f.pinned),
    )}
    {@render list(
      'Recent',
      folders.filter((f) => !f.pinned),
    )}
  {:else}
    <p class="text-xs text-muted-foreground">No saved folders yet. Folders you add jobs to are saved here.</p>
  {/if}
</section>
