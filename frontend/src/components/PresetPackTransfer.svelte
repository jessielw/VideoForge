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
  import { presetPack } from '../lib/presetPack'
  import { templateScripts } from '../lib/templateTransfer'
  import type { PresetKind, PresetPack, PresetPackPreview } from '../lib/types'

  let { disabled = false }: { disabled?: boolean } = $props()
  const labels: [PresetKind, string][] = [['template', 'Templates'], ['encoder', 'Video encoder presets'], ['audio', 'Audio encoder presets'], ['video', 'Video processing presets']]
  const MAX_BYTES = 20 * 1024 * 1024
  let mode = $state<'export' | 'import' | null>(null)
  let busy = $state(false)
  let error = $state('')
  let preview = $state<PresetPackPreview | null>(null)
  let selected = $state<string[]>([])
  const count = $derived(selected.length)
  const available = $derived(labels.reduce((n, [kind]) => n + app.presets[kind].length, 0))
  const scripts = $derived(preview ? [
    ...preview.bundle.presets.template.flatMap(entry => templateScripts(entry.data).map(script => ({ name: `${entry.name} / ${script.name}`, script: script.script }))),
    ...preview.bundle.presets.video.flatMap(entry => templateScripts({ video: entry.data }).map(script => ({ name: `${entry.name} / ${script.name}`, script: script.script }))),
  ] : [])

  function toggle(key: string, on: boolean) { selected = on ? [...new Set([...selected, key])] : selected.filter(value => value !== key) }
  function keys() {
    return mode === 'export' ? labels.flatMap(([kind]) => app.presets[kind].map(entry => `${kind}:${entry.name}`))
      : preview ? labels.flatMap(([kind]) => preview!.bundle.presets[kind].map((_, i) => `${kind}:${i}`)) : []
  }
  function open(next: 'export' | 'import') {
    mode = next
    error = ''
    preview = null
    selected = next === 'export' ? keys() : []
  }
  async function exportFile() {
    busy = true
    error = ''
    try {
      await saves.flush()
      const choose = <T extends { name: string }>(kind: PresetKind, entries: T[]) => entries.filter(entry => selected.includes(`${kind}:${entry.name}`))
      const bundle = await api.exportPresetPack(presetPack($state.snapshot({
        template: choose('template', app.presets.template), encoder: choose('encoder', app.presets.encoder),
        audio: choose('audio', app.presets.audio), video: choose('video', app.presets.video),
      })))
      const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' })
      if (blob.size > MAX_BYTES) throw new Error('This preset pack exceeds 20 MiB. Select fewer presets.')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'videoforge-presets.json'
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
      toast.success('Preset pack exported')
      mode = null
    } catch (e) { error = e instanceof Error ? e.message : String(e) }
    finally { busy = false }
  }
  async function readFile(file: File | undefined) {
    preview = null
    selected = []
    error = ''
    if (!file) return
    busy = true
    try {
      if (file.size > MAX_BYTES) throw new Error('Preset packs must be 20 MiB or smaller')
      let data: unknown
      try { data = JSON.parse((await file.text()).replace(/^\uFEFF/, '')) }
      catch { throw new Error('This file is not valid JSON. Choose a VideoForge preset pack.') }
      preview = await api.previewPresetPack(data)
      selected = keys()
    } catch (e) { error = e instanceof Error ? e.message : String(e) }
    finally { busy = false }
  }
  async function importFile() {
    if (!preview || !count) return
    busy = true
    error = ''
    try {
      await saves.flush()
      const choose = <T,>(kind: PresetKind, entries: T[]) => entries.filter((_, i) => selected.includes(`${kind}:${i}`))
      const libraries = preview.bundle.presets
      const bundle: PresetPack = { ...preview.bundle, presets: {
        template: choose('template', libraries.template), encoder: choose('encoder', libraries.encoder),
        audio: choose('audio', libraries.audio), video: choose('video', libraries.video),
      } }
      const result = await api.importPresetPack(bundle)
      app.presets = result.presets
      toast.success(`Imported ${Object.values(result.names).flat().length} presets`)
      mode = null
    } catch (e) { error = e instanceof Error ? e.message : String(e) }
    finally { busy = false }
  }
</script>

