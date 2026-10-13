<script lang="ts" generics="K extends PresetKind">
  // Presets for a job's video processing or encoder: the profile's defaults (built in) and the
  // user's own. Click one to load it; save the current settings under a name; delete your own.
  // The button names the preset the current settings match, if any.
  import { api } from '../lib/api'
  import { app, type PresetData } from '../lib/state.svelte'
  import type { PresetKind } from '../lib/types'
  import Icon from './Icon.svelte'

  let {
    kind,
    profile,
    current,
    apply,
    disabled = false,
    align = 'left',
  }: {
    kind: K
    profile: string
    current: PresetData<K>
    apply: (data: PresetData<K>) => void | Promise<void>
    disabled?: boolean
    align?: 'left' | 'right'
  } = $props()

  let open = $state(false)
  let name = $state('')
  let error = $state('')
  let busy = $state(false)
  let root = $state<HTMLDivElement>()

  const choices = $derived(app.presetChoices(kind, profile))
  const userNames = $derived(new Set(app.presets[kind].map(p => p.name)))
  const matched = $derived(choices.find(c => same(c.data, current))?.name ?? null)

  // Compare as the server stores them: sorted keys, and a video preset has no crop.
  function canon(v: unknown): string {
    return JSON.stringify(v, (key, val) =>
      key === 'crop' && kind === 'video'
        ? undefined
        : val && typeof val === 'object' && !Array.isArray(val)
          ? Object.fromEntries(Object.entries(val).sort(([a], [b]) => a.localeCompare(b)))
          : val,
    )
  }
  const same = (a: unknown, b: unknown) => canon(a) === canon(b)

  async function load(data: PresetData<K>) {
    open = false
    await apply(structuredClone($state.snapshot(data)) as PresetData<K>)
  }

  async function save() {
    const n = name.trim()
    if (!n) return
    busy = true
    try {
      const data = structuredClone($state.snapshot(current)) as Record<string, unknown>
      if (kind === 'video') delete data.crop
      app.presets = await api.savePreset(kind, n, data)
      name = ''
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }

  async function remove(n: string) {
    try {
      app.presets = await api.deletePreset(kind, n)
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  function onwindow(e: PointerEvent) {
    if (open && root && !root.contains(e.target as Node)) open = false
  }
</script>

<svelte:window onpointerdown={onwindow} onkeydown={e => open && e.key === 'Escape' && (open = false)} />

<div class="relative" bind:this={root}>
  <button class="btn max-w-full" {disabled} onclick={() => (open = !open)} title="Load or save a {kind} preset">
    <span class="truncate">{matched ? `Preset: ${matched}` : 'Presets'}</span><Icon name="down" size={14} />
  </button>
  {#if open}
    <div
      class="panel absolute top-full z-20 mt-1 w-72 space-y-2 p-2 text-sm shadow-lg {align === 'right' ? 'right-0' : 'left-0'}"
    >
      <ul class="max-h-64 overflow-auto">
        {#each choices as c (`${c.builtin}:${c.name}`)}
          <li class="group flex items-center gap-1">
            <button
              class="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1 text-left hover:bg-raised"
              onclick={() => load(c.data)}
            >
              <span class="w-3.5 shrink-0">{#if c.name === matched}<Icon name="check" size={14} class="text-accent" />{/if}</span>
              <span class="truncate">{c.name}</span>
              {#if c.builtin}<span class="ml-auto shrink-0 text-xs text-muted">profile</span>{/if}
            </button>
            {#if !c.builtin}
              <button class="btn-ghost px-1.5 opacity-60 group-hover:opacity-100" title="Delete {c.name}" onclick={() => remove(c.name)}>
                <Icon name="trash" size={14} />
              </button>
            {/if}
          </li>
        {/each}
      </ul>
      <form
        class="flex gap-1 border-t border-line pt-2"
        onsubmit={e => {
          e.preventDefault()
          save()
        }}
      >
        <input class="field min-w-0 flex-1" placeholder="Save these settings as…" bind:value={name} />
        <button class="btn" type="submit" disabled={busy || !name.trim()}>{userNames.has(name.trim()) ? 'Replace' : 'Save'}</button>
      </form>
      {#if kind === 'video'}<p class="text-xs text-muted">Video presets keep each job's own crop.</p>{/if}
      {#if error}<p class="text-xs text-bad">{error}</p>{/if}
    </div>
  {/if}
</div>
