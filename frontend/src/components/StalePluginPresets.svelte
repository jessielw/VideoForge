<script lang="ts">
  import { Button } from '$lib/components/ui/button'
  import { openSettings } from '../lib/settingsLink'
  import { router } from '../lib/router.svelte'
  import { app } from '../lib/state.svelte'

  // The app-wide notice that a plugin's presets differ from what it ships since the last start: edited, deleted,
  // or one of the user's own under a plugin preset's name. The next start puts them back; until then a new job
  // gets the changed settings. Dismissing hides it until the set of stale presets or a plugin's version changes.
  const DISMISS_KEY = 'videoforge.stalePluginPresets'
  // from /api/presets, which the app loads anyway and refreshes on every preset change
  const stale = $derived(app.presets.plugin_stale ?? [])
  let dismissed = $state(readDismissed())

  function readDismissed(): string {
    try {
      return localStorage.getItem(DISMISS_KEY) ?? ''
    } catch {
      return '' // storage blocked: the notice shows every time
    }
  }

  const signature = $derived(
    stale
      .map((p) => `${p.plugin}:${p.kind}:${p.key}:${p.shipping ?? ''}`)
      .sort()
      .join('|'),
  )
  const byPlugin = $derived(
    [...new Set(stale.map((p) => p.plugin))].map((plugin) => ({
      plugin,
      n: stale.filter((p) => p.plugin === plugin).length,
    })),
  )
  const visible = $derived(stale.length > 0 && signature !== dismissed && router.page !== 'settings')

  function dismiss() {
    dismissed = signature
    try {
      localStorage.setItem(DISMISS_KEY, signature)
    } catch {
      /* storage blocked: hidden until the page reloads */
    }
  }
</script>

{#if visible}
  <div
    class="mx-6 mt-4 flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-warning/50 bg-warning/10 px-4 py-3 text-sm"
    role="status"
  >
    <p class="min-w-0 flex-1">
      {#each byPlugin as { plugin, n }, i}{i ? '; ' : ''}<span class="font-medium">{plugin}</span>: {n}
        preset{n === 1 ? '' : 's'}{/each}
      {stale.length === 1 ? 'differs' : 'differ'} from what the plugin ships: edited, deleted, or one of your own under its
      name. The next start puts {stale.length === 1 ? 'it' : 'them'} back. Until then, new jobs get the changed settings.
    </p>
    <Button size="sm" variant="outline" onclick={() => openSettings('presets', 'plugin-presets')}>Review</Button>
    <Button size="sm" variant="ghost" onclick={dismiss}>Dismiss</Button>
  </div>
{/if}
