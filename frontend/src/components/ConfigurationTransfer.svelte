<script lang="ts">
  import { toast } from 'svelte-sonner'
  import DownloadIcon from '@lucide/svelte/icons/download'
  import UploadIcon from '@lucide/svelte/icons/upload'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { saves } from '../lib/saves'
  import { drafts } from '../lib/drafts'
  import { templateScripts } from '../lib/templateTransfer'
  import type { ConfigState, ConfigurationPreview, PresetKind } from '../lib/types'

  let { disabled = false, onimported }: { disabled?: boolean; onimported: (config: ConfigState) => void } = $props()
  const MAX_BYTES = 20 * 1024 * 1024
  const labels: [PresetKind, string][] = [
    ['template', 'Templates'],
    ['encoder', 'Video encoder presets'],
    ['audio', 'Audio encoder presets'],
    ['video', 'Video processing presets'],
  ]
  let open = $state(false)
  let busy = $state(false)
  let error = $state('')
  let filename = $state('')
  let preview = $state<ConfigurationPreview | null>(null)
  let confirmed = $state(false)
  const scripts = $derived(
    preview
      ? [
          ...preview.bundle.presets.template.flatMap((entry) =>
            templateScripts(entry.data).map((script) => ({
              name: `${entry.name} / ${script.name}`,
              script: script.script,
            })),
          ),
          ...preview.bundle.presets.video.flatMap((entry) =>
            templateScripts({ video: entry.data }).map((script) => ({
              name: `${entry.name} / ${script.name}`,
              script: script.script,
            })),
          ),
        ]
      : [],
  )

  async function exportFile() {
    busy = true
    error = ''
    try {
      await saves.flush()
      const bundle = await api.exportConfiguration()
      const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' })
      if (blob.size > MAX_BYTES) throw new Error('This configuration exceeds the 20 MiB file limit.')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `videoforge-configuration-${new Date().toISOString().slice(0, 10)}.json`
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
      toast.success('Configuration exported')
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  async function readFile(file: File | undefined) {
    preview = null
    confirmed = false
    error = ''
    filename = file?.name ?? ''
    if (!file) return
    busy = true
    try {
      if (file.size > MAX_BYTES) throw new Error('Configuration files must be 20 MiB or smaller')
      let data: unknown
      try {
        data = JSON.parse((await file.text()).replace(/^\uFEFF/, ''))
      } catch {
        throw new Error('This file is not valid JSON. Choose a VideoForge configuration export.')
      }
      await saves.flush()
      preview = await api.previewConfiguration(data)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  async function importFile() {
    if (!preview || !confirmed) return
    busy = true
    error = ''
    try {
      await saves.flush()
      const result = await api.importConfiguration(preview.bundle)
      app.presets = result.presets
      drafts.write('templates', null)
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
      onimported(result.config)
      toast.success('Configuration imported')
      open = false
      await Promise.all([
        api.profiles().then((profiles) => {
          app.profiles = profiles
        }),
        app.loadEncoders(),
      ]).catch(() => toast.error('Configuration imported. Reload the page to refresh available profiles.'))
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
</script>

<section class="col-span-full space-y-3 rounded-xl border bg-card p-4" aria-label="Configuration backup">
  <h2 class="font-medium">Configuration backup</h2>
  <p class="text-sm text-muted-foreground">
    Save or restore app settings, templates, video and audio encoder presets, video processing presets, and template
    defaults in one file.
  </p>
  <p class="text-xs text-muted-foreground">
    Includes tool paths, folder choices, notifications, actions, and plugin settings. Notification URLs, action targets,
    and plugin settings may include credentials. Use Preset sharing for group distribution. Jobs, media, installed
    tools, and plugin files are separate.
  </p>
  <div class="flex flex-wrap gap-2">
    <Button variant="outline" disabled={disabled || busy} onclick={exportFile}
      ><DownloadIcon />Export configuration</Button
    >
    <Button
      variant="outline"
      disabled={disabled || busy}
      onclick={() => {
        preview = null
        error = ''
        filename = ''
        confirmed = false
        open = true
      }}><UploadIcon />Import configuration…</Button
    >
  </div>
  {#if error && !open}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
</section>

<Dialog.Root
  {open}
  onOpenChange={(value) => {
    if (!busy) open = value
  }}
>
  <Dialog.Content
    class="max-h-[90dvh] overflow-y-auto sm:max-w-2xl"
    showCloseButton={!busy}
    onEscapeKeydown={(e) => {
      if (busy) e.preventDefault()
    }}
    onInteractOutside={(e) => {
      if (busy) e.preventDefault()
    }}
  >
    <Dialog.Header>
      <Dialog.Title>Import configuration</Dialog.Title>
      <Dialog.Description
        >Restore the configuration from a VideoForge backup. This replaces your saved settings and preset libraries,
        including default template selections. Existing jobs keep their settings.</Dialog.Description
      >
    </Dialog.Header>
    <label class="space-y-2 text-sm">
      <span>Configuration file (.json, up to 20 MiB)</span>
      <input
        class="block w-full rounded-md border p-2 text-sm"
        type="file"
        accept=".json,application/json"
        disabled={busy}
        onchange={(e) => readFile(e.currentTarget.files?.[0])}
      />
    </label>
    {#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
    {#if preview}
      <p class="break-all text-sm font-medium">{filename}</p>
      <table class="w-full text-left text-sm">
        <thead><tr class="border-b"><th class="py-2">Preset library</th><th>Current</th><th>In backup</th></tr></thead>
        <tbody
          >{#each labels as [kind, label] (kind)}<tr class="border-b"
              ><td class="py-2">{label}</td><td>{preview.current_counts[kind]}</td><td>{preview.counts[kind]}</td></tr
            >{/each}</tbody
        >
      </table>
      <p class="text-xs text-muted-foreground">
        {preview.bundle.settings.notifications.length} notification destinations · {preview.bundle.settings.actions
          .length} actions · {Object.keys(preview.bundle.template_defaults).length} default template selections
      </p>
      {#each preview.warnings as warning (warning)}<p class="text-xs text-warning">{warning}</p>{/each}
      {#if scripts.length || preview.bundle.settings.actions.length}
        <details class="space-y-2 text-xs">
          <summary class="cursor-pointer font-medium">Review included scripts and actions</summary>
          <p class="text-muted-foreground">
            Scripts run when processing video. Enabled actions run on their selected job or queue events. Command
            actions are {preview.bundle.application.allow_commands ? 'allowed' : 'disabled'} in this backup.
          </p>
          {#each scripts as script, i (i)}<p class="font-medium">{script.name}</p>
            <pre class="max-h-40 overflow-auto rounded bg-muted p-2">{script.script}</pre>{/each}
          {#each preview.bundle.settings.actions as action, i (i)}<p class="font-medium">
              {action.name} · {action.kind} · {action.enabled ? 'enabled' : 'disabled'}
            </p>
            <pre class="max-h-40 overflow-auto rounded bg-muted p-2">{action.target}</pre>{/each}
        </details>
      {/if}
      <label class="flex items-start gap-2 rounded-md border border-warning/50 p-3 text-sm">
        <Checkbox bind:checked={confirmed} disabled={busy} />
        Replace my configuration and preset libraries with this backup. I have exported anything I want to keep.
      </label>
    {/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (open = false)}>Cancel</Button>
      <Button disabled={busy || !preview || !confirmed} onclick={importFile}
        >{busy ? 'Working…' : 'Import configuration'}</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
