<script lang="ts">
  // Settings: where each tool is (found or not, and its version), what the folder browser
  // may show, and the profile new jobs start with. Each change saves at once and is used by
  // new jobs and runs; videoforge.toml stays the default underneath ("Reset" goes back to it).
  import { onMount } from 'svelte'
  import FileBrowser from '../components/FileBrowser.svelte'
  import Icon, { type IconName } from '../components/Icon.svelte'
  import { api } from '../lib/api'
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
      error = ''
      return true
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
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

  const LOOK: Record<ToolStatus, { icon: IconName; tone: string; text: string }> = {
    ok: { icon: 'check', tone: 'text-ok', text: 'found' },
    unknown: { icon: 'alert', tone: 'text-warn', text: 'found, no version' },
    missing: { icon: 'x', tone: 'text-bad', text: 'missing' },
    broken: { icon: 'x', tone: 'text-bad', text: "won't start" },
  }
</script>

<div class="h-full overflow-auto p-6">
  <div class="max-w-5xl space-y-8">
    <header class="flex items-center gap-3">
      <h1 class="text-xl font-semibold">Settings</h1>
      <span class="text-sm text-muted">Saved as you go; used by new jobs and runs.</span>
    </header>

    {#if error}<div class="rounded-md border border-bad/50 bg-bad/10 p-3 text-sm text-bad">{error}</div>{/if}
    {#each config?.restart ?? [] as note (note)}
      <div class="rounded-md border border-warn/50 bg-warn/10 p-3 text-sm text-warn">{note}</div>
    {/each}

    {#if !config}
      <p class="text-muted">{error ? '' : 'Loading…'}</p>
    {:else}
      <section class="space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Tools</h2>
          <span class="text-xs text-muted">A bare name (e.g. ffmpeg) is looked up on PATH.</span>
          <button class="btn ml-auto" onclick={checkAll} disabled={Object.values(checking).some(Boolean)}>
            <Icon name="refresh" />Check again
          </button>
        </div>
        <div class="divide-y divide-line/60 rounded-md border border-line bg-panel">
          {#each config.tools as t (t.name)}
            {@const c = checks[t.name]}
            {@const look = c ? LOOK[c.status] : null}
            <div class="grid grid-cols-[12rem_1fr] gap-x-4 gap-y-1.5 px-4 py-3">
              <div>
                <div class="text-sm font-medium">{t.label}</div>
                <div class="text-xs text-muted">{t.purpose}</div>
              </div>
              <div class="flex min-w-0 items-center gap-2">
                <input
                  class="field min-w-0 flex-1 font-mono text-xs {t.custom ? 'border-accent/60' : ''}"
                  value={t.custom ?? t.default}
                  placeholder={t.default || 'not set'}
                  aria-label="{t.label} path"
                  onchange={e => setTool(t, e.currentTarget.value)}
                />
                <button class="btn" onclick={() => (browse = { kind: 'tool', tool: t })}><Icon name="folder" />Browse…</button>
                <button
                  class="btn-ghost text-xs"
                  disabled={!t.custom}
                  title="Back to videoforge.toml's: {t.default || '(none)'}"
                  onclick={() => setTool(t, '')}>Reset</button
                >
              </div>
              <div></div>
              <div class="flex min-w-0 items-center gap-2 text-xs">
                {#if checking[t.name]}
                  <span class="text-muted">checking…</span>
                {:else if c && look}
                  <span class="flex shrink-0 items-center gap-1 {look.tone}"><Icon name={look.icon} size={13} />{look.text}</span>
                  {#if c.version}<span class="truncate" title={c.version}>{c.version}</span>{/if}
                  {#if c.detail}<span class="truncate text-muted" title={c.detail}>{c.detail}</span>{/if}
                  {#if c.found && c.found !== t.path}<span class="truncate text-muted" title={c.found}>· {c.found}</span>{/if}
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <p class="text-xs text-muted">
          Dolby Encoding Engine and qaac's CoreAudioToolbox can't be shipped with VideoForge: install them and point at them
          here. DDP needs DeeZy + DEE (+ truehdd for Atmos); AAC needs ffmpeg + qaac.
        </p>
      </section>

      <section class="space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Folder browser</h2>
          <span class="text-xs text-muted">
            {config.roots_custom ? 'Only these folders (and what is under them) can be browsed.' : 'Every drive can be browsed.'}
          </span>
          <button class="btn-ghost ml-auto text-xs" disabled={!config.roots_custom} onclick={() => setRoots(null)}>
            Reset to every drive
          </button>
        </div>
        <div class="flex flex-wrap gap-2">
          {#each config.roots as r (r)}
            <span class="flex items-center gap-1 rounded bg-raised px-2 py-1 font-mono text-xs">
              {r}
              {#if config.roots_custom}
                <button
                  class="text-muted hover:text-bad"
                  aria-label="Remove {r}"
                  onclick={() => setRoots(config!.roots.filter(x => x !== r))}><Icon name="x" size={12} /></button
                >
              {/if}
            </span>
          {/each}
        </div>
        <div class="flex gap-2">
          <input
            class="field w-96 font-mono text-xs"
            placeholder="D:\Media"
            bind:value={newRoot}
            onkeydown={e => e.key === 'Enter' && addRoot(newRoot)}
          />
          <button class="btn" onclick={() => addRoot(newRoot)} disabled={!newRoot.trim()}>Add folder</button>
          <button class="btn" onclick={() => (browse = { kind: 'root' })}><Icon name="folder" />Browse…</button>
        </div>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Profile</h2>
        <label class="flex items-center gap-3 text-sm">
          <span class="text-muted">New jobs start with</span>
          <select class="field" value={config.profile} onchange={e => setProfile(e.currentTarget.value)}>
            {#each config.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
          </select>
          <span class="text-xs text-muted">videoforge.toml says: {config.profile_default}</span>
        </label>
      </section>
    {/if}
  </div>
</div>

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
