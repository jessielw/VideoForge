<script lang="ts">
  import { toast } from 'svelte-sonner'
  import DownloadIcon from '@lucide/svelte/icons/download'
  import UploadIcon from '@lucide/svelte/icons/upload'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { api } from '../lib/api'
  import ImportNote from './ImportNote.svelte'
  import ImportOptions from './ImportOptions.svelte'
  import { app } from '../lib/state.svelte'
  import { downloadAudio, audioBundle, MAX_AUDIO_BYTES } from '../lib/audioTransfer'
  import { folderParts, presetLabel, type PresetDraft } from '../lib/presetDraft'
  import { templateFilename } from '../lib/templateTransfer'
  import type { ImportAction, AudioBundle, AudioPresetSettings, Preset } from '../lib/types'

  let { current, disabled = false }: { current: PresetDraft<AudioPresetSettings> | null; disabled?: boolean } = $props()
  let mode = $state<'import' | 'export' | null>(null)
  let exportSelected = $state<string[]>([])
  let busy = $state(false)
  let error = $state('')
  let bundle = $state<AudioBundle | null>(null)
  let names = $state<string[]>([])
  let actions = $state<ImportAction[]>([])
  let keepBoth = $state(false)
  let raw: unknown = null // the file read, previewed again when Keep both changes
  let selected = $state<boolean[]>([])
  const count = $derived(selected.filter(Boolean).length)
  const exportEntries = $derived(app.presets.audio.filter(entry => exportSelected.includes(entry.name)))

  const location = (entry: { group?: string[]; data: AudioPresetSettings }) => [entry.data.action, ...(entry.group ?? [])].join(' / ')
  const rate = (data: AudioPresetSettings) => data.action === 'copy' ? 'Copy' : `${data.layout ?? 'Auto channels'} / ${data.bitrate_kbps ? `${data.bitrate_kbps} kb/s` : 'default bitrate / quality'}`

  function open(next: 'import' | 'export') {
    error = ''
    bundle = null
    selected = []
    keepBoth = false
    exportSelected = app.presets.audio.map(entry => entry.name)
    mode = next
  }
  async function exportFile(entries: Preset<AudioPresetSettings>[]) {
    if (!entries.length) return
    busy = true
    error = ''
    try {
      // Snapshot Svelte proxies before the portable serializer clones them.
      const data = await api.exportAudio(audioBundle($state.snapshot(entries)))
      downloadAudio(data, templateFilename(entries.length === 1 ? presetLabel(entries[0]) : 'audio-presets'))
      toast.success(`Exported ${entries.length} audio preset${entries.length === 1 ? '' : 's'}`)
      mode = null
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      if (!mode) toast.error(error)
    } finally { busy = false }
  }
  function exportCurrent() {
    if (!current) return
    const label = current.label.trim() || `${current.data.action} settings`
    exportFile([{ name: label, label, group: folderParts(current.folder), data: current.data }])
  }
  async function readFile(file: File | undefined) {
    bundle = null
    selected = []
    error = ''
    if (!file) return
    busy = true
    try {
      if (file.size > MAX_AUDIO_BYTES) throw new Error('Audio preset files must be 5 MiB or smaller')
      let data: unknown
      try { data = JSON.parse((await file.text()).replace(/^\uFEFF/, '')) }
      catch { throw new Error('This file is not valid JSON. Choose a VideoForge audio preset export.') }
      raw = data
      await previewFile(true)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally { busy = false }
  }
  // fresh: a new file (all selected); else the same file again after Keep both changed (the selection stays)
  async function previewFile(fresh: boolean) {
    const preview = await api.previewAudio(raw, keepBoth)
    bundle = preview.bundle
    names = preview.names
    actions = preview.actions ?? []
    if (fresh) selected = names.map(() => true)
  }
  async function setKeepBoth(on: boolean) {
    keepBoth = on
    busy = true
    error = ''
    try { await previewFile(false) } catch (e) { error = e instanceof Error ? e.message : String(e) } finally { busy = false }
  }
  async function importFile() {
    if (!bundle || !count) return
    busy = true
    error = ''
    try {
      const result = await api.importAudio({ ...bundle, audio: bundle.audio.filter((_, i) => selected[i]) }, keepBoth)
      app.presets = result.presets
      toast.success(`Imported ${result.names.length} audio preset${result.names.length === 1 ? '' : 's'}`)
      mode = null
      bundle = null
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally { busy = false }
  }
</script>

<div class="grid shrink-0 grid-cols-2 gap-2">
  <Button variant="outline" size="sm" disabled={disabled || busy} onclick={() => open('import')}><UploadIcon />Import</Button>
  <Button variant="outline" size="sm" disabled={disabled || busy || !app.presets.audio.length} onclick={() => open('export')}><DownloadIcon />Export…</Button>
  <Button variant="outline" size="sm" class="col-span-2" disabled={disabled || busy || !current}
    title="Export the open audio settings, including unsaved edits" onclick={exportCurrent}><DownloadIcon />Export current settings</Button>
</div>

<Dialog.Root open={mode !== null} onOpenChange={value => { if (!value && !busy) mode = null }}>
  <Dialog.Content class="max-h-[90dvh] overflow-y-auto sm:max-w-xl" showCloseButton={!busy}
    onEscapeKeydown={e => { e.stopPropagation(); if (busy) e.preventDefault() }}
    onInteractOutside={e => { if (busy) e.preventDefault() }}>
    <Dialog.Header>
      <Dialog.Title>{mode === 'export' ? 'Export' : 'Import'} audio presets</Dialog.Title>
      <Dialog.Description>
        {#if mode === 'export'}Choose saved presets to share with their folders. Use Export current settings to include unsaved edits.
        {:else}Choose a VideoForge audio preset file. Names and folders are preserved; a preset with the same name in the same encoder and folder replaces yours, unless you keep both.{/if}
      </Dialog.Description>
    </Dialog.Header>
    {#if mode === 'export'}
      <div class="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={busy} onclick={() => (exportSelected = app.presets.audio.map(entry => entry.name))}>Select all</Button>
        <Button variant="ghost" size="sm" disabled={busy || !exportEntries.length} onclick={() => (exportSelected = [])}>Clear selection</Button>
        <span class="ml-auto text-sm text-muted-foreground" aria-live="polite">{exportEntries.length} of {app.presets.audio.length} selected</span>
      </div>
      <div class="max-h-[45vh] space-y-2 overflow-auto" role="group" aria-label="Audio presets to export">
        {#each app.presets.audio as entry (entry.name)}
          <label class="flex items-start gap-2 rounded-md border p-3 text-sm">
            <Checkbox checked={exportSelected.includes(entry.name)} disabled={busy} onCheckedChange={checked => {
              exportSelected = checked ? [...exportSelected, entry.name] : exportSelected.filter(name => name !== entry.name)
            }} />
            <span class="min-w-0 break-all">{presetLabel(entry)}<span class="block text-xs text-muted-foreground">{location(entry)}</span></span>
          </label>
        {/each}
      </div>
    {:else}
      <label class="space-y-2 text-sm">
        <span>Audio preset file (.json, up to 5 MiB)</span>
        <input class="block w-full rounded-md border p-2 text-sm" type="file" accept=".json,application/json" disabled={busy}
          onchange={e => readFile(e.currentTarget.files?.[0])} />
      </label>
      {#if bundle}
        <ImportOptions {keepBoth} actions={actions.filter((_, i) => selected[i])} disabled={busy} onchange={setKeepBoth} />
        <div class="max-h-[45vh] space-y-2 overflow-auto" role="group" aria-label="Audio presets to import">
          {#each bundle.audio as entry, i (i)}
            <label class="flex items-start gap-2 rounded-md border p-3 text-sm">
              <Checkbox checked={selected[i]} disabled={busy} onCheckedChange={checked => (selected[i] = checked)} />
              <span class="min-w-0 break-all">{entry.label}<ImportNote action={actions[i]} name={names[i]} original={entry.label} />
                <span class="block text-xs text-muted-foreground">{location(entry)} / {rate(entry.data)}{entry.data.title ? ` / Title: ${entry.data.title}` : ""}</span>
              </span>
            </label>
          {/each}
        </div>
        {#if actions.includes('copy')}<p class="text-xs text-muted-foreground">Copy numbers may change if you select fewer presets or another browser saves a matching name.</p>{/if}
      {/if}
    {/if}
    {#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (mode = null)}>Cancel</Button>
      {#if mode === 'export'}
        <Button disabled={busy || !exportEntries.length} onclick={() => exportFile(exportEntries)}><DownloadIcon />{busy ? 'Exporting…' : `Export ${exportEntries.length} selected`}</Button>
      {:else}
        <Button disabled={busy || !bundle || !count} onclick={importFile}>{busy ? (bundle ? 'Importing…' : 'Reading…') : `Import${count ? ` ${count}` : ''}`}</Button>
      {/if}
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
