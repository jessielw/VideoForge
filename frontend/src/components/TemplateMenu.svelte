<script lang="ts">
  // Templates, StaxRip-style: a job's whole run (video, encoder, container, AutoQPF, what to do with
  // the crop, audio, subtitle rules). The profile's defaults are built in; click one to apply it; save
  // this job's settings as one (its audio by position; replacing one keeps its subtitle rules and audio
  // rules: they're set on the Templates page); delete your own. The button names the template the job's settings match, if any.
  import { api } from '../lib/api'
  import { router } from '../lib/router.svelte'
  import { app } from '../lib/state.svelte'
  import { splitName } from '../lib/templateFolders'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import type { CropMode, JobSpec, Template, TemplateAudio, TrackOverride } from '../lib/types'
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as Popover from '$lib/components/ui/popover'
  import Tip from './Tip.svelte'

  let {
    profile,
    spec,
    audioKeys,
    apply,
    disabled = false,
  }: {
    profile: string
    spec: JobSpec
    audioKeys: string[] // the source's audio tracks, in source order (not added files or copies)
    apply: (template: Template) => void | Promise<void>
    disabled?: boolean
  } = $props()

  let open = $state(false)
  let name = $state('')
  let cropMode = $state<CropMode>('keep')
  let withAudio = $state(true)
  let error = $state('')
  let busy = $state(false)

  const choices = $derived(app.presetChoices('template', profile))
  // a profile without a track editor chooses the audio by its own rules, so there's none to save
  const trackEditor = $derived(app.profiles.find((p) => p.id === profile)?.track_editor ?? false)
  const userNames = $derived(new Set(app.presets.template.map((p) => p.name)))
  // replacing a template whose audio is by rules keeps them (rules can't be made from a job)
  const replaced = $derived(app.presets.template.find((p) => p.name === name.trim())?.data ?? null)
  const keepsRules = $derived(replaced?.audio?.mode === 'rules')
  const current = $derived<Template>({
    video: spec.video,
    encoder: spec.encoder,
    mux: spec.mux,
    qpf: spec.qpf,
    crop_mode: cropMode,
    audio: withAudio && trackEditor ? jobAudio() : null,
  })

  // The job's audio choices as slots: track n's settings and the outputs copied from it, by position.
  function jobAudio(): TemplateAudio | null {
    if (!audioKeys.length) return null
    const o = spec.overrides
    const strip = (ov: TrackOverride | undefined): TrackOverride => ({
      exclude: null,
      title: null,
      flags: {},
      action: null,
      bitrate_kbps: null,
      layout: null,
      options: {},
      ...ov,
      language: null,
    })
    const copiesOf = (key: string) =>
      o.copies.filter((c) => c.startsWith(`${key}+`)).sort((a, b) => +a.split('+').pop()! - +b.split('+').pop()!)
    const slots = audioKeys.map((k) => ({
      track: strip(o.tracks[k]),
      extra: copiesOf(k).map((c) => strip(o.tracks[c])),
    }))
    return { mode: 'position', slots, rules: [], others: 'keep' }
  }
  const matched = $derived(choices.find((c) => same(c.data, current))?.name ?? null)
  const crop = $derived(spec.video.crop)
  const cropText = (c: Template['video']['crop']) => `${c.left}/${c.top}/${c.right}/${c.bottom}`

  // The job's settings match a template when all but the crop and tracks do (per source, or rules).
  function canon(v: unknown): string {
    return JSON.stringify(v, (key, val) =>
      key === 'crop' || key === 'crop_mode' || key === 'audio' || key === 'subs'
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
      const old = app.presets.template.find((p) => p.name === n)?.data
      const audio = old?.audio?.mode === 'rules' ? old.audio : current.audio
      app.presets = await api.savePreset('template', n, {
        ...structuredClone($state.snapshot(current)),
        audio,
        subs: old?.subs ?? null,
      })
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
  <Tip class="ml-auto shrink-0" text="Apply or save a template: the whole run's settings">
    <Popover.Trigger {disabled}>
      {#snippet child({ props })}
        <Button {...props} variant="outline" size="sm" class="max-w-64">
          <span class="truncate">{matched ? `Template: ${matched}` : 'Template'}</span><ChevronDownIcon />
        </Button>
      {/snippet}
    </Popover.Trigger>
  </Tip>
  <Popover.Content align="end" class="w-80 gap-2 p-2" onEscapeKeydown={(e) => e.stopPropagation()}>
    <ul class="max-h-64 overflow-auto">
      {#each choices as c (`${c.builtin}:${c.name}`)}
        {@const { folder, label } = splitName(c.name)}
        <li class="group flex items-center gap-1">
          <button
            class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-accent"
            onclick={() => load(c.data)}
          >
            <span class="w-3.5 shrink-0"
              >{#if c.name === matched}<CheckIcon class="size-3.5 text-primary" />{/if}</span
            >
            <Tip class="block truncate" text={c.name}
              >{#if folder.length}<span class="text-muted-foreground">{folder.join(' / ')} / </span>{/if}{label ||
                c.name}</Tip
            >
            <span class="ml-auto shrink-0 text-xs text-muted-foreground"
              >{c.builtin ? 'profile' : cropNote(c.data)}</span
            >
          </button>
          {#if !c.builtin}
            <Tip text="Delete {c.name}">
              <Button
                variant="ghost"
                size="icon-sm"
                class="opacity-60 group-hover:opacity-100 hover:text-destructive"
                aria-label="Delete {c.name}"
                onclick={() => remove(c.name)}
              >
                <Trash2Icon />
              </Button>
            </Tip>
          {/if}
        </li>
      {/each}
    </ul>
    <form
      class="space-y-1 border-t pt-2"
      onsubmit={(e) => {
        e.preventDefault()
        save()
      }}
    >
      <div class="flex gap-1">
        <Input class="min-w-0 flex-1" placeholder="Save this job's settings as…" bind:value={name} />
        <Button variant="outline" type="submit" disabled={busy || !name.trim()}
          >{userNames.has(name.trim()) ? 'Replace' : 'Save'}</Button
        >
      </div>
      <NativeSelect class="w-full" aria-label="Crop in the template" bind:value={cropMode}>
        <option value="keep">Crop: keep each job's own</option>
        <option value="fixed">Crop: this job's ({cropText(crop)}) on every job</option>
        <option value="auto">Crop: detect it for each job</option>
      </NativeSelect>
      {#if keepsRules}
        <p class="text-xs text-muted-foreground">Audio: {name.trim()}'s rules are kept.</p>
      {:else if audioKeys.length && trackEditor}
        <label class="flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox bind:checked={withAudio} />
          This job's audio too ({audioKeys.length} track{audioKeys.length === 1 ? '' : 's'}, by position)
        </label>
      {/if}
    </form>
    <p class="text-xs text-muted-foreground">
      Holds video, encoder, audio, subtitle rules, container and AutoQPF.
      <button class="underline underline-offset-2" onclick={() => router.go('templates')}>Edit templates…</button>
    </p>
    {#if error}<p class="text-xs text-destructive">{error}</p>{/if}
  </Popover.Content>
</Popover.Root>
