<script lang="ts">
  // Settings: where each tool is (found or not, and its version), what the folder browser
  // may show, the profile new jobs start with, and whether batch indexing waits for an encode's disk. Each change saves at once and is used by
  // new jobs and runs; videoforge.toml stays the default underneath ("Reset" goes back to it).
  import { onMount } from 'svelte'
  import FileBrowser from '../components/FileBrowser.svelte'
  import CheckIcon from '@lucide/svelte/icons/check'
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import PowerIcon from '@lucide/svelte/icons/power'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import XIcon from '@lucide/svelte/icons/x'
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { api } from '../lib/api'
  import { drops } from '../lib/dropPaths.svelte'
  import { app } from '../lib/state.svelte'
  import type { ConfigState, ToolCheck, ToolSetting, ToolStatus } from '../lib/types'

  let config = $state<ConfigState | null>(null)
  let checks = $state<Record<string, ToolCheck>>({})
  let checking = $state<Record<string, boolean>>({})
  let error = $state('')
  let newRoot = $state('')
  let browse = $state<{ kind: 'tool'; tool: ToolSetting } | { kind: 'root' } | null>(null)

  async function checkAll() {
    const names = config?.tools.map(t => t.name) ?? []
    checking = Object.fromEntries(names.map(n => [n, true]))
    try {
      const all = await api.toolChecks()
      checks = Object.fromEntries(all.map(c => [c.name, c]))
    } finally {
      checking = {}
    }
  }

  onMount(async () => {
    try {
      config = await api.config()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      return
    }
    checkAll()
  })

  async function change(changes: Parameters<typeof api.saveConfig>[0]): Promise<boolean> {
    try {
      config = await api.saveConfig(changes)
      return true
    } catch (e) {
      toast.error("Couldn't save the settings", { description: e instanceof Error ? e.message : String(e) })
      return false
    }
  }

  async function setTool(t: ToolSetting, value: string) {
    const path = value.trim()
    if (!(await change({ tools: { [t.name]: path && path !== t.default ? path : null } }))) return
    app.loadEncoders()
    checking = { ...checking, [t.name]: true }
    try {
      const now = config!.tools.find(x => x.name === t.name)!
      checks = { ...checks, [t.name]: await api.checkTool(t.name, now.path) }
    } finally {
      checking = { ...checking, [t.name]: false }
    }
  }

  async function setProfile(id: string) {
    if (await change({ profile: id === config?.profile_default ? null : id })) app.profiles = await api.profiles()
  }

  function setRoots(roots: string[] | null) {
    change({ roots })
  }

  async function addRoot(path: string) {
    const p = path.trim()
    if (!p || !config) return
    const current = config.roots_custom ? config.roots : []
    if (await change({ roots: [...current.filter(r => r.toLowerCase() !== p.toLowerCase()), p] })) newRoot = ''
  }

  // Where Browse opens: the tool's folder (or the plugin folder itself).
  function startFolder(t: ToolSetting): string {
    const found = checks[t.name]?.found ?? ''
    return t.folder ? found : found.replace(/[\\/][^\\/]*$/, '')
  }

  const LOOK: Record<ToolStatus, { icon: typeof CheckIcon; tone: string; text: string }> = {
    ok: { icon: CheckIcon, tone: 'text-success', text: 'found' },
    unknown: { icon: TriangleAlertIcon, tone: 'text-warning', text: 'found, no version' },
    missing: { icon: XIcon, tone: 'text-destructive', text: 'missing' },
    broken: { icon: XIcon, tone: 'text-destructive', text: "won't start" },
  }

  // --- shutting down from the page ---
  let confirmStop = $state(false)
  let stopping = $state(false)

  async function shutDown() {
    stopping = true
    try {
      await api.shutdown()
      app.stopped = true
      confirmStop = false
    } catch (e) {
      toast.error("Couldn't shut down", { description: e instanceof Error ? e.message : String(e) })
    } finally {
      stopping = false
    }
  }
</script>

