<script lang="ts">
  // Encoder settings (x264 / x265): rate control, preset, tune, bit depth, --options, extra args.
  // Emits a fresh copy on every change; the parent decides when to save.
  import type { EncoderName, EncoderSettings, RateControl, VideoHdr } from '../lib/types'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'

  // colorArgs: the job's source's colour flags for this encoder; hdr10plus: whether the source has HDR10+; dv: its
  // Dolby Vision (false: none) (the job editor; null until probed, absent in the batch panel and on the Templates
  // page, which have no one source)
  let {
    value,
    onchange,
    disabled = false,
    colorArgs,
    hdr10plus,
    dv,
  }: {
    value: EncoderSettings
    onchange: (v: EncoderSettings) => void
    disabled?: boolean
    colorArgs?: string[] | null
    hdr10plus?: boolean | null
    dv?: VideoHdr | false | null
  } = $props()

  const vbv = $derived('vbv-maxrate' in value.options && 'vbv-bufsize' in value.options)

  const HDR_TRANSFERS = ['smpte2084', 'arib-std-b67'] // PQ, HLG
  const hdr = $derived(!!colorArgs && colorArgs.some((a, i) => colorArgs[i - 1] === '--transfer' && HDR_TRANSFERS.includes(a)))

  const PRESETS = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo']
  const TUNES: Record<EncoderName, string[]> = {
    x264: ['film', 'animation', 'grain', 'stillimage', 'psnr', 'ssim', 'fastdecode', 'zerolatency'],
    x265: ['animation', 'grain', 'psnr', 'ssim', 'fastdecode', 'zerolatency'],
  }
  const DEPTHS: Record<EncoderName, number[]> = { x264: [8, 10], x265: [8, 10, 12] }

  let newKey = $state('')
  let newValue = $state('')

  function set<K extends keyof EncoderSettings>(key: K, v: EncoderSettings[K]) {
    const next: EncoderSettings = { ...value, options: { ...value.options }, [key]: v }
    if (key === 'encoder') {
      const enc = v as EncoderName
      if (!TUNES[enc].includes(next.tune)) next.tune = ''
      if (!DEPTHS[enc].includes(next.depth)) next.depth = 8
    }
    onchange(next)
  }

  function setOption(key: string, v: string | null, rename?: string) {
    const entries = Object.entries(value.options).flatMap(([k, val]) => {
      if (k !== key) return [[k, val]]
      if (v === null) return []
      return [[rename ?? k, v]]
    })
    onchange({ ...value, options: Object.fromEntries(entries) })
  }

  function addOption() {
    const key = newKey.trim().replace(/^-+/, '')
    if (!key) return
    onchange({ ...value, options: { ...value.options, [key]: newValue.trim() } })
    newKey = newValue = ''
  }
</script>

