<script lang="ts">
  // Templates, StaxRip-style: a job's whole run (video, encoder, container, AutoQPF, what to do with
  // the crop). The profile's defaults are built in; click one to apply it; save this job's settings
  // as one; delete your own. The button names the template the job's settings match, if any.
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import type { CropMode, JobSpec, Template } from '../lib/types'
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as Popover from '$lib/components/ui/popover'

  let {
    profile,
    spec,
    apply,
    disabled = false,
  }: {
    profile: string
    spec: JobSpec
    apply: (template: Template) => void | Promise<void>
    disabled?: boolean
  } = $props()

  let open = $state(false)
  let name = $state('')
  let cropMode = $state<CropMode>('keep')
  let error = $state('')
  let busy = $state(false)

  const choices = $derived(app.presetChoices('template', profile))
  const userNames = $derived(new Set(app.presets.template.map(p => p.name)))
  const current = $derived<Template>({ video: spec.video, encoder: spec.encoder, mux: spec.mux, qpf: spec.qpf, crop_mode: cropMode })
  const matched = $derived(choices.find(c => same(c.data, current))?.name ?? null)
  const crop = $derived(spec.video.crop)
  const cropText = (c: Template['video']['crop']) => `${c.left}/${c.top}/${c.right}/${c.bottom}`

  // The job's settings match a template when all but the crop does (the crop is per source).
  function canon(v: unknown): string {
    return JSON.stringify(v, (key, val) =>
      key === 'crop' || key === 'crop_mode'
        ? undefined
        : val && typeof val === 'object' && !Array.isArray(val)
          ? Object.fromEntries(Object.entries(val).sort(([a], [b]) => a.localeCompare(b)))
          : val,
    )
  }
  const same = (a: unknown, b: unknown) => canon(a) === canon(b)

  function cropNote(t: Template): string {
    return t.crop_mode === 'auto' ? 'auto crop' : t.crop_mode === 'fixed' ? `crop ${cropText(t.video.crop)}` : ''
  }

  async function load(data: Template) {
    open = false
    await apply(structuredClone($state.snapshot(data)) as Template)
  }

  async function save() {
    const n = name.trim()
    if (!n) return
    busy = true
    try {
      app.presets = await api.savePreset('template', n, structuredClone($state.snapshot(current)))
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
      app.presets = await api.deletePreset('template', n)
      error = ''
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }
</script>

<Popover.Root bind:open>
  <Popover.Trigger {disabled} title="Apply or save a template: the whole run's settings">
    {#snippet child({ props })}
      <Button {...props} variant="outline" size="sm" class="ml-auto max-w-64 shrink-0">
        <span class="truncate">{matched ? `Template: ${matched}` : 'Template'}</span><ChevronDownIcon />
      </Button>
    {/snippet}
  </Popover.Trigger>
  <Popover.Content align="end" class="w-80 gap-2 p-2" onEscapeKeydown={e => e.stopPropagation()}>
    <ul class="max-h-64 overflow-auto">
      {#each choices as c (`${c.builtin}:${c.name}`)}
        <li class="group flex items-center gap-1">
          <button
            class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-accent"
            onclick={() => load(c.data)}
          >
            <span class="w-3.5 shrink-0">{#if c.name === matched}<CheckIcon class="size-3.5 text-primary" />{/if}</span>
            <span class="truncate">{c.name}</span>
            <span class="ml-auto shrink-0 text-xs text-muted-foreground">{c.builtin ? 'profile' : cropNote(c.data)}</span>
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
      class="space-y-1 border-t pt-2"
      onsubmit={e => {
        e.preventDefault()
        save()
      }}
    >
      <div class="flex gap-1">
        <Input class="min-w-0 flex-1" placeholder="Save this job's settings as…" bind:value={name} />
        <Button variant="outline" type="submit" disabled={busy || !name.trim()}>{userNames.has(name.trim()) ? 'Replace' : 'Save'}</Button>
      </div>
      <NativeSelect class="w-full" aria-label="Crop in the template" bind:value={cropMode}>
        <option value="keep">Crop: keep each job's own</option>
        <option value="fixed">Crop: this job's ({cropText(crop)}) on every job</option>
        <option value="auto">Crop: detect it for each job</option>
      </NativeSelect>
    </form>
    <p class="text-xs text-muted-foreground">Holds video, encoder, container and AutoQPF; audio and subtitles stay per job.</p>
    {#if error}<p class="text-xs text-destructive">{error}</p>{/if}
  </Popover.Content>
</Popover.Root>
