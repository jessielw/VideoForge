<script lang="ts">
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import type { ManagedPreset, ManagedPresets } from '../lib/types'

  // The presets plugins ship. A plugin keeps the ones you haven't touched up to date; one you edited is
  // left alone (and says when the plugin has a newer version), one you deleted stays deleted. Reset puts
  // either back as the plugin ships it.
  let { disabled = false, refreshKey = 0 }: { disabled?: boolean; refreshKey?: number } = $props()
  let managed = $state<ManagedPresets | null>(null)
  let error = $state('')
  let busy = $state(false)
  let confirming = $state('') // the row whose reset would discard edits

  async function refresh() {
    try {
      managed = await api.managedPresets()
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }
  $effect(() => {
    refreshKey
    app.presets // an edit, import or profile switch changes what's current
    void refresh()
  })

  const kinds = { template: 'Template', video: 'Video', encoder: 'Encoder', audio: 'Audio' } as const
  const id = (p: ManagedPreset) => `${p.plugin}:${p.kind}:${p.key}`
  const needsAttention = (p: ManagedPreset) => p.state !== 'current' || p.update_available || p.retired
  const plugins = $derived(
    [...new Set(managed?.presets.map((p) => p.plugin) ?? [])].map((plugin) => {
      const all = managed!.presets.filter((p) => p.plugin === plugin)
      return { plugin, total: all.length, attention: all.filter(needsAttention) }
    }),
  )

  function describe(p: ManagedPreset) {
    if (p.state === 'removed') return 'Deleted by you'
    if (p.state === 'edited') return p.update_available ? 'Edited · newer version available' : 'Edited'
    return 'No longer shipped by the plugin'
  }

  async function reset(p: ManagedPreset) {
    if (p.state === 'edited' && confirming !== id(p)) {
      confirming = id(p)
      return
    }
    confirming = ''
    busy = true
    try {
      const result = await api.resetManagedPreset({ plugin: p.plugin, kind: p.kind, key: p.key })
      app.presets = result.presets
      await refresh()
      toast.success(`${p.label} is back as ${p.plugin} ships it`)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
</script>

{#if managed && (managed.presets.length || managed.problems.length)}
  <section class="col-span-full min-w-0 space-y-3">
    <h2 class="font-medium">Plugin presets</h2>
    <p class="text-xs text-muted-foreground">
      Presets that come with a plugin are updated with it. One you edited is kept as you left it; Reset puts it back as
      the plugin ships it.
    </p>
    <div class="divide-y rounded-md border">
      {#each plugins as { plugin, total, attention } (plugin)}
        <div class="space-y-2 px-4 py-3 text-sm">
          <p>
            <span class="font-medium">{plugin}</span>
            <span class="text-muted-foreground">
              · {total} preset{total === 1 ? '' : 's'}{attention.length
                ? `, ${attention.length} to look at`
                : ', all as shipped'}
            </span>
          </p>
          {#each attention as p (id(p))}
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span class="min-w-0 flex-1">
                <span class="text-muted-foreground">{kinds[p.kind]} ·</span>
                {[...p.group, p.label].join(' / ')}
                <span class="text-muted-foreground">— {describe(p)}</span>
              </span>
              {#if p.state !== 'current' && !p.retired}
                <Button
                  size="sm"
                  variant={confirming === id(p) ? 'destructive' : 'outline'}
                  disabled={busy || disabled}
                  onclick={() => reset(p)}
                  >{confirming === id(p) ? 'Discard my edits?' : p.state === 'removed' ? 'Restore' : 'Reset'}</Button
                >
              {/if}
            </div>
          {/each}
        </div>
      {/each}
    </div>
    {#each managed.problems as problem}<p class="text-xs text-destructive" role="alert">
        Plugin presets not used: {problem}
      </p>{/each}
    {#if error}<p class="text-xs text-destructive" role="alert">{error}</p>{/if}
  </section>
{/if}
