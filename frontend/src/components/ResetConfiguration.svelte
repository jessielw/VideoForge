<script lang="ts">
  import { toast } from 'svelte-sonner'
  import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { saves } from '../lib/saves'
  import { drafts } from '../lib/drafts'
  import type { ConfigState } from '../lib/types'

  let { disabled = false, onreset }: { disabled?: boolean; onreset: (config: ConfigState) => void } = $props()
  const WORD = 'RESET'
  let open = $state(false)
  let busy = $state(false)
  let error = $state('')
  let typed = $state('')
  let scopes = $state({ settings: true, presets: false, jobs: false })
  const ready = $derived(typed.trim() === WORD && (scopes.settings || scopes.presets || scopes.jobs))

  async function reset() {
    if (!ready) return
    busy = true
    error = ''
    try {
      await saves.flush()
      const result = await api.resetConfiguration($state.snapshot(scopes))
      app.presets = result.presets
      if (scopes.presets) drafts.write('templates', null)
      const newJobs = drafts.read<Record<string, unknown>>('new-jobs')
      if (newJobs)
        drafts.write('new-jobs', {
          ...newJobs,
          profile: '',
          templateName: null,
          encoder: null,
          container: '',
          output: [],
        })
      onreset(result.config)
      open = false
      toast.success('VideoForge reset', {
        description: `Backup saved to ${result.backup}. Import it from Configuration backup to undo.`,
        duration: 15_000,
      })
      await Promise.all([
        api.profiles().then((profiles) => {
          app.profiles = profiles
        }),
        app.loadEncoders(),
      ]).catch(() => toast.error('Reset done. Reload the page to refresh available profiles.'))
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
</script>

<section class="col-span-full space-y-3 rounded-xl border border-destructive/40 bg-card p-4" aria-label="Reset">
  <h2 class="font-medium">Reset VideoForge</h2>
  <p class="text-sm text-muted-foreground">
    Go back to the defaults from videoforge.toml. A configuration backup is saved to the data folder first.
  </p>
  <Button
    variant="outline"
    disabled={disabled || busy}
    onclick={() => {
      error = ''
      typed = ''
      scopes = { settings: true, presets: false, jobs: false }
      open = true
    }}><RotateCcwIcon />Reset…</Button
  >
</section>

<Dialog.Root
  {open}
  onOpenChange={(value) => {
    if (!busy) open = value
  }}
>
  <Dialog.Content
    class="sm:max-w-lg"
    showCloseButton={!busy}
    onEscapeKeydown={(e) => {
      if (busy) e.preventDefault()
    }}
    onInteractOutside={(e) => {
      if (busy) e.preventDefault()
    }}
  >
    <Dialog.Header>
      <Dialog.Title>Reset VideoForge</Dialog.Title>
      <Dialog.Description
        >Choose what to remove. The queue must be stopped. Installed plugins and their files, work folders, and kept job
        records stay.</Dialog.Description
      >
    </Dialog.Header>
    <div class="space-y-3 text-sm">
      <label class="flex items-start gap-2">
        <Checkbox bind:checked={scopes.settings} disabled={busy} />
        <span
          >Settings<span class="block text-xs text-muted-foreground"
            >Tool paths, folder choices, default profile, notifications, actions, plugin settings, and default subtitle
            rules. Tools then need to be found on PATH or set again.</span
          ></span
        >
      </label>
      <label class="flex items-start gap-2">
        <Checkbox bind:checked={scopes.presets} disabled={busy} />
        <span
          >Presets and templates<span class="block text-xs text-muted-foreground"
            >Templates, video and audio encoder presets, video processing presets, and default template selections.</span
          ></span
        >
      </label>
      <label class="flex items-start gap-2">
        <Checkbox bind:checked={scopes.jobs} disabled={busy} />
        <span
          >Jobs<span class="block text-xs text-muted-foreground"
            >Every job in the queue, finished or not. Not part of the backup.</span
          ></span
        >
      </label>
      <label class="block space-y-1.5">
        <span>Type <span class="font-mono font-medium">{WORD}</span> to confirm</span>
        <Input bind:value={typed} disabled={busy} autocomplete="off" spellcheck="false" />
      </label>
    </div>
    {#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (open = false)}>Cancel</Button>
      <Button variant="destructive" disabled={busy || !ready} onclick={reset}>{busy ? 'Working…' : 'Reset'}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
