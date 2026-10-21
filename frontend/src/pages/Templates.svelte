<script lang="ts">
  // Templates without a file: a job's whole run (video, crop, encoder, container, AutoQPF, audio, subtitles), set up
  // once and picked when adding jobs. Each profile's own defaults are built in; star a template to
  // make it the profile's default (New jobs starts on it). A job's Template menu saves one from a job.
  import { toast } from 'svelte-sonner'
  import { onDestroy } from 'svelte'
  import CopyIcon from '@lucide/svelte/icons/copy'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import SaveIcon from '@lucide/svelte/icons/save'
  import StarIcon from '@lucide/svelte/icons/star'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import { Button } from '$lib/components/ui/button'
  import * as Card from '$lib/components/ui/card'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { Textarea } from '$lib/components/ui/textarea'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import EncoderPanel from '../components/EncoderPanel.svelte'
  import FilterChain from '../components/FilterChain.svelte'
  import ResizeEditor from '../components/ResizeEditor.svelte'
  import TemplateAudioEditor from '../components/TemplateAudioEditor.svelte'
  import TemplateSubsEditor from '../components/TemplateSubsEditor.svelte'
  import { api } from '../lib/api'
  import { drafts } from '../lib/drafts'
  import { router } from '../lib/router.svelte'
  import { app } from '../lib/state.svelte'
  import { SOURCE_FILTERS, type CropMode, type SourceFilter, type Template } from '../lib/types'

  type Choice = { name: string; data: Template; builtin: boolean }
  // What the editor holds: the saved template it started from (name null = not saved yet).
  type Open = { name: string | null; builtin: boolean; data: Template }

  const restored = drafts.read<{ profile: string; opened: Open | null; draft: Template | null; draftName: string }>('templates')
  let profile = $state(restored?.profile ?? '')
  let opened = $state<Open | null>(restored?.opened ?? null)
  let draft = $state<Template | null>(restored?.draft ?? null)
  let draftName = $state(restored?.draftName ?? '')
  let pending = $state<(() => void) | null>(null)
  let busy = $state(false)
  let error = $state('')

  const SIDES = ['left', 'top', 'right', 'bottom'] as const
  const CROP_MODES: { id: CropMode; label: string }[] = [
    { id: 'keep', label: "Keep each job's" },
    { id: 'fixed', label: 'Fixed' },
    { id: 'auto', label: 'Detect per job' },
  ]

  const choices = $derived<Choice[]>(app.presetChoices('template', profile))
  const starred = $derived(app.defaultTemplate(profile))
  const userNames = $derived(new Set(app.presets.template.map(t => t.name)))
  const containers = $derived(app.profiles.find(p => p.id === profile)?.containers ?? [])
  // templates are shared; a profile without a track editor ignores their audio and subtitles
  const trackEditor = $derived(app.profiles.find(p => p.id === profile)?.track_editor ?? false)
  const trackFlags = $derived(app.profiles.find(p => p.id === profile)?.track_properties ?? [])
  const audioFlags = $derived(trackFlags.filter(f => f.kind === 'audio'))
  const subFlags = $derived(trackFlags.filter(f => f.kind === 'sub'))
  const readOnly = $derived(!!opened?.builtin)
  const dirty = $derived(
    !!opened && !!draft && !opened.builtin && (opened.name === null || draftName.trim() !== opened.name || canon(draft) !== canon(opened.data)),
  )

  function persist() { drafts.write('templates', $state.snapshot({ profile, opened, draft, draftName })) }
  function request(proceed: () => void) {
    if (busy) return
    if (dirty) pending = proceed
    else proceed()
  }
  $effect(() => {
    router.guard = request
    return () => { if (router.guard === request) router.guard = null }
  })
  onDestroy(persist)

  $effect(() => {
    if (!profile && app.defaultProfile) profile = app.defaultProfile.id
  })
  $effect(() => {
    // the first time the profile's templates are known, open its default
    if (!opened && choices.length) open(choices.find(c => c.name === starred) ?? choices[0])
  })

  function canon(v: unknown): string {
    return JSON.stringify(v, (_k, val) =>
      val && typeof val === 'object' && !Array.isArray(val) ? Object.fromEntries(Object.entries(val).sort(([a], [b]) => a.localeCompare(b))) : val,
    )
  }
  const copy = <T,>(v: T): T => structuredClone($state.snapshot(v)) as T

  function open(c: Choice) {
    opened = { name: c.builtin ? null : c.name, builtin: c.builtin, data: copy(c.data) }
    draft = copy(c.data)
    draftName = c.name
    pending = null
    error = ''
  }

  function pick(c: Choice) {
    request(() => open(c))
  }

  function unique(base: string): string {
    let name = base
    for (let i = 2; userNames.has(name); i++) name = `${base} ${i}`
    return name
  }

  function startNew() {
    const base = choices[0]?.data
    if (!base) return
    opened = { name: null, builtin: false, data: copy(base) }
    draft = copy(base)
    draftName = unique('New template')
    error = ''
  }

  function duplicate() {
    if (!draft) return
    opened = { name: null, builtin: false, data: copy(draft) }
    draftName = unique(`${draftName} copy`)
    error = ''
  }

  async function save(): Promise<boolean> {
    if (!opened || !draft) return false
    const name = draftName.trim()
    if (!name) {
      error = 'Give the template a name'
      return false
    }
    if (name !== opened.name && userNames.has(name)) {
      error = `There is already a template named ${name}`
      return false
    }
    busy = true
    try {
      if (opened.name && opened.name !== name) app.presets = await api.renamePreset('template', opened.name, name)
      app.presets = await api.savePreset('template', name, copy(draft))
      opened = { name, builtin: false, data: copy(draft) }
      draftName = name
      error = ''
      toast.success(`Saved ${name}`)
      return true
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      return false
    } finally {
      busy = false
    }
  }

  async function remove() {
    if (!opened?.name) return
    const name = opened.name
    try {
      app.presets = await api.deletePreset('template', name)
      toast.success(`Deleted ${name}`)
      opened = null // the effect opens the profile's default
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  async function star(c: Choice) {
    try {
      app.presets = await api.setTemplateDefault(profile, c.builtin ? null : c.name)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }

  async function resolve(action: 'save' | 'discard' | 'stay') {
    const next = pending
    if (action === 'stay' || !next) { pending = null; return }
    if (action === 'save' && !(await save())) return
    if (action === 'discard' && opened) {
      if (opened.name === null) { opened = null; draft = null; draftName = '' }
      else { draft = copy(opened.data); draftName = opened.name }
    }
    pending = null
    next()
  }
</script>

<svelte:window onbeforeunload={e => { persist(); if (dirty) { e.preventDefault(); e.returnValue = '' } }} />

<div class="flex h-full">
  <section class="flex w-72 shrink-0 flex-col border-r">
    <div class="space-y-3 border-b p-4">
      <h1 class="text-xl font-semibold">Templates</h1>
      <label class="flex items-center gap-2 text-sm text-muted-foreground">
        Profile
        <NativeSelect class="min-w-0 flex-1" aria-label="Profile" value={profile} onchange={e => {
          const next = e.currentTarget.value
          request(() => { profile = next; opened = null })
        }}>
          {#each app.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
        </NativeSelect>
      </label>
    </div>
    <ul class="min-h-0 flex-1 overflow-auto p-2" aria-label="Templates">
      {#each choices as c (`${c.builtin}:${c.name}`)}
        {@const active = opened && (c.builtin ? opened.builtin && draftName === c.name : opened.name === c.name)}
        <li class="flex items-center gap-1 rounded-md {active ? 'bg-primary/15 text-primary' : 'hover:bg-accent'}">
          <Button
            variant="ghost"
            size="icon-sm"
            class={c.name === starred ? 'text-warning hover:text-warning' : 'text-muted-foreground opacity-50 hover:opacity-100'}
            title={c.name === starred ? `New jobs start on this template for ${profile}` : 'Make this the default for New jobs'}
            aria-label="Default: {c.name}"
            aria-pressed={c.name === starred}
            onclick={() => star(c)}
          >
            <StarIcon class={c.name === starred ? 'fill-current' : ''} />
          </Button>
          <button class="min-w-0 flex-1 truncate py-1.5 pr-2 text-left text-sm" onclick={() => pick(c)}>
            {c.name}{#if c.builtin}<span class="ml-2 text-xs text-muted-foreground">built in</span>{/if}
          </button>
        </li>
      {/each}
    </ul>
    <div class="border-t p-2">
      <Button variant="outline" class="w-full" onclick={() => request(startNew)}><PlusIcon />New template</Button>
    </div>
  </section>

  <section class="min-w-0 flex-1 overflow-auto">
    {#if draft && opened}
      <div class="max-w-4xl space-y-4 p-6">
        <header class="flex flex-wrap items-center gap-2">
          <Input class="max-w-sm text-base font-semibold" aria-label="Template name" bind:value={draftName} disabled={readOnly} />
          {#if dirty}<span class="text-xs text-warning">{opened.name === null ? 'Not saved yet' : 'Unsaved changes'}</span>{/if}
          <div class="ml-auto flex gap-2">
            {#if !readOnly}<Button onclick={save} disabled={busy || !dirty}><SaveIcon />Save</Button>{/if}
            <Button variant="outline" onclick={duplicate}><CopyIcon />{readOnly ? 'Duplicate to change it' : 'Duplicate'}</Button>
            {#if opened.name}
              <Button variant="ghost" class="hover:text-destructive" onclick={remove}><Trash2Icon />Delete</Button>
            {/if}
          </div>
        </header>
        {#if readOnly}<p class="text-sm text-muted-foreground">The profile's own settings for a new job. Duplicate it to make your own.</p>{/if}
        {#if error}<p class="text-sm text-destructive">{error}</p>{/if}

        <fieldset disabled={readOnly} class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
          <Card.Root class="gap-4 p-4">
            <span class="section-label">Video</span>
            <label class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-2 text-sm">
              <span class="text-muted-foreground">Source filter</span>
              <NativeSelect
                class="w-full"
                value={draft.video.source_filter}
                onchange={e => (draft!.video.source_filter = e.currentTarget.value as SourceFilter)}
              >
                {#each SOURCE_FILTERS as f (f.id)}<option value={f.id} title={f.title}>{f.label}</option>{/each}
              </NativeSelect>
            </label>
            <div class="space-y-2">
              <span class="text-sm text-muted-foreground">Crop</span>
              <ToggleGroup.Root
                type="single"
                variant="outline"
                spacing={1}
                class="w-fit max-w-full flex-wrap"
                disabled={readOnly}
                value={draft.crop_mode}
                onValueChange={v => v && (draft!.crop_mode = v as CropMode)}
              >
                {#each CROP_MODES as m (m.id)}
                  <ToggleGroup.Item value={m.id} class="px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{m.label}</ToggleGroup.Item>
                {/each}
              </ToggleGroup.Root>
              {#if draft.crop_mode === 'fixed'}
                <div class="grid grid-cols-[auto_minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-sm">
                  {#each SIDES as side (side)}
                    <label class="text-muted-foreground capitalize" for="tcrop-{side}">{side}</label>
                    <Input id="tcrop-{side}" type="number" step="2" min="0" bind:value={draft.video.crop[side]} />
                  {/each}
                </div>
                <p class="text-xs text-muted-foreground">The same crop on every job (one show, the same black bars).</p>
              {:else if draft.crop_mode === 'auto'}
                <p class="text-xs text-muted-foreground">Each job's crop is detected after it's added (indexing the source takes a while the first time).</p>
              {:else}
                <p class="text-xs text-muted-foreground">Applying the template leaves each job's crop as it is.</p>
              {/if}
            </div>
            <ResizeEditor bind:resize={draft.video.resize} disabled={readOnly} />
            <FilterChain
              bind:filters={draft.video.filters}
              crop={draft.crop_mode === 'fixed' ? draft.video.crop : undefined}
              resize={draft.video.resize}
              template
              disabled={readOnly || draft.video.custom !== null}
            />
            <div class="space-y-2">
              <label class="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={draft.video.custom !== null}
                  disabled={readOnly}
                  onCheckedChange={on => (draft!.video.custom = on ? (opened?.data.video.custom ?? '') : null)}
                />
                Custom script body (instead of the filters)
              </label>
              {#if draft.video.custom !== null}
                <Textarea
                  class="h-40 w-full font-mono text-xs"
                  aria-label="Custom script body"
                  placeholder={'clip = src  # reads `src`, leaves the result in `clip`'}
                  bind:value={draft.video.custom}
                />
              {/if}
            </div>
          </Card.Root>

          <div class="min-w-0 space-y-4">
            <Card.Root class="@container/output gap-3 p-4">
              <span class="section-label">Output</span>
              <div class="grid grid-cols-[minmax(0,1fr)] items-center gap-3 text-sm @min-[26rem]/output:grid-cols-[7rem_minmax(0,1fr)]">
                <span class="text-muted-foreground">Container</span>
                {#if containers.length > 1}
                  <ToggleGroup.Root
                    type="single"
                    variant="outline"
                    spacing={1}
                    class="w-fit max-w-full flex-wrap"
                    disabled={readOnly}
                    value={containers.some(c => c.id === draft?.mux.container) ? draft.mux.container : containers[0].id}
                    onValueChange={v => v && (draft!.mux.container = v)}
                  >
                    {#each containers as c (c.id)}
                      <ToggleGroup.Item value={c.id} class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{c.label}</ToggleGroup.Item>
                    {/each}
                  </ToggleGroup.Root>
                {:else}
                  <span>{containers[0]?.label ?? '—'}{draft.mux.container && draft.mux.container !== containers[0]?.id ? ` (this profile can't make ${draft.mux.container.toUpperCase()})` : ''}</span>
                {/if}
                <span class="text-muted-foreground">Extra arguments</span>
                <Input class="font-mono text-xs" aria-label="Extra muxer arguments" placeholder="added to the muxer command as typed" bind:value={draft.mux.extra} />
                <span class="hidden @min-[26rem]/output:block"></span>
                <label class="flex items-center gap-2">
                  <Checkbox checked={draft.qpf} disabled={readOnly} onCheckedChange={v => (draft!.qpf = v)} />
                  AutoQPF: chapters from the source (or every 5%) and keyframes on them
                </label>
              </div>
            </Card.Root>
            <Card.Root class="p-4">
              <EncoderPanel {profile} value={draft.encoder} disabled={readOnly} onchange={v => (draft!.encoder = v)} />
            </Card.Root>
          </div>
        </fieldset>
        <Card.Root class="gap-3 p-4">
          <span class="section-label">Audio</span>
          {#if !trackEditor}
            <p class="text-xs text-muted-foreground">
              {app.profiles.find(p => p.id === profile)?.name}'s rules choose its jobs' audio: these settings apply to other profiles' jobs.
            </p>
          {/if}
          <TemplateAudioEditor value={draft.audio ?? null} flags={audioFlags} disabled={readOnly} onchange={v => (draft!.audio = v)} />
        </Card.Root>
        <Card.Root class="gap-3 p-4">
          <span class="section-label">Subtitles</span>
          {#if !trackEditor}
            <p class="text-xs text-muted-foreground">
              {app.profiles.find(p => p.id === profile)?.name}'s rules choose its jobs' subtitles: these settings apply to other profiles' jobs.
            </p>
          {/if}
          <TemplateSubsEditor value={draft.subs ?? null} flags={subFlags} disabled={readOnly} onchange={v => (draft!.subs = v)} />
        </Card.Root>
      </div>
    {:else}
      <div class="flex h-full items-center justify-center text-muted-foreground">Loading…</div>
    {/if}
  </section>
</div>

<Dialog.Root open={pending !== null} onOpenChange={open => { if (!open && !busy) pending = null }}>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>Save changes to {draftName}?</Dialog.Title>
      <Dialog.Description>Save this template before continuing, discard the edits, or stay here.</Dialog.Description>
    </Dialog.Header>
    {#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="ghost" disabled={busy} onclick={() => resolve('stay')}>Stay</Button>
      <Button variant="outline" disabled={busy} onclick={() => resolve('discard')}>Discard</Button>
      <Button disabled={busy} onclick={() => resolve('save')}>Save</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
