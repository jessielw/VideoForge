<script lang="ts">
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import Tip from './Tip.svelte'
  import { shownOptions } from '../lib/format'
  import { audioEncodeLayouts } from '../lib/audioPresets'
  import { app } from '../lib/state.svelte'
  import type { AudioAction, AudioPresetSettings, EncodeOptionInfo } from '../lib/types'

  let {
    value,
    onchange,
    disabled = false,
    editTitle = false,
  }: {
    value: AudioPresetSettings
    onchange: (value: AudioPresetSettings) => void
    disabled?: boolean
    editTitle?: boolean
  } = $props()
  const uid = $props.id()
  const enc = $derived(app.encodes.find((e) => e.id === value.action))
  const changed = $derived(Object.keys(value.options).length)

  function set(change: Partial<AudioPresetSettings>) {
    onchange({ ...value, options: { ...value.options }, ...change })
  }
  function setOption(option: EncodeOptionInfo, raw: string) {
    const options = { ...value.options }
    const v = raw.trim()
    if (v === option.default || (!v && !option.choices.length && !option.range)) delete options[option.key]
    else options[option.key] = v
    set({ options, ...(option.key === 'ddp_mode' && v === 'bluray' && value.layout !== '7.1' ? { layout: null } : {}) })
  }
</script>

<fieldset class="min-w-0 space-y-4" {disabled}>
  {#if editTitle}
    <label class="block space-y-1 text-xs text-muted-foreground"
      >Track title
      <Input
        aria-label="Track title"
        placeholder="Keep the track's title"
        value={value.title ?? ''}
        onchange={(e) => set({ title: e.currentTarget.value.trim() || null })}
      />
      <span class="block">Optional. A custom title is restored whenever this preset is selected.</span>
    </label>
  {/if}
  <div class="flex flex-wrap items-end gap-3">
    <label class="grid gap-1 text-xs text-muted-foreground"
      >Encoder
      <NativeSelect
        value={value.action}
        aria-label="Copy or encode"
        onchange={(e) =>
          set({ action: e.currentTarget.value as AudioAction, layout: null, bitrate_kbps: null, options: {} })}
      >
        <option value="copy">Copy</option>
        {#each app.encodes as e (e.id)}<option value={e.id}
            >{e.label}{e.missing.length ? ` (needs ${e.missing.join(', ')})` : ''}</option
          >{/each}
      </NativeSelect>
    </label>
    {#if enc}
      <label class="grid gap-1 text-xs text-muted-foreground"
        >Channels
        <NativeSelect
          value={value.layout ?? ''}
          aria-label="Channels"
          onchange={(e) => set({ layout: e.currentTarget.value || null })}
        >
          <option value="">Auto</option>
          {#each audioEncodeLayouts(enc, value.options) as layout (layout)}<option value={layout}>{layout}</option
            >{/each}
        </NativeSelect>
      </label>
      {#if enc.bitrates !== null}
        <label class="grid gap-1 text-xs text-muted-foreground"
          >Bitrate (kb/s)
          {#if enc.bitrate_choices.length}
            <NativeSelect
              value={value.bitrate_kbps ?? ''}
              aria-label="Bitrate"
              onchange={(e) => set({ bitrate_kbps: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
            >
              <option value="">Auto</option>
              {#each enc.bitrate_choices as bitrate (bitrate)}<option value={bitrate}>{bitrate}</option>{/each}
            </NativeSelect>
          {:else}
            <Input
              class="w-28"
              type="number"
              min={enc.bitrate_range?.[0] ?? 1}
              max={enc.bitrate_range?.[1]}
              step="1"
              aria-label="Bitrate"
              placeholder={enc.vbr_default ? 'VBR' : 'Auto'}
              value={value.bitrate_kbps ?? ''}
              onchange={(e) =>
                set({ bitrate_kbps: e.currentTarget.value.trim() ? Math.round(Number(e.currentTarget.value)) : null })}
            />
          {/if}
        </label>
      {/if}
    {/if}
  </div>
  {#if value.action === 'copy'}<p class="text-sm text-muted-foreground">
      Copy the source audio without re-encoding.
    </p>{/if}
  {#if enc?.options.length}
    <details class="rounded-lg border bg-muted/20">
      <summary class="cursor-pointer px-3 py-2 text-sm font-medium"
        >Advanced settings{changed ? ` (${changed})` : ''}</summary
      >
      <div class="grid min-w-0 gap-x-4 gap-y-3 border-t p-3 text-sm sm:grid-cols-[12rem_minmax(0,1fr)]">
        {#each shownOptions(enc.options, (o) => value.options[o.key] ?? o.default) as o (o.key)}
          {@const v = value.options[o.key] ?? o.default}
          {@const id = `${uid}-${o.key}`}
          <Tip text={o.help}><label class="text-muted-foreground" for={id}>{o.label}</label></Tip>
          <div class="min-w-0 space-y-1">
            {#if o.choices.length}
              <NativeSelect {id} value={v} onchange={(e) => setOption(o, e.currentTarget.value)}>
                {#each o.choices as choice (choice.value)}<option value={choice.value}>{choice.label}</option>{/each}
              </NativeSelect>
            {:else if o.range}
              <Input
                {id}
                class="w-28"
                type="number"
                min={o.range[0]}
                max={o.range[1]}
                step={o.step}
                value={v}
                onchange={(e) => setOption(o, e.currentTarget.value)}
              />
            {:else}
              <Input
                {id}
                class="w-full min-w-0 font-mono text-xs"
                value={v}
                placeholder={o.help}
                onchange={(e) => setOption(o, e.currentTarget.value)}
              />
            {/if}
            {#if o.help}<p class="text-xs text-muted-foreground">{o.help}</p>{/if}
          </div>
        {/each}
      </div>
    </details>
  {/if}
</fieldset>
