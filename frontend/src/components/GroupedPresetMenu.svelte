<script lang="ts" generics="T">
  import { tick, type Snippet } from 'svelte'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import SettingsIcon from '@lucide/svelte/icons/settings'
  import { Button } from '$lib/components/ui/button'
  import * as Popover from '$lib/components/ui/popover'
  import PresetBrowser from './PresetBrowser.svelte'
  import PresetManager from './PresetManager.svelte'
  import { matchingPreset, presetKey, presetLabel, type PresetChoice, type PresetDraft } from '../lib/presetDraft'

  let {
    title,
    current,
    choices,
    parents,
    parentOf,
    summary,
    apply,
    savePreset,
    removePreset,
    removePresets,
    editor,
    folderExample,
    nameExample,
    folderHint = 'Use / for nested folders.',
    builtinLabel = 'built-in',
    problem = () => '',
    showTitle = false,
    applyLabel = 'Apply settings',
    disabled = false,
    transfer,
    manageOnly = false,
  }: {
    title: string
    current: T
    choices: PresetChoice<T>[]
    parents: [string, string][]
    parentOf: (settings: T) => string
    summary: (settings: T) => string
    apply: (settings: T) => void | Promise<void>
    savePreset: (preset: { name?: string; label: string; group: string[]; data: T }) => Promise<PresetChoice<T>[]>
    removePreset: (name: string) => Promise<void>
    removePresets?: (names: string[]) => Promise<void>
    editor: Snippet<[T, (value: T) => void]>
    folderExample: string
    nameExample: string
    folderHint?: string
    builtinLabel?: string
    problem?: (settings: T) => string
    showTitle?: boolean
    applyLabel?: string
    disabled?: boolean
    manageOnly?: boolean
    transfer?: Snippet<[PresetDraft<T> | null, boolean]>
  } = $props()

  let open = $state(false)
  let managerOpen = $state(false)
  let trigger = $state<HTMLButtonElement | null>(null)
  let encoder = $state('')
  let path = $state<string[]>([])
  let search = $state('')
  let selected = $state<string | null>(null)
  let busy = $state(false)
  let error = $state('')
  const matched = $derived(matchingPreset(choices, current, selected))
  const currentLabel = $derived(
    matched ? [...(matched.group ?? []), presetLabel(matched)].join(' / ') : 'Custom / modified',
  )
  $effect(() => {
    if (disabled) {
      open = false
      managerOpen = false
    }
  })

  function setOpen(value: boolean) {
    open = value
    if (value) {
      encoder = ''
      path = []
      search = error = ''
    }
  }
  async function load(choice: PresetChoice<T>) {
    busy = true
    error = ''
    try {
      const data = structuredClone($state.snapshot(choice.data)) as T
      const reason = problem(data)
      if (reason) throw new Error(reason)
      await apply(data)
      selected = presetKey(choice)
      open = false
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      busy = false
    }
  }
  async function closeManager() {
    managerOpen = false
    await tick()
    trigger?.focus()
  }
</script>

{#if manageOnly}
  <Button bind:ref={trigger} variant="outline" {disabled} onclick={() => (managerOpen = true)}
    ><SettingsIcon />Manage {title === 'Audio' ? 'audio' : 'video encoder'} presets</Button
  >
{:else}
  <Popover.Root {open} onOpenChange={setOpen}>
    <Popover.Trigger {disabled} title={currentLabel}>
      {#snippet child({ props })}
        <Button {...props} bind:ref={trigger} variant="outline" class="max-w-full" aria-label="{title} presets">
          <span class="truncate">{showTitle ? `${title} preset: ` : ''}{currentLabel}</span><ChevronDownIcon />
        </Button>
      {/snippet}
    </Popover.Trigger>
    <Popover.Content
      align="start"
      collisionPadding={8}
      class="max-h-[min(28rem,var(--bits-popover-content-available-height))] w-96 max-w-[calc(100vw-2rem)] gap-3 overflow-hidden p-3"
      onEscapeKeydown={(e) => e.stopPropagation()}
      onCloseAutoFocus={(e) => {
        if (managerOpen) e.preventDefault()
      }}
    >
      <PresetBrowser
        {title}
        {choices}
        {parents}
        {parentOf}
        {summary}
        {problem}
        {builtinLabel}
        bind:encoder
        bind:path
        bind:search
        selected={matched ? presetKey(matched) : null}
        disabled={busy}
        onselect={load}
      />
      {#if error}<p class="shrink-0 text-xs text-destructive" role="alert">{error}</p>{/if}
      <div class="shrink-0 border-t pt-2">
        <Button
          variant="ghost"
          class="w-full justify-start"
          disabled={busy}
          onclick={() => {
            open = false
            managerOpen = true
          }}><SettingsIcon />Manage presets…</Button
        >
      </div>
    </Popover.Content>
  </Popover.Root>
{/if}

{#if managerOpen}
  <PresetManager
    {title}
    {current}
    {choices}
    {parents}
    {parentOf}
    {summary}
    {problem}
    {builtinLabel}
    {editor}
    {nameExample}
    {folderExample}
    {folderHint}
    {apply}
    {savePreset}
    {removePreset}
    {removePresets}
    {applyLabel}
    {transfer}
    {manageOnly}
    initialSelected={matched ? presetKey(matched) : null}
    onclose={closeManager}
    onapplied={(key) => (selected = key)}
  />
{/if}