<section class="col-span-full space-y-3 rounded-xl border bg-card p-4" aria-label="Preset sharing">
  <h2 class="font-medium">Preset sharing</h2>
  <p class="text-sm text-muted-foreground">Share selected templates and video or audio encoder presets with your group in one preset pack.</p>
  <p class="text-xs text-muted-foreground">App settings, tool paths, folder choices, notification URLs, actions, and plugin settings are excluded. Review any custom scripts and extra arguments you added before sharing.</p>
  <div class="flex flex-wrap gap-2">
    <Button variant="outline" disabled={disabled || busy || !available} onclick={() => open('export')}><DownloadIcon />Export presets…</Button>
    <Button variant="outline" disabled={disabled || busy} onclick={() => open('import')}><UploadIcon />Import presets…</Button>
  </div>
</section>

<Dialog.Root open={mode !== null} onOpenChange={value => { if (!value && !busy) mode = null }}>
  <Dialog.Content class="max-h-[90dvh] overflow-y-auto sm:max-w-2xl" showCloseButton={!busy}
    onEscapeKeydown={e => { if (busy) e.preventDefault() }} onInteractOutside={e => { if (busy) e.preventDefault() }}>
    <Dialog.Header>
      <Dialog.Title>{mode === 'export' ? 'Export' : 'Import'} preset pack</Dialog.Title>
      <Dialog.Description>
        {#if mode === 'export'}Choose the templates and presets to share. The file contains only their settings, display names, and folders.
        {:else}Choose a VideoForge preset pack. Imported presets are added to your library; matching names get numbered copies. Your app settings and default selections stay the same.{/if}
      </Dialog.Description>
    </Dialog.Header>
    {#if mode === 'import'}
      <label class="space-y-2 text-sm"><span>Preset pack (.json, up to 20 MiB)</span>
        <input class="block w-full rounded-md border p-2 text-sm" type="file" accept=".json,application/json" disabled={busy} onchange={e => readFile(e.currentTarget.files?.[0])} />
      </label>
    {/if}
    {#if mode === 'export' || preview}
      <div class="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={busy} onclick={() => (selected = keys())}>Select all</Button>
        <Button variant="ghost" size="sm" disabled={busy || !count} onclick={() => (selected = [])}>Clear selection</Button>
        <span class="ml-auto text-sm text-muted-foreground" aria-live="polite">{count} selected</span>
      </div>
      <div class="max-h-[40vh] space-y-4 overflow-auto">
        {#each labels as [kind, label] (kind)}
          {@const entries = mode === 'export' ? app.presets[kind] : preview!.bundle.presets[kind]}
          {#if entries.length}
            <fieldset class="space-y-2"><legend class="mb-2 text-sm font-medium">{label}</legend>
              {#each entries as entry, i (i)}
                {@const name = 'label' in entry ? entry.label ?? ('name' in entry ? entry.name : '') : entry.name}
                {@const key = `${kind}:${mode === 'export' && 'name' in entry ? entry.name : i}`}
                <label class="flex items-start gap-2 rounded-md border p-2 text-sm">
                  <Checkbox checked={selected.includes(key)} disabled={busy} onCheckedChange={on => toggle(key, on)} />
                  <span class="min-w-0 break-all">{name}{#if mode === 'import' && preview?.names[kind][i] !== name}<span class="text-muted-foreground">{' → '}{preview?.names[kind][i]}</span>{/if}
                    {#if 'group' in entry && entry.group?.length}<span class="block text-xs text-muted-foreground">{entry.group.join(' / ')}</span>{/if}
                  </span>
                </label>
              {/each}
            </fieldset>
          {/if}
        {/each}
      </div>
      {#if mode === 'import'}
        <p class="text-xs text-muted-foreground">Copy numbers may change with your selection or other library edits. Tools and plugins referenced by presets must be available on this computer.</p>
        {#if scripts.length}<details class="space-y-2 text-xs"><summary class="cursor-pointer font-medium">Review included scripts ({scripts.length})</summary>
          {#each scripts as script, i (i)}<p class="font-medium">{script.name}</p><pre class="max-h-40 overflow-auto rounded bg-muted p-2">{script.script}</pre>{/each}
        </details>{/if}
      {/if}
    {/if}
    {#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (mode = null)}>Cancel</Button>
      <Button disabled={busy || !count} onclick={mode === 'export' ? exportFile : importFile}>{busy ? 'Working…' : `${mode === 'export' ? 'Export' : 'Import'} ${count} selected`}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