<div class="h-full overflow-auto p-6">
  <div class="max-w-5xl space-y-8">
    <header class="flex items-center gap-3">
      <h1 class="text-xl font-semibold">Settings</h1>
      <span class="text-sm text-muted-foreground">Saved as you go; used by new jobs and runs.</span>
    </header>

    {#if error}<div class="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>{/if}
    {#each config?.restart ?? [] as note (note)}
      <div class="rounded-md border border-warning/50 bg-warning/10 p-3 text-sm text-warning">{note}</div>
    {/each}

    {#if !config}
      <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
    {:else}
      <section class="space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Tools</h2>
          <span class="text-xs text-muted-foreground">A bare name (e.g. ffmpeg) is looked up on PATH.</span>
          <Button variant="outline" class="ml-auto" onclick={checkAll} disabled={Object.values(checking).some(Boolean)}>
            <RefreshCwIcon />Check again
          </Button>
        </div>
        <div class="divide-y divide-border/60 rounded-xl border bg-card">
          {#each config.tools as t (t.name)}
            {@const c = checks[t.name]}
            {@const look = c ? LOOK[c.status] : null}
            <div class="grid grid-cols-[12rem_1fr] gap-x-4 gap-y-1.5 px-4 py-3">
              <div>
                <div class="text-sm font-medium">{t.label}</div>
                <div class="text-xs text-muted-foreground">{t.purpose}</div>
              </div>
              <div class="flex min-w-0 items-center gap-2">
                <Input
                  class="min-w-0 flex-1 font-mono text-xs {t.custom ? 'border-primary/60' : ''}"
                  value={t.custom ?? t.default}
                  placeholder={t.default || 'not set'}
                  aria-label="{t.label} path"
                  onchange={e => setTool(t, e.currentTarget.value)}
                />
                <Button variant="outline" onclick={() => (browse = { kind: 'tool', tool: t })}><FolderOpenIcon />Browse…</Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!t.custom}
                  title="Back to videoforge.toml's: {t.default || '(none)'}"
                  onclick={() => setTool(t, '')}>Reset</Button
                >
              </div>
              <div></div>
              <div class="flex min-w-0 items-center gap-2 text-xs">
                {#if checking[t.name]}
                  <span class="text-muted-foreground">checking…</span>
                {:else if c && look}
                  <span class="flex shrink-0 items-center gap-1 {look.tone}"><look.icon class="size-3.5" />{look.text}</span>
                  {#if c.version}<span class="truncate" title={c.version}>{c.version}</span>{/if}
                  {#if c.detail}<span class="truncate text-muted-foreground" title={c.detail}>{c.detail}</span>{/if}
                  {#if c.found && c.found !== t.path}<span class="truncate text-muted-foreground" title={c.found}>· {c.found}</span>{/if}
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <p class="text-xs text-muted-foreground">
          Dolby Encoding Engine and qaac's CoreAudioToolbox can't be shipped with VideoForge: install them and point at them
          here. DDP needs DeeZy + DEE (+ truehdd for Atmos); AAC needs ffmpeg + qaac.
        </p>
      </section>

      <section class="space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Folder browser</h2>
          <span class="text-xs text-muted-foreground">
            {config.roots_custom ? 'Only these folders (and what is under them) can be browsed.' : 'Every drive can be browsed.'}
          </span>
          <Button variant="ghost" size="sm" class="ml-auto" disabled={!config.roots_custom} onclick={() => setRoots(null)}>
            Reset to every drive
          </Button>
        </div>
        <div class="flex flex-wrap gap-2">
          {#each config.roots as r (r)}
            <span class="flex items-center gap-1 rounded-md bg-muted px-2 py-1 font-mono text-xs">
              {r}
              {#if config.roots_custom}
                <button
                  class="text-muted-foreground hover:text-destructive"
                  aria-label="Remove {r}"
                  onclick={() => setRoots(config!.roots.filter(x => x !== r))}><XIcon class="size-3" /></button
                >
              {/if}
            </span>
          {/each}
        </div>
        <div class="flex gap-2">
          <Input
            class="w-96 font-mono text-xs"
            placeholder="D:\Media"
            bind:value={newRoot}
            onkeydown={e => e.key === 'Enter' && addRoot(newRoot)}
          />
          <Button variant="outline" onclick={() => addRoot(newRoot)} disabled={!newRoot.trim()}>Add folder</Button>
          <Button variant="outline" onclick={() => (browse = { kind: 'root' })}><FolderOpenIcon />Browse…</Button>
        </div>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Profile</h2>
        <label class="flex items-center gap-3 text-sm">
          <span class="text-muted-foreground">New jobs start with</span>
          <NativeSelect value={config.profile} onchange={e => setProfile(e.currentTarget.value)}>
            {#each config.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
          </NativeSelect>
          <span class="text-xs text-muted-foreground">videoforge.toml says: {config.profile_default}</span>
        </label>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Batch indexing</h2>
        <label class="flex items-start gap-3 text-sm">
          <Checkbox
            class="mt-0.5"
            checked={config.index_waits_for_disk}
            onCheckedChange={v => change({ index_waits_for_disk: v })}
          />
          <span>
            Wait while an encode reads the same disk
            <span class="block text-xs text-muted-foreground">
              A job in the index lane whose source is on the disk the running encode reads waits for it to finish; jobs on
              other disks go first. Index now on a job never waits.
            </span>
          </span>
        </label>
      </section>
    {/if}

    <section class="space-y-3">
      <h2 class="font-medium">VideoForge</h2>
      <div class="flex flex-wrap items-center gap-3 text-sm">
        <Button variant="outline" class="text-destructive hover:text-destructive" onclick={() => (confirmStop = true)}>
          <PowerIcon />Shut down…
        </Button>
        <span class="text-muted-foreground">
          Stops the server{drops.desktop ? ' and closes this window' : ''}; start it again with
          <code class="text-xs">videoforge serve{drops.desktop ? ' --window' : ''}</code>.
        </span>
      </div>
    </section>
  </div>
</div>

<Dialog.Root bind:open={confirmStop}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Shut down VideoForge?</Dialog.Title>
      <Dialog.Description>
        {#if app.queue.running}
          A job is running: it is cancelled. Started again, it skips the steps it finished.
        {:else}
          No job is running.
        {/if}
        {#if app.queue.queued}{app.queue.queued} queued job(s) stay in the queue.{/if}
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => (confirmStop = false)}>Cancel</Button>
      <Button variant="destructive" disabled={stopping} onclick={shutDown}><PowerIcon />Shut down</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

{#if browse}
  <FileBrowser
    title={browse.kind === 'tool' ? browse.tool.label : 'Add a folder'}
    mode={browse.kind === 'root' || browse.tool.folder ? 'folder' : 'files'}
    extensions={browse.kind === 'tool' && !browse.tool.folder ? ['.exe', '.bat', '.cmd'] : []}
    start={browse.kind === 'tool' ? startFolder(browse.tool) : ''}
    onpick={paths => {
      const b = browse
      browse = null
      if (!paths[0] || !b) return
      if (b.kind === 'tool') setTool(b.tool, paths[0])
      else addRoot(paths[0])
    }}
    onclose={() => (browse = null)}
  />
{/if}
