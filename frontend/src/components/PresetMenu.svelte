<script lang="ts" generics="K extends PresetKind">
  // Presets for a job's video processing or encoder: the profile's defaults (built in) and the
  // user's own. Click one to load it; save the current settings under a name; delete your own.
  // The button names the preset the current settings match, if any.
  import { api } from '../lib/api'
  import { app, type PresetData } from '../lib/state.svelte'
  import type { PresetKind } from '../lib/types'
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import * as Popover from '$lib/components/ui/popover'

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
</script>

<Popover.Root bind:open>
  <Popover.Trigger {disabled} title="Load or save a {kind} preset">
    {#snippet child({ props })}
      <Button {...props} variant="outline" class="max-w-full">
        <span class="truncate">{matched ? `Preset: ${matched}` : 'Presets'}</span><ChevronDownIcon />
      </Button>
    {/snippet}
  </Popover.Trigger>
  <Popover.Content
    align={align === 'right' ? 'end' : 'start'}
    class="w-72 gap-2 p-2"
    onEscapeKeydown={e => e.stopPropagation()}
  >
    <ul class="max-h-64 overflow-auto">
      {#each choices as c (`${c.builtin}:${c.name}`)}
        <li class="group flex items-center gap-1">
          <button
            class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-accent"
            onclick={() => load(c.data)}
          >
            <span class="w-3.5 shrink-0">{#if c.name === matched}<CheckIcon class="size-3.5 text-primary" />{/if}</span>
            <span class="truncate">{c.name}</span>
            {#if c.builtin}<span class="ml-auto shrink-0 text-xs text-muted-foreground">profile</span>{/if}
          </button>
          {#if !c.builtin}
            <Button
              variant="ghost"
              size="icon-sm"
              class="opacity-60 group-hover:opacity-100 hover:text-destructive"
              title="Delete {c.name}"
              aria-label="Delete {c.name}"
              onclick={() => remove(c.name)}
            >
              <Trash2Icon />
            </Button>
          {/if}
        </li>
      {/each}
    </ul>
    <form
      class="flex gap-1 border-t pt-2"
      onsubmit={e => {
        e.preventDefault()
        save()
      }}
    >
      <Input class="min-w-0 flex-1" placeholder="Save these settings as…" bind:value={name} />
      <Button variant="outline" type="submit" disabled={busy || !name.trim()}>{userNames.has(name.trim()) ? 'Replace' : 'Save'}</Button>
    </form>
    {#if kind === 'video'}<p class="text-xs text-muted-foreground">Video presets keep each job's own crop.</p>{/if}
    {#if error}<p class="text-xs text-destructive">{error}</p>{/if}
  </Popover.Content>
</Popover.Root>
