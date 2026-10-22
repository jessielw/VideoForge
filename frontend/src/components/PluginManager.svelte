<script lang="ts">
  import { toast } from 'svelte-sonner'
  import UploadIcon from '@lucide/svelte/icons/upload'
  import { Button } from '$lib/components/ui/button'
  import * as Dialog from '$lib/components/ui/dialog'
  import { api } from '../lib/api'
  import { saves } from '../lib/saves'
  import type { ConfigState, ManagedPlugin, PluginInventory, PluginPreview } from '../lib/types'

  let { refreshKey = 0, onupdated }: { refreshKey?: number; onupdated: (config: ConfigState) => void } = $props()
  let inventory = $state<PluginInventory | null>(null)
  let error = $state('')
  let busy = $state(false)
  let installOpen = $state(false)
  let preview = $state<PluginPreview | null>(null)
  let file = $state<File | null>(null)
  let trusted = $state(false)
  let removing = $state<ManagedPlugin | null>(null)
  let editing = $state<ManagedPlugin | null>(null)
  let values = $state<Record<string, string | boolean | number>>({})
  let changed = $state<string[]>([])
  let dialogError = $state('')

  async function refresh() {
    try { inventory = await api.plugins(); error = '' }
    catch (e) { error = e instanceof Error ? e.message : String(e) }
  }
  $effect(() => { refreshKey; void refresh() })

  async function update(operation: () => Promise<PluginInventory>, message: string) {
    busy = true
    dialogError = ''
    error = ''
    try {
      await saves.flush()
      // Share Settings' write order. Validation errors belong to this dialog, not the global save retry queue.
      const result = await saves.add(async () => {
        try { return { inventory: await operation() } }
        catch (failure) { return { failure } }
      })
      if ('failure' in result) throw result.failure
      inventory = result.inventory
      onupdated(await api.config())
      toast.success(message)
      return true
    } catch (e) {
      dialogError = e instanceof Error ? e.message : String(e)
      error = dialogError
      return false
    } finally { busy = false }
  }
  async function readFile(selected?: File) {
    preview = null
    file = selected ?? null
    trusted = false
    dialogError = ''
    if (!selected) return
    if (selected.size > 50 * 1024 * 1024) { dialogError = 'Plugin ZIP files must be 50 MiB or smaller'; return }
    busy = true
    try { preview = await api.previewPlugin(selected) }
    catch (e) { dialogError = e instanceof Error ? e.message : String(e) }
    finally { busy = false }
  }
  async function install() {
    if (!file || !preview || !trusted) return
    const selected = file, checked = preview
    if (await update(() => api.installPlugin(selected, checked.revision, !!checked.current), 'Plugin queued for the next restart')) {
      installOpen = false
      preview = null
      file = null
    }
  }
  function edit(plugin: ManagedPlugin) {
    editing = plugin
    values = { ...plugin.values }
    changed = []
    dialogError = ''
  }
  function field(key: string, value: string | boolean | number) {
    values = { ...values, [key]: value }
    if (!changed.includes(key)) changed = [...changed, key]
  }
  async function saveSettings(reset = false) {
    if (!editing) return
    const plugin = editing
    const patch = reset ? {} : Object.fromEntries(changed.map(key => [key, values[key]]))
    if (await update(() => api.pluginSettings(plugin.id, patch, reset ? plugin.settings.map(s => s.key) : []), 'Plugin settings saved for the next restart')) editing = null
  }
</script>