<fieldset class="space-y-4" {disabled}>
  <div class="grid grid-cols-[9rem_1fr] items-center gap-x-4 gap-y-3">
    <span class="section-label">Encoder</span>
    <ToggleGroup.Root
      type="single"
      variant="outline"
      class="w-fit"
      {disabled}
      value={value.encoder}
      onValueChange={v => v && set('encoder', v as EncoderName)}
    >
      {#each ['x264', 'x265'] as enc (enc)}
        <ToggleGroup.Item value={enc} class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{enc}</ToggleGroup.Item>
      {/each}
    </ToggleGroup.Root>

    <span class="section-label">Rate control</span>
    <div class="flex flex-wrap items-center gap-2">
      <NativeSelect value={value.rate_control} aria-label="Rate control" onchange={e => set('rate_control', e.currentTarget.value as RateControl)}>
        <option value="crf">CRF (constant quality)</option>
        <option value="abr">Bitrate, 1 pass</option>
        <option value="2pass">Bitrate, 2 passes</option>
      </NativeSelect>
      {#if value.rate_control === 'crf'}
        <Input
          class="w-24"
          type="number"
          aria-label="CRF"
          step="0.5"
          min="0"
          max="51"
          value={value.crf}
          onchange={e => set('crf', +(e.target as HTMLInputElement).value)}
        />
      {:else}
        <Input
          class="w-28"
          type="number"
          aria-label="Bitrate"
          step="100"
          min="100"
          value={value.bitrate_kbps}
          onchange={e => set('bitrate_kbps', +(e.target as HTMLInputElement).value)}
        /><span class="text-sm text-muted-foreground">kb/s</span>
      {/if}
    </div>

    <span class="section-label">Preset</span>
    <NativeSelect class="w-48" value={value.preset} aria-label="Preset" onchange={e => set('preset', e.currentTarget.value)}>
      <option value="">(encoder default)</option>
      {#each PRESETS as p (p)}<option value={p}>{p}</option>{/each}
    </NativeSelect>

    <span class="section-label">Tune</span>
    <NativeSelect class="w-48" value={value.tune} aria-label="Tune" onchange={e => set('tune', e.currentTarget.value)}>
      <option value="">none</option>
      {#each TUNES[value.encoder] as t (t)}<option value={t}>{t}</option>{/each}
    </NativeSelect>

    <span class="section-label">Bit depth</span>
    <NativeSelect class="w-24" value={value.depth} aria-label="Bit depth" onchange={e => set('depth', +e.currentTarget.value)}>
      {#each DEPTHS[value.encoder] as d (d)}<option value={d}>{d}-bit</option>{/each}
    </NativeSelect>
  </div>

  <label class="flex items-start gap-3 text-sm">
    <Checkbox class="mt-0.5" checked={value.source_color} {disabled} onCheckedChange={v => set('source_color', v)} />
    <span class="min-w-0">
      Colour from the source
      <span class="block text-xs text-muted-foreground">
        Tags the encode with the source's colour description{value.encoder === 'x265' ? ' and HDR10 metadata' : ''}
        (vspipe passes none on). An option below with the same flag wins. Untick it when the script changes the colours.
      </span>
      {#if colorArgs !== undefined}
        {#if colorArgs === null}
          <span class="block text-xs text-muted-foreground">Known once the source is probed.</span>
        {:else if !colorArgs.length}
          <span class="block text-xs text-muted-foreground">The source doesn't describe its colours.</span>
        {:else}
          <code class="mt-1 block font-mono text-xs break-all {value.source_color ? '' : 'text-muted-foreground line-through'}"
            >{colorArgs.join(' ')}</code
          >
        {/if}
        {#if hdr && value.source_color && value.depth < 10}
          <span class="mt-1 block text-xs text-warning">An HDR source: encode it at 10-bit.</span>
        {/if}
      {/if}
    </span>
  </label>

  <label class="flex items-start gap-3 text-sm">
    <Checkbox class="mt-0.5" checked={value.hdr10plus} {disabled} onCheckedChange={v => set('hdr10plus', v)} />
    <span class="min-w-0">
      HDR10+ from the source
      <span class="block text-xs text-muted-foreground">
        x265: carries a source's HDR10+ metadata into the encode (hdr10plus_tool reads it, x265's --dhdr10-info writes it). Needs a
        10-bit encode and a script that keeps every frame (no trims).
      </span>
      {#if hdr10plus !== undefined}
        {#if hdr10plus === null}
          <span class="block text-xs text-muted-foreground">Known once the source is probed.</span>
        {:else if !hdr10plus}
          <span class="block text-xs text-muted-foreground">The source has no HDR10+.</span>
        {:else if value.encoder !== 'x265'}
          <span class="mt-1 block text-xs text-warning">x264 can't carry HDR10+: the encode keeps HDR10 only.</span>
        {:else}
          <code class="mt-1 block font-mono text-xs break-all {value.hdr10plus ? '' : 'text-muted-foreground line-through'}"
            >--dhdr10-info hdr10plus.json</code
          >
          {#if value.hdr10plus && value.depth < 10}
            <span class="mt-1 block text-xs text-warning">HDR10+ needs a 10-bit encode.</span>
          {/if}
        {/if}
      {/if}
    </span>
  </label>

  <label class="flex items-start gap-3 text-sm">
    <Checkbox class="mt-0.5" checked={value.dolby_vision} {disabled} onCheckedChange={v => set('dolby_vision', v)} />
    <span class="min-w-0">
      Dolby Vision from the source
      <span class="block text-xs text-muted-foreground">
        x265: carries a source's Dolby Vision into the encode as profile 8.1 (dovi_tool reads the RPU and moves its active
        area with the crop and resize). Needs a 10-bit encode, --vbv-maxrate and --vbv-bufsize, and a script that keeps every
        frame. A FEL's enhancement layer is baked into the picture first (felbaker). Profile 5 and 8.4 (HLG) aren't
        carried yet.
      </span>
      {#if dv !== undefined}
        {#if dv === null}
          <span class="block text-xs text-muted-foreground">Known once the source is probed.</span>
        {:else if !dv || !dv.dv_profile}
          <span class="block text-xs text-muted-foreground">The source has no Dolby Vision.</span>
        {:else if dv.dv_profile === 5}
          <span class="mt-1 block text-xs text-warning">Profile 5 has no HDR10 layer to encode: not supported yet.</span>
        {:else if value.encoder !== 'x265'}
          <span class="mt-1 block text-xs text-warning">x264 can't carry Dolby Vision: the encode keeps the HDR10 layer.</span>
        {:else}
          <code class="mt-1 block font-mono text-xs break-all {value.dolby_vision ? '' : 'text-muted-foreground line-through'}"
            >--dolby-vision-profile 8.1 --dolby-vision-rpu dv_rpu.bin</code
          >
          {#if value.dolby_vision}
            {#if dv.dv_compat === 4}
              <span class="mt-1 block text-xs text-warning">Dolby Vision 8.4 (HLG) isn't carried yet: untick it to keep the HLG layer.</span>
            {/if}
            {#if dv.dv_profile === 7 && dv.dv_el === 'FEL'}
              <span class="mt-1 block text-xs text-muted-foreground">FEL: its enhancement layer is baked into the picture (FFMS2 or L-SMASH), and the HDR10 values come from the RPU.</span>
            {:else if dv.dv_profile === 7 && dv.dv_el !== 'MEL'}
              <span class="mt-1 block text-xs text-warning">The enhancement layer's kind (FEL or MEL) couldn't be read: untick it to keep the base layer.</span>
            {/if}
            {#if value.depth !== 10}
              <span class="mt-1 block text-xs text-warning">Dolby Vision needs a 10-bit encode.</span>
            {/if}
            {#if !vbv}
              <span class="mt-1 block text-xs text-warning">Add --vbv-maxrate and --vbv-bufsize below (x265 needs VBV for Dolby Vision).</span>
            {/if}
          {/if}
        {/if}
      {/if}
    </span>
  </label>

  <div>
    <div class="section-label mb-2">Options (--name value, in order; an empty value is a flag)</div>
    <div class="overflow-hidden rounded-lg border">
      {#each Object.entries(value.options) as [key, val] (key)}
        <div class="flex items-center gap-2 border-b border-border/60 px-2 py-1 last:border-b-0">
          <span class="font-mono text-xs text-muted-foreground">--</span>
          <Input
            class="w-44 font-mono text-xs"
            value={key}
            aria-label="Option name"
            onchange={e => setOption(key, val, (e.target as HTMLInputElement).value.trim().replace(/^-+/, ''))}
          />
          <Input
            class="flex-1 font-mono text-xs"
            value={val}
            aria-label="--{key} value"
            placeholder="(flag)"
            onchange={e => setOption(key, (e.target as HTMLInputElement).value.trim())}
          />
          <Button variant="ghost" size="icon-sm" class="text-muted-foreground hover:text-destructive" onclick={() => setOption(key, null)} aria-label="Remove">
            <XIcon />
          </Button>
        </div>
      {/each}
      <div class="flex items-center gap-2 bg-muted/50 px-2 py-1">
        <span class="font-mono text-xs text-muted-foreground">--</span>
        <Input class="w-44 font-mono text-xs" placeholder="name" aria-label="New option name" bind:value={newKey} onkeydown={e => e.key === 'Enter' && addOption()} />
        <Input class="flex-1 font-mono text-xs" placeholder="value" aria-label="New option value" bind:value={newValue} onkeydown={e => e.key === 'Enter' && addOption()} />
        <Button variant="ghost" size="icon-sm" onclick={addOption} aria-label="Add"><PlusIcon /></Button>
      </div>
    </div>
  </div>

  <label class="block">
    <span class="section-label">Extra arguments</span>
    <Input
      class="mt-1 w-full font-mono text-xs"
      value={value.extra}
      placeholder="appended as typed"
      onchange={e => set('extra', (e.target as HTMLInputElement).value)}
    />
  </label>
</fieldset>
