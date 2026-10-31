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
  import { downloadEncoders, encoderBundle, MAX_ENCODER_BYTES } from '../lib/encoderTransfer'
  import { folderParts, presetLabel, type PresetDraft } from '../lib/presetDraft'
  import { templateFilename } from '../lib/templateTransfer'
  import type { ImportAction, EncoderBundle, EncoderSettings, Preset } from '../lib/types'
  import Tip from './Tip.svelte'

  let { current, disabled = false }: { current: PresetDraft<EncoderSettings> | null; disabled?: boolean } = $props()
  let mode = $state<'import' | 'export' | null>(null)
  let exportSelected = $state<string[]>([])
  let busy = $state(false)
  let error = $state('')
  let bundle = $state<EncoderBundle | null>(null)
  let names = $state<string[]>([])
  let actions = $state<ImportAction[]>([])
  let keepBoth = $state(false)
  let raw: unknown = null // the file read, previewed again when Keep both changes
  let selected = $state<boolean[]>([])
  const count = $derived(selected.filter(Boolean).length)
  const exportEntries = $derived(app.presets.encoder.filter((entry) => exportSelected.includes(entry.name)))

  const location = (entry: { group?: string[]; data: EncoderSettings }) =>
    [entry.data.encoder, ...(entry.group ?? [])].join(' / ')
  const rate = (data: EncoderSettings) =>
    data.rate_control === 'crf'
      ? `CRF ${data.crf}`
      : `${data.rate_control === '2pass' ? 'Two pass · ' : ''}${data.rate_control === '2pass' && data.target_mb !== null ? `${data.target_mb} MB` : `${data.bitrate_kbps} kb/s`}`

  function open(next: 'import' | 'export') {
    error = ''
    bundle = null
    selected = []
    keepBoth = false
    exportSelected = app.presets.encoder.map((entry) => entry.name)
    mode = next
  }
  async function exportFile(entries: Preset<EncoderSettings>[]) {
    if (!entries.length) return
    busy = true
    error = ''
    try {
      // Snapshot Svelte proxies before the portable serializer clones them.
      const data = await api.exportEncoders(encoderBundle($state.snapshot(entries)))
      downloadEncoders(data, templateFilename(entries.length === 1 ? presetLabel(entries[0]) : 'encoder-presets'))
      toast.success(`Exported ${entries.length} encoder preset${entries.length === 1 ? '' : 's'}`)
      mode = null
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      if (!mode) toast.error(error)
    } finally {
      busy = false
    }
  }
  function exportCurrent() {
    if (!current) return
    const label = current.label.trim() || `${current.data.encoder} settings`
    exportFile([{ name: label, label, group: folderParts(current.folder), data: current.data }])
  }
  async function readFile(file: File | undefined) {
    bundle = null
    selected = []
    error = ''
    if (!file) return
    busy = true
    try {
      if (file.size > MAX_ENCODER_BYTES) throw new Error('Encoder preset files must be 5 MiB or smaller')
      let data: unknown
      try {
        data = JSON.parse((await file.text()).replace(/^\uFEFF/, ''))
      } catch {
        throw new Error('This file is not valid JSON. Choose a VideoForge encoder preset export.')
      }
      raw = data
      await previewFile(true)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  // fresh: a new file (all selected); else the same file again after Keep both changed (the selection stays)
  async function previewFile(fresh: boolean) {
    const preview = await api.previewEncoders(raw, keepBoth)
    bundle = preview.bundle
    names = preview.names
    actions = preview.actions ?? []
    if (fresh) selected = names.map(() => true)
  }
  async function setKeepBoth(on: boolean) {
    keepBoth = on
    busy = true
    error = ''
    try {
      await previewFile(false)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  async function importFile() {
    if (!bundle || !count) return
    busy = true
    error = ''
    try {
      const result = await api.importEncoders(
        { ...bundle, encoders: bundle.encoders.filter((_, i) => selected[i]) },
        keepBoth,
      )
      app.presets = result.presets
      toast.success(`Imported ${result.names.length} encoder preset${result.names.length === 1 ? '' : 's'}`)
      mode = null
      bundle = null
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
</script>

<div class="grid shrink-0 grid-cols-2 gap-2">
  <Button variant="outline" size="sm" disabled={disabled || busy} onclick={() => open('import')}
    ><UploadIcon />Import</Button
  >
  <Button
    variant="outline"
    size="sm"
    disabled={disabled || busy || !app.presets.encoder.length}
    onclick={() => open('export')}><DownloadIcon />Export…</Button
  >
  <Tip class="col-span-2 grid" text="Export the open encoder settings, including unsaved edits">
    <Button variant="outline" size="sm" disabled={disabled || busy || !current} onclick={exportCurrent}
      ><DownloadIcon />Export current settings</Button
    >
  </Tip>
</div>

<Dialog.Root
  open={mode !== null}
  onOpenChange={(value) => {
    if (!value && !busy) mode = null
  }}
>
  <Dialog.Content
    class="max-h-[90dvh] overflow-y-auto sm:max-w-xl"
    showCloseButton={!busy}
    onEscapeKeydown={(e) => {
      e.stopPropagation()
      if (busy) e.preventDefault()
    }}
    onInteractOutside={(e) => {
      if (busy) e.preventDefault()
    }}
  >
    <Dialog.Header>
      <Dialog.Title>{mode === 'export' ? 'Export' : 'Import'} encoder presets</Dialog.Title>
      <Dialog.Description>
        {#if mode === 'export'}Choose saved presets to share with their folders. Use Export current settings to include
          unsaved edits.
        {:else}Choose a VideoForge encoder preset file. Names and folders are preserved; a preset with the same name in
          the same encoder and folder replaces yours, unless you keep both.{/if}
      </Dialog.Description>
    </Dialog.Header>
    {#if mode === 'export'}
      <div class="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onclick={() => (exportSelected = app.presets.encoder.map((entry) => entry.name))}>Select all</Button
        >
        <Button variant="ghost" size="sm" disabled={busy || !exportEntries.length} onclick={() => (exportSelected = [])}
          >Clear selection</Button
        >
        <span class="ml-auto text-sm text-muted-foreground" aria-live="polite"
          >{exportEntries.length} of {app.presets.encoder.length} selected</span
        >
      </div>
      <div class="max-h-[45vh] space-y-2 overflow-auto" role="group" aria-label="Encoder presets to export">
        {#each app.presets.encoder as entry (entry.name)}
          <label class="flex items-start gap-2 rounded-md border p-3 text-sm">
            <Checkbox
              checked={exportSelected.includes(entry.name)}
              disabled={busy}
              onCheckedChange={(checked) => {
                exportSelected = checked
                  ? [...exportSelected, entry.name]
                  : exportSelected.filter((name) => name !== entry.name)
              }}
            />
            <span class="min-w-0 break-all"
              >{presetLabel(entry)}<span class="block text-xs text-muted-foreground">{location(entry)}</span></span
            >
          </label>
        {/each}
      </div>
    {:else}
      <label class="space-y-2 text-sm">
        <span>Encoder preset file (.json, up to 5 MiB)</span>
        <input
          class="block w-full rounded-md border p-2 text-sm"
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onchange={(e) => readFile(e.currentTarget.files?.[0])}
        />
      </label>
      {#if bundle}
        <ImportOptions
          {keepBoth}
          actions={actions.filter((_, i) => selected[i])}
          disabled={busy}
          onchange={setKeepBoth}
        />
        <div class="max-h-[45vh] space-y-2 overflow-auto" role="group" aria-label="Encoder presets to import">
          {#each bundle.encoders as entry, i (i)}
            <label class="flex items-start gap-2 rounded-md border p-3 text-sm">
              <Checkbox checked={selected[i]} disabled={busy} onCheckedChange={(checked) => (selected[i] = checked)} />
              <span class="min-w-0 break-all"
                >{entry.label}<ImportNote action={actions[i]} name={names[i]} original={entry.label} />
                <span class="block text-xs text-muted-foreground"
                  >{location(entry)} · {entry.data.depth}-bit · {rate(entry.data)} · {entry.data.preset ||
                    'default speed'}</span
                >
              </span>
            </label>
          {/each}
        </div>
        {#if actions.includes('copy')}<p class="text-xs text-muted-foreground">
            Copy numbers may change if you select fewer presets or another browser saves a matching name.
          </p>{/if}
      {/if}
    {/if}
    {#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (mode = null)}>Cancel</Button>
      {#if mode === 'export'}
        <Button disabled={busy || !exportEntries.length} onclick={() => exportFile(exportEntries)}
          ><DownloadIcon />{busy ? 'Exporting…' : `Export ${exportEntries.length} selected`}</Button
        >
      {:else}
        <Button disabled={busy || !bundle || !count} onclick={importFile}
          >{busy ? (bundle ? 'Importing…' : 'Reading…') : `Import${count ? ` ${count}` : ''}`}</Button
        >
      {/if}
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