<section class="col-span-full min-w-0 space-y-3" aria-label="Plugin manager">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h2 class="font-medium">Plugins</h2>
    <Button variant="outline" disabled={!inventory?.management_enabled || busy} onclick={() => { installOpen = true; preview = null; file = null; trusted = false; dialogError = '' }}>
      <UploadIcon />Install ZIP…
    </Button>
  </div>
  <p class="text-xs text-muted-foreground">Python plugins react to job started, job finished, queue finished, and indexing finished. Changes take effect when VideoForge starts again.</p>
  {#if inventory}
    <p class="break-all text-xs text-muted-foreground">Plugin folder: <code>{inventory.folder}</code></p>
    {#if !inventory.management_enabled}<p class="text-xs text-muted-foreground">Plugin management is disabled for this server. Enable it at startup with <code>--plugin-management</code>.</p>{/if}
    <div class="divide-y divide-border/60 rounded-xl border bg-card">
      {#each inventory.items as plugin (plugin.id)}
        <div class="min-w-0 space-y-2 px-4 py-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="min-w-0 space-y-1">
              <div class="flex flex-wrap items-baseline gap-2 text-sm"><span class="font-medium">{plugin.name}</span><span class="text-xs text-muted-foreground">{plugin.version}</span><code class="text-xs text-muted-foreground">{plugin.id}</code></div>
              <p class="text-xs text-muted-foreground">
                {plugin.running ? `Running${plugin.running_version ? ` ${plugin.running_version}` : ''}` : 'Not running'}
                · {plugin.enabled ? 'Enabled on next start' : 'Disabled on next start'}
                {#if plugin.pending} · {plugin.pending === 'install' ? 'Install' : plugin.pending === 'replace' ? 'Replacement' : 'Removal'} pending restart{/if}
              </p>
            </div>
            <label class="flex items-center gap-2 text-xs"><input type="checkbox" checked={plugin.enabled} disabled={busy || !inventory.management_enabled || plugin.pending === 'remove'} onchange={e => { const enabled = e.currentTarget.checked; void update(() => api.enablePlugin(plugin.id, enabled), 'Plugin preference saved for the next restart') }} />Enabled</label>
          </div>
          {#if plugin.description}<p class="text-xs">{plugin.description}</p>{/if}
          {#if plugin.events.length}<p class="text-xs text-muted-foreground">Handles: {plugin.events.join(', ')}</p>{/if}
          {#if plugin.error}<p class="text-xs text-destructive" role="alert">{plugin.error}</p>{/if}
          <details class="text-xs">
            <summary class="cursor-pointer">Details and settings</summary>
            <p class="mt-2 break-all text-muted-foreground">{plugin.source}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              {#if plugin.settings.length}<Button size="sm" variant="outline" disabled={busy || !inventory.management_enabled || plugin.pending === 'remove'} onclick={() => edit(plugin)}>Configure {plugin.name}</Button>{/if}
              {#if plugin.removable && !plugin.pending}<Button size="sm" variant="outline" disabled={busy || !inventory.management_enabled} onclick={() => { removing = plugin; dialogError = '' }}>Remove {plugin.name}…</Button>{/if}
              {#if !plugin.removable && !plugin.pending}<span class="text-muted-foreground">Files are managed outside VideoForge.</span>{/if}
            </div>
          </details>
        </div>
      {/each}
      {#if !inventory.items.length}<p class="px-4 py-3 text-xs text-muted-foreground">No plugins installed.</p>{/if}
    </div>
    {#each inventory.failures as failure}<p class="text-xs text-destructive" role="alert">{failure}</p>{/each}
  {/if}
  {#if error && !installOpen && !editing && !removing}<p class="text-xs text-destructive" role="alert">{error}</p>{/if}
</section>

<Dialog.Root open={installOpen} onOpenChange={value => { if (!busy) installOpen = value }}>
  <Dialog.Content class="max-h-[90dvh] overflow-y-auto sm:max-w-xl" showCloseButton={!busy} onEscapeKeydown={e => { if (busy) e.preventDefault() }} onInteractOutside={e => { if (busy) e.preventDefault() }}>
    <Dialog.Header><Dialog.Title>Install plugin</Dialog.Title><Dialog.Description>Choose a VideoForge plugin ZIP. It will load after you restart the app.</Dialog.Description></Dialog.Header>
    <label class="space-y-2 text-sm"><span>Plugin ZIP (up to 50 MiB)</span><input class="block w-full rounded-md border p-2 text-sm" type="file" accept=".zip,application/zip" disabled={busy} onchange={e => readFile(e.currentTarget.files?.[0])} /></label>
    {#if preview}
      <div class="space-y-2 rounded-md border p-3 text-sm">
        <p class="font-medium">{preview.plugin.name} {preview.plugin.version}</p>
        <p class="text-xs text-muted-foreground">{preview.plugin.id} · Plugin API {preview.plugin.api_version}</p>
        {#if preview.plugin.description}<p>{preview.plugin.description}</p>{/if}
        {#if preview.current}<p>Replace installed version {preview.current.version || '(unspecified)'} with {preview.plugin.version}. Settings and plugin data will be kept.</p>{/if}
      </div>
      <label class="flex items-start gap-2 text-sm"><input type="checkbox" bind:checked={trusted} disabled={busy} class="mt-1" /><span>I trust this plugin. Its Python code can access files and the network as VideoForge’s user.</span></label>
    {/if}
    {#if dialogError}<p class="text-sm text-destructive" role="alert">{dialogError}</p>{/if}
    <Dialog.Footer><Button variant="outline" disabled={busy} onclick={() => installOpen = false}>Cancel</Button><Button disabled={busy || !preview || !trusted} onclick={install}>{busy ? 'Working…' : preview?.current ? 'Replace on restart' : 'Install on restart'}</Button></Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root open={!!editing} onOpenChange={value => { if (!value && !busy) editing = null }}>
  <Dialog.Content class="max-h-[90dvh] overflow-y-auto sm:max-w-xl" showCloseButton={!busy} onEscapeKeydown={e => { if (busy) e.preventDefault() }} onInteractOutside={e => { if (busy) e.preventDefault() }}>
    <Dialog.Header><Dialog.Title>Configure {editing?.name}</Dialog.Title><Dialog.Description>Settings apply after restart. Leave a stored password unchanged to keep it.</Dialog.Description></Dialog.Header>
    {#if editing}
      {#each editing.settings as setting (setting.key)}
        <label class="block space-y-1 text-sm">
          <span>{setting.label}{setting.required ? ' *' : ''}</span>
          {#if setting.type === 'checkbox'}
            <input class="ml-2" type="checkbox" checked={values[setting.key] === true} disabled={busy} onchange={e => field(setting.key, e.currentTarget.checked)} />
          {:else if setting.type === 'choice'}
            <select class="block w-full rounded-md border bg-background p-2" value={String(values[setting.key] ?? '')} disabled={busy} onchange={e => field(setting.key, e.currentTarget.value)}><option value="" disabled>Choose…</option>{#each setting.choices as choice}<option value={choice}>{choice}</option>{/each}</select>
          {:else if setting.type === 'integer'}
            <input class="block w-full rounded-md border bg-background p-2" type="number" step="1" value={values[setting.key] as number ?? ''} disabled={busy} oninput={e => field(setting.key, e.currentTarget.value === '' ? '' : Number(e.currentTarget.value))} />
          {:else}
            <input class="block w-full rounded-md border bg-background p-2" type={setting.type === 'password' ? 'password' : 'text'} autocomplete={setting.type === 'password' ? 'new-password' : 'off'} value={String(values[setting.key] ?? '')} placeholder={setting.type === 'password' && editing.configured_passwords.includes(setting.key) ? 'Stored password (unchanged)' : ''} disabled={busy} oninput={e => field(setting.key, e.currentTarget.value)} />
          {/if}
          {#if setting.help}<span class="block text-xs text-muted-foreground">{setting.help}</span>{/if}
        </label>
      {/each}
    {/if}
    {#if dialogError}<p class="text-sm text-destructive" role="alert">{dialogError}</p>{/if}
    <Dialog.Footer><Button variant="outline" disabled={busy} onclick={() => saveSettings(true)}>Reset overrides</Button><Button variant="outline" disabled={busy} onclick={() => editing = null}>Cancel</Button><Button disabled={busy || !changed.length} onclick={() => saveSettings()}>Save settings</Button></Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root open={!!removing} onOpenChange={value => { if (!value && !busy) removing = null }}>
  <Dialog.Content showCloseButton={!busy} onEscapeKeydown={e => { if (busy) e.preventDefault() }} onInteractOutside={e => { if (busy) e.preventDefault() }}>
    <Dialog.Header><Dialog.Title>Remove {removing?.name}?</Dialog.Title><Dialog.Description>Plugin files will be removed on the next restart. Saved settings and plugin data will be kept.</Dialog.Description></Dialog.Header>
    {#if dialogError}<p class="text-sm text-destructive" role="alert">{dialogError}</p>{/if}
    <Dialog.Footer><Button variant="outline" disabled={busy} onclick={() => removing = null}>Cancel</Button><Button variant="destructive" disabled={busy} onclick={async () => { if (!removing) return; const plugin = removing; if (await update(() => api.removePlugin(plugin.id, plugin.revision), 'Plugin removal queued for the next restart')) removing = null }}>Remove on restart</Button></Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
