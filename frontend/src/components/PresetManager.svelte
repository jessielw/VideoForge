<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import CopyIcon from '@lucide/svelte/icons/copy'
  import SaveIcon from '@lucide/svelte/icons/save'
  import Trash2Icon from '@lucide/svelte/icons/trash-2'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import * as Dialog from '$lib/components/ui/dialog'
  import PresetBrowser from './PresetBrowser.svelte'
  import { canonical, draftFromChoice, duplicatePresetDraft, folderParts, matchingPreset, newPresetDraft, presetKey, presetLabel, saveDestination, type PresetChoice, type PresetDraft } from '../lib/presetDraft'

  let { title, current, choices, parents, parentOf, summary, editor, apply, savePreset, removePreset,
    onclose, onapplied, nameExample, folderExample, folderHint, builtinLabel = 'built-in',
    problem = () => '', applyLabel = 'Apply settings', initialSelected = null }: {
    title: string
    current: T
    choices: PresetChoice<T>[]
    parents: [string, string][]
    parentOf: (data: T) => string
    summary: (data: T) => string
    editor: Snippet<[T, (value: T) => void]>
    apply: (data: T) => void | Promise<void>
    savePreset: (preset: { name?: string; label: string; group: string[]; data: T }) => Promise<PresetChoice<T>[]>
    removePreset: (name: string) => Promise<void>
    onclose: () => void
    onapplied: (key: string | null) => void
    nameExample: string
    folderExample: string
    folderHint: string
    builtinLabel?: string
    problem?: (data: T) => string
    applyLabel?: string
    initialSelected?: string | null
  } = $props()

  type Pending = { kind: 'choice'; choice: PresetChoice<T> } | { kind: 'new' } | { kind: 'close' }
  let draft = $state<PresetDraft<T> | null>(null)
  let baseline = $state('')
  let selected = $state<string | null>(null)
  let encoder = $state('')
  let path = $state<string[]>([])
  let search = $state('')
  let pending = $state<Pending | null>(null)
  let deleting = $state(false)
  let busy = $state(false)
  let error = $state('')
  let notice = $state('')
  const dirty = $derived(!!draft && canonical(draft) !== baseline)
  const applyProblem = $derived(draft ? problem(draft.data) : '')
  const deleteLabel = $derived(choices.find(c => !c.builtin && c.name === draft?.name)?.label ?? choices.find(c => !c.builtin && c.name === draft?.name)?.name ?? draft?.label)
  const replacement = $derived(draft && !draft.name ? choices.find(c => !c.builtin
    && presetLabel(c) === draft!.label.trim() && parentOf(c.data) === parentOf(draft!.data)
    && canonical(c.group ?? []) === canonical(folderParts(draft!.folder))) : undefined)

  $effect(() => {
    // The manager edits a snapshot. Refreshed library data never replaces an open draft.
    if (draft === null) {
      const match = matchingPreset(choices, current, initialSelected)
      if (match) openChoice(match)
      else startNew()
    }
  })

  function setDraft(next: PresetDraft<T>, key: string | null) {
    draft = next
    baseline = canonical(next)
    selected = key
    pending = null
    deleting = false
    error = notice = ''
  }
  function openChoice(choice: PresetChoice<T>) {
    setDraft(draftFromChoice(structuredClone($state.snapshot(choice)) as PresetChoice<T>), presetKey(choice))
    encoder = parentOf(choice.data)
    path = [...(choice.group ?? [])]
  }
  function startNew() {
    setDraft(newPresetDraft($state.snapshot(current) as T), null)
    encoder = parentOf(current)
    path = []
    search = ''
  }
  function duplicate() {
    if (!draft || busy) return
    const next = duplicatePresetDraft($state.snapshot(draft) as PresetDraft<T>, choices, parentOf)
    setDraft(next, null)
    baseline = canonical(newPresetDraft(next.data, next.folder))
  }
  function proceed(action: Pending) {
    if (action.kind === 'choice') openChoice(action.choice)
    else if (action.kind === 'new') startNew()
    else onclose()
  }
  function request(action: Pending) {
    if (busy) return
    deleting = false
    if (dirty) pending = action
    else proceed(action)
  }
  function updateData(value: T) {
    if (draft && !busy) { draft.data = value; notice = ''; error = '' }
  }

  async function save(): Promise<boolean> {
    if (!draft || busy || !draft.label.trim()) return false
    busy = true
    error = notice = ''
    try {
      const payload = saveDestination($state.snapshot(draft) as PresetDraft<T>, choices, parentOf)
      const saved = await savePreset(payload)
      const choice = saved.find(c => !c.builtin && presetLabel(c) === payload.label
        && parentOf(c.data) === parentOf(payload.data) && canonical(c.group ?? []) === canonical(payload.group))
      if (!choice) throw new Error('The saved preset could not be found. Reopen the manager to refresh the library.')
      openChoice(choice)
      search = ''
      notice = 'Preset saved. Current job or template settings have not changed.'
      return true
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      return false
    } finally {
      busy = false
    }
  }
  async function resolve(saveFirst: boolean) {
    const action = pending
    if (!action) return
    if (saveFirst && !(await save())) return
    pending = null
    proceed(action)
  }
  async function applyDraft() {
    if (!draft || busy) return
    busy = true
    error = ''
    try {
      const data = structuredClone($state.snapshot(draft.data)) as T
      const reason = problem(data)
      if (reason) throw new Error(reason)
      await apply(data)
      const match = matchingPreset(choices, data, selected)
      onapplied(match ? presetKey(match) : null)
      onclose()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  async function remove() {
    if (!draft?.name || busy) return
    busy = true
    error = ''
    try {
      await removePreset(draft.name)
      startNew()
      notice = 'Preset deleted. Applied settings have not changed.'
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
</script>

<Dialog.Root open onOpenChange={value => { if (!value) request({ kind: 'close' }) }}>
  <Dialog.Content
    class="flex h-[min(52rem,calc(100dvh-2rem))] w-[calc(100vw-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl"
    showCloseButton={false}
    onInteractOutside={e => e.preventDefault()}
    onEscapeKeydown={e => { e.preventDefault(); e.stopPropagation(); request({ kind: 'close' }) }}
    onCloseAutoFocus={e => e.preventDefault()}
  >
    <Dialog.Header class="relative shrink-0 border-b p-4 pr-14">
      <Dialog.Title>{title} presets</Dialog.Title>
      <Dialog.Description>Edit and save library presets here. Apply settings separately to the current job or template.</Dialog.Description>
      <Button variant="ghost" size="icon-sm" class="absolute top-3 right-3" aria-label="Close preset manager" disabled={busy} onclick={() => request({ kind: 'close' })}><XIcon /></Button>
    </Dialog.Header>
    <div class="min-h-0 flex-1 overflow-y-auto md:grid md:grid-cols-[18rem_minmax(0,1fr)] md:grid-rows-1 md:overflow-hidden">
      <aside class="flex h-72 min-h-0 flex-col gap-3 overflow-y-auto border-b p-4 md:h-auto md:border-r md:border-b-0">
        <Button variant="outline" class="w-full shrink-0" disabled={busy} onclick={() => request({ kind: 'new' })}><PlusIcon />New from current settings</Button>
        <div class="flex min-h-52 flex-1 flex-col">
          <PresetBrowser {title} {choices} {parents} {parentOf} {summary} {problem} {builtinLabel} allowIncompatible
            bind:encoder bind:path bind:search {selected} disabled={busy} onselect={choice => request({ kind: 'choice', choice })} />
        </div>
      </aside>
      <section class="min-h-0 min-w-0 overscroll-contain p-4 md:overflow-y-auto" aria-label="Preset editor">
        {#if draft}
          <div class="mb-5 space-y-3 border-b pb-4">
            <div class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{draft.name ? 'Saved preset' : selected ? `${builtinLabel} · save as your own preset` : 'New preset'}</span>
              {#if dirty}<span class="text-warning">Unsaved changes</span>{/if}
              <div class="ml-auto flex items-center gap-1">
                <Button variant="ghost" size="sm" disabled={busy} onclick={duplicate}><CopyIcon />Duplicate</Button>
                {#if draft.name}<Button variant="ghost" size="sm" class="hover:text-destructive" disabled={busy} onclick={() => { deleting = true; pending = null }}><Trash2Icon />Delete preset</Button>{/if}
              </div>
            </div>
            <fieldset class="grid gap-3 sm:grid-cols-2" disabled={busy}>
              <label class="space-y-1 text-xs text-muted-foreground">Preset name
                <Input aria-label="{title} preset name" placeholder="e.g. {nameExample}" maxlength={80} bind:value={draft.label} />
              </label>
              <label class="space-y-1 text-xs text-muted-foreground">Folder
                <Input aria-label="{title} preset folder" placeholder="e.g. {folderExample}" bind:value={draft.folder} />
              </label>
            </fieldset>
            <p class="text-xs text-muted-foreground">{folderHint}</p>
          </div>
          <fieldset disabled={busy} class="min-w-0">{@render editor(draft.data, updateData)}</fieldset>
        {/if}
      </section>
    </div>
    {#if pending}
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-t border-warning/40 bg-warning/10 px-4 py-3 text-sm" role="alert">
        <span class="mr-auto">Save your preset changes before continuing?</span>
        <Button size="sm" disabled={busy || !draft?.label.trim()} onclick={() => resolve(true)}>Save and continue</Button>
        <Button size="sm" variant="outline" disabled={busy} onclick={() => resolve(false)}>Discard changes</Button>
        <Button size="sm" variant="ghost" disabled={busy} onclick={() => (pending = null)}>Keep editing</Button>
      </div>
    {:else if deleting}
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-t bg-muted/30 px-4 py-3 text-sm" role="alert">
        <span class="mr-auto">Delete “{deleteLabel}” from the preset library?</span>
        <Button size="sm" variant="destructive" disabled={busy} onclick={remove}>Delete preset</Button>
        <Button size="sm" variant="ghost" disabled={busy} onclick={() => (deleting = false)}>Keep preset</Button>
      </div>
    {/if}
    {#if error || notice || applyProblem}
      <div class="shrink-0 border-t px-4 py-2 text-xs">
        {#if error}<p class="text-destructive" role="alert">{error}</p>{/if}
        {#if notice}<p class="text-muted-foreground" role="status">{notice}</p>{/if}
        {#if applyProblem}<p class="text-warning">Cannot apply here: {applyProblem}</p>{/if}
      </div>
    {/if}
    <footer class="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t bg-muted/30 p-4">
      <Button variant="ghost" disabled={busy} onclick={onclose}>Cancel</Button>
      <Button variant="outline" disabled={busy || !draft?.label.trim() || (!!draft.name && !dirty)} onclick={save}><SaveIcon />{replacement ? 'Replace preset' : draft?.name ? 'Save preset' : 'Save new preset'}</Button>
      <Button disabled={busy || !draft || !!applyProblem} onclick={applyDraft}>{applyLabel}</Button>
    </footer>
  </Dialog.Content>
</Dialog.Root>
