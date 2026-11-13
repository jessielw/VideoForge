<script lang="ts">
  // Settings › Files & folders: the saved output folders New jobs offers (OutputFolderMenu), to pin, make the
  // default, or forget. They are the active profile's; the tab loads them each time it opens.
  import { onMount, tick } from 'svelte'
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
  let section = $state<HTMLElement>()

  onMount(async () => {
    const s = await api.settings().catch(() => null)
    folders = s?.output_folders ?? []
    fallback = s?.output_default ?? ''
  })

  async function save(next: OutputFolder[], def: string): Promise<boolean> {
    try {
      const s = await api.saveSettings({ output_folders: next, output_default: def })
      folders = s.output_folders
      fallback = s.output_default
      return true
    } catch (e) {
      toast.error("Couldn't save the folders", { description: e instanceof Error ? e.message : String(e) })
      return false
    }
  }
  const apply = (r: { folders: OutputFolder[]; fallback: string }) => save(r.folders, r.fallback)

  // Pin and Forget re-create or remove the row the focused button is in, so focus follows the folder: to its
  // button in the other list, or to the next folder's Forget (the heading when none is left).
  async function focusAfter(selector: string | null) {
    await tick()
    const el = selector ? section?.querySelector<HTMLElement>(selector) : null
    ;(el ?? section?.querySelector<HTMLElement>('h2'))?.focus()
  }
  async function pin(f: OutputFolder) {
    if (await apply(togglePin(folders!, f, fallback))) focusAfter(`[data-pin="${CSS.escape(f.path)}"]`)
  }
  async function remove(f: OutputFolder) {
    const shown = [...folders!.filter((x) => x.pinned), ...folders!.filter((x) => !x.pinned)]
    const i = shown.findIndex((x) => x.path === f.path)
    const next = shown[i + 1] ?? shown[i - 1]
    if (await apply(forget(folders!, f, fallback))) focusAfter(next ? `[data-forget="${CSS.escape(next.path)}"]` : null)
  }
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
                data-pin={f.path}
                onclick={() => pin(f)}
              >
                {#if f.pinned}<PinOffIcon class="size-3.5" />{:else}<PinIcon class="size-3.5" />{/if}
              </button>
            </Tip>
            <Tip text="Forget this folder">
              <button
                type="button"
                class="rounded-sm p-1 text-muted-foreground hover:text-destructive"
                aria-label="Forget {f.path}"
                data-forget={f.path}
                onclick={() => remove(f)}
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

<section bind:this={section} class="col-span-full min-w-0 space-y-3" aria-label="Saved output folders">
  <h2 class="font-medium outline-none" tabindex="-1">Saved output folders</h2>
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
