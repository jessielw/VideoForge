<script lang="ts">
  import { toast } from 'svelte-sonner'
  import DownloadIcon from '@lucide/svelte/icons/download'
  import UploadIcon from '@lucide/svelte/icons/upload'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { saves } from '../lib/saves'
  import { forgetConfigurationDrafts } from '../lib/drafts'
  import { templateScripts } from '../lib/templateTransfer'
  import type { ConfigState, ConfigurationBundle, ConfigurationPreview, PresetKind } from '../lib/types'

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
  // Where it goes: NEW (a new profile, named newName) or a profile's id; switchTo: make it the active one
  const NEW = ''
  let target = $state(NEW)
  let newName = $state('')
  let switchTo = $state(true)
  const replaces = $derived(target !== NEW)
  const applies = $derived(target === app.profiles.active || (switchTo && !app.queue.running))
  const targetName = $derived(app.profiles.profiles.find((p) => p.id === target)?.name ?? newName.trim())
  const currentCounts = $derived(
    preview && replaces ? preview.profile_counts[target] : { template: 0, encoder: 0, audio: 0, video: 0 },
  )
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
  // The backup's profile name (or the file's), numbered if a profile already has it
  function suggestedName(bundle: ConfigurationBundle): string {
    const base = (bundle.profile || filename.replace(/\.json$/i, '') || 'Imported').slice(0, 80)
    const taken = new Set(app.profiles.profiles.map((p) => p.name.toLowerCase()))
    let name = base
    for (let n = 2; taken.has(name.toLowerCase()); n++) name = `${base.slice(0, 80 - ` (${n})`.length)} (${n})`
    return name
  }
  async function readFile(file: File | undefined) {
    preview = null
    confirmed = false
    target = NEW
    switchTo = true
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
      newName = suggestedName(preview.bundle)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  async function importFile() {
    if (!preview || (replaces && !confirmed) || (!replaces && !newName.trim())) return
    busy = true
    error = ''
    try {
      await saves.flush()
      const into = replaces ? { profile: target } : { new: newName.trim() }
      const result = await api.importConfiguration(preview.bundle, into, applies && target !== app.profiles.active)
      app.profiles = { profiles: result.profiles, active: result.active }
      const name = result.profiles.find((p) => p.id === result.profile)?.name ?? ''
      open = false
      if (result.profile !== result.active) {
        toast.success(`Configuration imported into ${name}`, { description: 'Switch to it under Profiles to use it.' })
        return
      }
      app.presets = result.presets
      forgetConfigurationDrafts()
      onimported(result.config)
      toast.success('Configuration imported', { description: `Profile: ${name}` })
      await Promise.all([
        api.ruleSets().then((ruleSets) => {
          app.ruleSets = ruleSets
        }),
        app.loadEncoders(),
      ]).catch(() => toast.error('Configuration imported. Reload the page to refresh available rule sets.'))
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
    Save the {app.activeProfile ? `${app.activeProfile} profile's` : "active profile's"} settings, templates, video and audio
    encoder presets, video processing presets, and template defaults in one file, or restore one into a new or existing profile.
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
        >Restore a VideoForge backup into a new profile, or replace an existing profile's saved settings and preset
        libraries, including default template selections. Existing jobs keep their settings.</Dialog.Description
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
      <div class="grid gap-3 text-sm sm:grid-cols-2">
        <label class="grid gap-1.5">
          <span>Import into</span>
          <NativeSelect bind:value={target} disabled={busy} onchange={() => (confirmed = false)}>
            <option value={NEW}>A new profile</option>
            {#each app.profiles.profiles as profile (profile.id)}
              <option value={profile.id}>{profile.name}{profile.id === app.profiles.active ? ' (active)' : ''}</option>
            {/each}
          </NativeSelect>
        </label>
        {#if !replaces}
          <label class="grid gap-1.5">
            <span>New profile's name</span>
            <Input bind:value={newName} disabled={busy} maxlength={80} autocomplete="off" />
          </label>
        {/if}
      </div>
      {#if target !== app.profiles.active}
        <label class="flex items-start gap-2 text-sm">
          <Checkbox bind:checked={switchTo} disabled={busy || app.queue.running} />
          <span
            >Switch to it after importing<span class="block text-xs text-muted-foreground"
              >{app.queue.running
                ? 'Stop the queue to switch: its jobs use the active profile’s settings.'
                : 'Its settings, templates and presets are used at once.'}</span
            ></span
          >
        </label>
      {/if}
      <table class="w-full text-left text-sm">
        <thead
          ><tr class="border-b"
            ><th class="py-2">Preset library</th><th>{replaces ? targetName : 'New profile'}</th><th>In backup</th></tr
          ></thead
        >
        <tbody
          >{#each labels as [kind, label] (kind)}<tr class="border-b"
              ><td class="py-2">{label}</td><td>{currentCounts[kind]}</td><td>{preview.counts[kind]}</td></tr
            >{/each}</tbody
        >
      </table>
      <p class="text-xs text-muted-foreground">
        {preview.bundle.settings.notifications.length} notification destinations · {preview.bundle.settings.actions
          .length} actions · {Object.keys(preview.bundle.template_defaults).length} default template selections
      </p>
      {#each preview.warnings as warning (warning)}<p class="text-xs text-warning">{warning}</p>{/each}
      {#if scripts.length || preview.bundle.settings.actions.length}
        <details class="min-w-0 space-y-2 text-xs">
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
      {#if replaces}
        <label class="flex items-start gap-2 rounded-md border border-warning/50 p-3 text-sm">
          <Checkbox bind:checked={confirmed} disabled={busy} />
          Replace {targetName}'s configuration and preset libraries with this backup. I have exported anything I want to
          keep.
        </label>
      {/if}
    {/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (open = false)}>Cancel</Button>
      <Button disabled={busy || !preview || (replaces ? !confirmed : !newName.trim())} onclick={importFile}
        >{busy ? 'Working…' : 'Import configuration'}</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
