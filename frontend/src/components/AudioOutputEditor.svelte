<script lang="ts">
  // One audio output in a template, with no source track to look at: copy or an encode (channels,
  // bitrate, the encode's settings), a title and flags. Empty fields keep what the job would do:
  // the source's title and flags, the encode's default channels and bitrate.
  import SlidersHorizontalIcon from '@lucide/svelte/icons/sliders-horizontal'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { shownOptions } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import TrackFlags from './TrackFlags.svelte'
  import type { AudioAction, EncodeOptionInfo, TrackOverride, TrackProperty } from '../lib/types'

  let {
    value,
    onchange,
    flags,
    label,
    disabled = false,
  }: {
    value: TrackOverride
    onchange: (v: TrackOverride) => void
    flags: TrackProperty[]
    label: string // for screen readers: "Track 1", "Track 1, extra output 1"
    disabled?: boolean
  } = $props()

  let settingsOpen = $state(false)
  const enc = $derived(app.encodes.find(e => e.id === value.action))
  const needs = (missing: string[]) => (missing.length ? ` (needs ${missing.join(', ')})` : '')
  const changed = $derived(Object.keys(value.options ?? {}).length)

  function set(change: (ov: TrackOverride) => void) {
    const next = structuredClone($state.snapshot(value)) as TrackOverride
    next.flags ??= {}
    next.options ??= {}
    change(next)
    onchange(next)
  }
  const setAction = (a: string) =>
    set(ov => {
      ov.action = a === 'copy' ? null : (a as AudioAction)
      ov.layout = ov.bitrate_kbps = null
      ov.options = {}
    })
  function setBitrate(v: string) {
    const n = Math.round(+v)
    set(ov => (ov.bitrate_kbps = v.trim() && n > 0 ? n : null))
  }
  const setOption = (o: EncodeOptionInfo, v: string) =>
    set(ov => {
      if (v.trim() === o.default || (!v.trim() && !o.choices.length && !o.range)) delete ov.options[o.key]
      else ov.options[o.key] = v.trim()
    })
</script>

<div class="space-y-2" role="group" aria-label={label}>
  <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
    <NativeSelect value={value.action ?? 'copy'} aria-label="Copy or encode" {disabled} onchange={e => setAction(e.currentTarget.value)}>
      <option value="copy">Copy</option>
      {#each app.encodes as e (e.id)}
        <option value={e.id}>Encode: {e.label}{needs(e.missing)}{e.id === 'atmos' ? ' (TrueHD Atmos sources)' : ''}</option>
      {/each}
    </NativeSelect>
    {#if enc && enc.layouts.length > 1}
      <NativeSelect value={value.layout ?? ''} aria-label="Channels" {disabled} onchange={e => set(ov => (ov.layout = e.currentTarget.value || null))}>
        <option value="">Channels: auto</option>
        {#each enc.layouts as l (l)}<option value={l}>{l}</option>{/each}
      </NativeSelect>
    {/if}
    {#if enc && enc.bitrates !== null}
      <label class="flex items-center gap-1.5 text-muted-foreground">
        {#if enc.bitrate_choices.length}
          <NativeSelect value={value.bitrate_kbps ?? ''} aria-label="Bitrate" {disabled} onchange={e => setBitrate(e.currentTarget.value)}>
            <option value="">auto</option>
            {#each enc.bitrate_choices as b (b)}<option value={b}>{b}</option>{/each}
          </NativeSelect>
        {:else}
          <Input
            class="w-24"
            type="number"
            min="6"
            step="8"
            placeholder={enc.vbr_default ? 'VBR' : 'auto'}
            value={value.bitrate_kbps ?? ''}
            aria-label="Bitrate"
            {disabled}
            onchange={e => setBitrate(e.currentTarget.value)}
          />
        {/if}kb/s
      </label>
    {/if}
    {#if enc?.options.length}
      <Button
        variant="ghost"
        size="sm"
        class={settingsOpen ? 'text-primary hover:text-primary' : ''}
        aria-expanded={settingsOpen}
        onclick={() => (settingsOpen = !settingsOpen)}
        title="{enc.label} settings"
      >
        <SlidersHorizontalIcon />Settings{changed ? ` (${changed})` : ''}
      </Button>
    {/if}
  </div>
  {#if enc?.options.length && settingsOpen}
    <div class="grid gap-x-4 gap-y-2 rounded-md border bg-muted/30 p-2 text-sm sm:grid-cols-[12rem_1fr]">
      {#each shownOptions(enc.options, o => value.options?.[o.key] ?? o.default) as o (o.key)}
        {@const v = value.options?.[o.key] ?? o.default}
        {@const id = `${label}-${o.key}`.replace(/\W+/g, '-')}
        <label class="text-muted-foreground" for={id} title={o.help}>{o.label}</label>
        <div class="flex items-center gap-2">
          {#if o.choices.length}
            <NativeSelect {id} value={v} {disabled} onchange={e => setOption(o, e.currentTarget.value)}>
              {#each o.choices as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
            </NativeSelect>
          {:else if o.range}
            <Input {id} class="w-24" type="number" min={o.range[0]} max={o.range[1]} step={o.step} value={v} {disabled} onchange={e => setOption(o, e.currentTarget.value)} />
          {:else}
            <Input {id} class="min-w-0 flex-1 font-mono text-xs" value={v} placeholder={o.help} {disabled} onchange={e => setOption(o, e.currentTarget.value)} />
          {/if}
          {#if o.help && (o.choices.length || o.range)}<span class="text-xs text-muted-foreground">{o.help}</span>{/if}
        </div>
      {/each}
    </div>
  {/if}
  <div class="flex flex-wrap items-center gap-2">
    <Input
      class="w-56"
      aria-label="Title"
      placeholder="Title: the source's"
      value={value.title ?? ''}
      {disabled}
      onchange={e => set(ov => (ov.title = e.currentTarget.value.trim() || null))}
    />
    <TrackFlags value={value.flags ?? {}} {flags} {disabled} onchange={f => set(ov => (ov.flags = f))} />
  </div>
</div>
