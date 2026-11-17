<script lang="ts">
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import { api } from '../lib/api'
  import { tick } from 'svelte'
  import { app } from '../lib/state.svelte'
  import { peekSettingsSection, takeSettingsSection } from '../lib/settingsLink'
  import type { ManagedPreset, ManagedPresets } from '../lib/types'

  // The presets plugins ship, which VideoForge keeps exactly as shipped: every start puts back one you edited
  // or deleted, and overwrites a preset of your own under its name (replaced). Between starts this lists those
  // (stale) and puts them back at once; StalePluginPresets says so across the app.
  let { disabled = false, refreshKey = 0 }: { disabled?: boolean; refreshKey?: number } = $props()
  let managed = $state<ManagedPresets | null>(null)
  let error = $state('')
  let busy = $state(false)
  let confirming = $state('') // the row (or "all:<plugin>") whose put-back would overwrite something of yours

  async function refresh() {
    try {
      managed = await api.managedPresets()
      error = ''
      if (peekSettingsSection() === 'plugin-presets') {
        // the app's stale-presets notice links here; the section shows only once this has loaded
        await tick()
        const target = document.getElementById('plugin-presets')
        if (target) {
          takeSettingsSection()
          target.scrollIntoView({ block: 'start' })
          target.focus({ preventScroll: true })
        }
      }
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
      const attention = all.filter(needsAttention)
      return {
        plugin,
        total: all.length,
        attention,
        stale: attention.filter((p) => p.stale),
      }
    }),
  )

  function describe(p: ManagedPreset) {
    if (p.retired) return 'no longer shipped by the plugin, so no longer kept as shipped'
    if (p.state === 'replaced')
      return `your own “${p.replaced_by ?? p.label}” has its name; the next start overwrites it with the plugin's`
    if (p.state === 'removed') return 'deleted; the next start puts it back'
    return 'edited; the next start puts it back as shipped'
  }

  // Something of yours is overwritten: an edit, or your own preset under the name.
  const overwrites = (ps: ManagedPreset[]) => ps.some((p) => p.state === 'edited' || p.state === 'replaced')

  async function restoreAll(plugin: string, stale: ManagedPreset[]) {
    if (overwrites(stale) && confirming !== `all:${plugin}`) {
      confirming = `all:${plugin}`
      return
    }
    confirming = ''
    busy = true
    try {
      let result
      for (const p of stale) result = await api.resetManagedPreset({ plugin, kind: p.kind, key: p.key })
      if (result) app.presets = result.presets
      toast.success(`${stale.length} presets are back as ${plugin} ships them`)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      await refresh()
      busy = false
    }
  }

  async function reset(p: ManagedPreset) {
    if (overwrites([p]) && confirming !== id(p)) {
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
  <section id="plugin-presets" tabindex="-1" class="col-span-full min-w-0 scroll-mt-6 space-y-3 outline-none">
    <h2 class="font-medium">Plugin presets</h2>
    <p class="text-xs text-muted-foreground">
      Presets that come with a plugin are kept exactly as the plugin ships them. Each time VideoForge starts, it puts
      back any you edited or deleted, and overwrites a preset of your own with the same name. To keep changes, save them
      as a preset under a new name.
    </p>
    <div class="divide-y rounded-md border">
      {#each plugins as { plugin, total, attention, stale } (plugin)}
        <div class="space-y-2 px-4 py-3 text-sm">
          <p class="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span class="min-w-0 flex-1">
              <span class="font-medium">{plugin}</span>
              <span class="text-muted-foreground">
                · {total} preset{total === 1 ? '' : 's'}{attention.length
                  ? `, ${attention.length} to look at`
                  : ', all as shipped'}
              </span>
            </span>
            {#if stale.length > 1}
              <Button
                size="sm"
                variant={confirming === `all:${plugin}` ? 'destructive' : 'outline'}
                disabled={busy || disabled}
                onclick={() => restoreAll(plugin, stale)}
                >{confirming === `all:${plugin}`
                  ? `Overwrite my changes to ${stale.length}?`
                  : `Put all back now (${stale.length})`}</Button
              >
            {/if}
          </p>
          {#if attention.length}
            <div class="max-h-64 space-y-2 overflow-y-auto pr-1">
              {#each attention as p (id(p))}
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                  <span class="min-w-0 flex-1">
                    <span class="text-muted-foreground">{kinds[p.kind]} ·</span>
                    {[...p.group, p.label].join(' / ')}
                    <span class="text-muted-foreground">— {describe(p)}</span>
                  </span>
                  {#if p.stale}
                    <Button
                      size="sm"
                      variant={confirming === id(p) ? 'destructive' : 'outline'}
                      disabled={busy || disabled}
                      onclick={() => reset(p)}
                      >{confirming === id(p)
                        ? p.state === 'replaced'
                          ? 'Overwrite my preset?'
                          : 'Discard my edits?'
                        : 'Put back now'}</Button
                    >
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>
    {#each managed.problems as problem}<p class="text-xs text-destructive" role="alert">
        A plugin's presets couldn't be read, so they aren't used: {problem}
      </p>{/each}
    {#if error}<p class="text-xs text-destructive" role="alert">{error}</p>{/if}
  </section>
{/if}
