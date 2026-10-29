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
  import {
    downloadTemplates,
    MAX_TEMPLATE_BYTES,
    templateBundle,
    templateFilename,
    templateScripts,
  } from '../lib/templateTransfer'
  import type { ImportAction, Template, TemplateBundle } from '../lib/types'

  let { current, disabled = false }: { current: { name: string; data: Template } | null; disabled?: boolean } = $props()
  let open = $state(false)
  let exportOpen = $state(false)
  let exportSelected = $state<string[]>([])
  let busy = $state(false)
  let error = $state('')
  let filename = $state('')
  let bundle = $state<TemplateBundle | null>(null)
  let names = $state<string[]>([])
  let actions = $state<ImportAction[]>([])
  let keepBoth = $state(false)
  let raw: unknown = null // the file read, previewed again when Keep both changes
  let selected = $state<boolean[]>([])
  const count = $derived(selected.filter(Boolean).length)
  const exportEntries = $derived(app.presets.template.filter((entry) => exportSelected.includes(entry.name)))

  async function exportFile(entries: TemplateBundle['templates']) {
    if (!entries.length) return
    busy = true
    error = ''
    try {
      const data = await api.exportTemplates(templateBundle(entries))
      downloadTemplates(data, templateFilename(entries.length === 1 ? entries[0].name : 'templates'))
      toast.success(`Exported ${entries.length} template${entries.length === 1 ? '' : 's'}`)
      exportOpen = false
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      if (!exportOpen) toast.error(error)
    } finally {
      busy = false
    }
  }

  async function readFile(file: File | undefined) {
    bundle = null
    selected = []
    error = ''
    filename = file?.name ?? ''
    if (!file) return
    busy = true
    try {
      if (file.size > MAX_TEMPLATE_BYTES) throw new Error('Template files must be 5 MiB or smaller')
      let data: unknown
      try {
        data = JSON.parse((await file.text()).replace(/^\uFEFF/, ''))
      } catch {
        throw new Error('This file is not valid JSON. Choose a VideoForge template export.')
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
    const preview = await api.previewTemplates(raw, keepBoth)
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
      const result = await api.importTemplates(templateBundle(bundle.templates.filter((_, i) => selected[i])), keepBoth)
      app.presets = result.presets
      toast.success(`Imported ${result.names.length} template${result.names.length === 1 ? '' : 's'}`)
      open = false
      bundle = null
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
</script>

<div class="grid grid-cols-2 gap-2">
  <Button
    variant="outline"
    size="sm"
    disabled={disabled || busy}
    onclick={() => {
      bundle = null
      selected = []
      filename = ''
      error = ''
      keepBoth = false
      open = true
    }}><UploadIcon />Import</Button
  >
  <Button
    variant="outline"
    size="sm"
    disabled={disabled || busy || !app.presets.template.length}
    title="Choose saved templates to export"
    onclick={() => {
      exportSelected = app.presets.template.map((entry) => entry.name)
      error = ''
      exportOpen = true
    }}><DownloadIcon />Export…</Button
  >
  <Button
    variant="outline"
    size="sm"
    class="col-span-2"
    disabled={disabled || busy || !current?.name.trim()}
    title="Export the open template, including unsaved edits"
    onclick={() => exportFile(current ? [current] : [])}><DownloadIcon />Export current template</Button
  >
</div>

<Dialog.Root
  open={exportOpen}
  onOpenChange={(value) => {
    if (!busy) exportOpen = value
  }}
>
  <Dialog.Content
    class="max-h-[90dvh] overflow-y-auto sm:max-w-xl"
    showCloseButton={!busy}
    onEscapeKeydown={(e) => {
      if (busy) e.preventDefault()
    }}
    onInteractOutside={(e) => {
      if (busy) e.preventDefault()
    }}
  >
    <Dialog.Header>
      <Dialog.Title>Export templates</Dialog.Title>
      <Dialog.Description
        >Choose saved templates to share in one file. Save any editor changes first, or use Export current template to
        include unsaved edits.</Dialog.Description
      >
    </Dialog.Header>
    <div class="flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        onclick={() => (exportSelected = app.presets.template.map((entry) => entry.name))}>Select all</Button
      >
      <Button variant="ghost" size="sm" disabled={busy || !exportEntries.length} onclick={() => (exportSelected = [])}
        >Clear selection</Button
      >
      <span class="ml-auto text-sm text-muted-foreground" aria-live="polite"
        >{exportEntries.length} of {app.presets.template.length} selected</span
      >
    </div>
    <div class="max-h-[45vh] space-y-2 overflow-auto" role="group" aria-label="Templates to export">
      {#each app.presets.template as entry (entry.name)}
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
          <span class="min-w-0 break-all">{entry.name}</span>
        </label>
      {/each}
    </div>
    {#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (exportOpen = false)}>Cancel</Button>
      <Button disabled={busy || !exportEntries.length} onclick={() => exportFile(exportEntries)}>
        <DownloadIcon />{busy ? 'Exporting…' : `Export ${exportEntries.length} selected`}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

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
      <Dialog.Title>Import templates</Dialog.Title>
      <Dialog.Description
        >Choose a VideoForge template file. A template with the same name replaces yours, and stays a default if it was
        one, unless you keep both. Built-in defaults are never replaced.</Dialog.Description
      >
    </Dialog.Header>
    <label class="space-y-2 text-sm">
      <span>Template file (.json, up to 5 MiB)</span>
      <input
        class="block w-full rounded-md border p-2 text-sm"
        type="file"
        accept=".json,application/json"
        disabled={busy}
        onchange={(e) => readFile(e.currentTarget.files?.[0])}
      />
    </label>
    {#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
    {#if bundle}
      <div class="space-y-3">
        <p class="break-all text-sm text-muted-foreground">
          {filename}: {bundle.templates.length} template{bundle.templates.length === 1 ? '' : 's'}
        </p>
        <ImportOptions
          {keepBoth}
          actions={actions.filter((_, i) => selected[i])}
          disabled={busy}
          onchange={setKeepBoth}
        />
        <p class="text-xs text-muted-foreground">
          Tools, plugins and files referenced by scripts must be available on this computer. Review included Python
          before using it; scripts run when processing video.
        </p>
        <div class="max-h-[45vh] space-y-2 overflow-auto">
          {#each bundle.templates as entry, i (i)}
            {@const scripts = templateScripts(entry.data)}
            <div class="space-y-2 rounded-md border p-3">
              <label class="flex items-start gap-2 text-sm font-medium">
                <Checkbox checked={selected[i]} disabled={busy} onCheckedChange={(v) => (selected[i] = v)} />
                <span class="break-all"
                  >{entry.name}<ImportNote action={actions[i]} name={names[i]} original={entry.name} /></span
                >
              </label>
              <p class="text-xs text-muted-foreground">
                {entry.data.encoder.encoder} · {entry.data.mux.container.toUpperCase()} · Crop: {entry.data
                  .crop_mode}{entry.data.audio ? ' · Audio' : ''}{entry.data.subs ? ' · Subtitles' : ''}
              </p>
              {#if scripts.length}
                <details class="text-xs">
                  <summary class="cursor-pointer text-warning">Review included scripts ({scripts.length})</summary>
                  {#each scripts as script, j (j)}
                    <p class="mt-2 font-medium">{script.name}</p>
                    <pre class="mt-1 max-h-48 overflow-auto rounded bg-muted p-2">{script.script}</pre>
                  {/each}
                </details>
              {/if}
            </div>
          {/each}
        </div>
        {#if actions.includes('copy')}<p class="text-xs text-muted-foreground">
            Copy numbers may change if you select fewer templates or another browser saves a matching name.
          </p>{/if}
      </div>
    {/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (open = false)}>Cancel</Button>
      <Button disabled={busy || !bundle || !count} onclick={importFile}
        >{busy ? (bundle ? 'Importing…' : 'Reading…') : `Import${count ? ` ${count}` : ''}`}</Button
      >
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
