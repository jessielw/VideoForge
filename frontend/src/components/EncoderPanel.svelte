<script lang="ts">
  // Encoder settings (x264 / x265): rate control, preset, tune, bit depth, --options, extra args.
  // Emits a fresh copy on every change; the parent decides when to save.
  import type { EncoderName, EncoderSettings, RateControl, SizeBudget, VideoHdr } from '../lib/types'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'

  // colorArgs: the job's source's colour flags for this encoder; hdr10plus: whether the source has HDR10+; dv: its
  // Dolby Vision (false: none); budget: where a 2-pass target size goes (the job editor; null until probed or
  // planned, absent in the batch panel and on the Templates page, which have no one source)
  let {
    value,
    onchange,
    disabled = false,
    colorArgs,
    hdr10plus,
    dv,
    budget,
  }: {
    value: EncoderSettings
    onchange: (v: EncoderSettings) => void
    disabled?: boolean
    colorArgs?: string[] | null
    hdr10plus?: boolean | null
    dv?: VideoHdr | false | null
    budget?: SizeBudget | null
  } = $props()

  // StaxRip's size menu (MB) and its default target size
  const SIZES: [number, string][] = [[4700, 'DVD / BD-5'], [8540, 'DVD-DL / BD-9'], [25000, 'BD'], [50000, 'BD-DL']]
  const DEFAULT_SIZE = 5000
  const sized = $derived(value.rate_control === '2pass' && value.target_mb !== null)

  const mb = (bytes: number) => `${Math.round(bytes / 1e6).toLocaleString()} MB`
  function duration(seconds: number) {
    const s = Math.round(seconds)
    return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
  }
  // what the target size takes away from the video, the parts that have any
  const spent = $derived(
    budget
      ? (
          [
            ['audio', budget.audio],
            ['subtitles', budget.subs],
            ['attachments', budget.attachments],
            ['HDR metadata', budget.metadata],
            ['container overhead', budget.overhead],
          ] as [string, number][]
        )
          .filter(([, n]) => n > 0)
          .map(([what, n]) => `${what} ${mb(n)}`)
      : [],
  )

  // H.265 MaxBR (kb/s) by level x 10, [Main tier, High tier]: Dolby Vision fills a missing --vbv-maxrate /
  // --vbv-bufsize from --level-idc (High tier unless --no-high-tier), as encoders.level_vbv does
  const LEVEL_KBPS: Record<number, [number, number]> = {
    10: [128, 128], 20: [1500, 1500], 21: [3000, 3000], 30: [6000, 6000], 31: [10000, 10000], 40: [12000, 30000],
    41: [20000, 50000], 50: [25000, 100000], 51: [40000, 160000], 52: [60000, 240000], 60: [60000, 240000],
    61: [120000, 480000], 62: [240000, 800000],
  }
  // the VBV flags filled from the level ([] when both are set, null when one is missing and the level can't fill it)
  const levelVbv = $derived.by(() => {
    const missing = ['vbv-maxrate', 'vbv-bufsize'].filter(f => !value.options[f])
    if (!missing.length) return []
    const level = parseFloat(value.options['level-idc'] ?? '')
    const kbps = LEVEL_KBPS[level < 10 ? Math.round(10 * level) : Math.trunc(level)]
    if (!kbps) return null
    const rate = 'no-high-tier' in value.options ? kbps[0] : kbps[1]
    return missing.flatMap(f => [`--${f}`, String(rate)])
  })

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
      {:else if sized}
        <Input
          class="w-28"
          type="number"
          aria-label="Target size"
          list="target-sizes"
          step="100"
          min="1"
          value={value.target_mb}
          onchange={e => {
            const n = Math.round(+(e.target as HTMLInputElement).value)
            set('target_mb', n > 0 ? n : DEFAULT_SIZE)
          }}
        />
        <datalist id="target-sizes">
          {#each SIZES as [size, label] (size)}<option value={size}>{label}</option>{/each}
        </datalist>
      {:else}
        <Input
          class="w-28"
          type="number"
          aria-label="Bitrate"
          step="100"
          min="100"
          value={value.bitrate_kbps}
          onchange={e => set('bitrate_kbps', +(e.target as HTMLInputElement).value)}
        />
      {/if}
      {#if value.rate_control === '2pass'}
        <NativeSelect
          value={sized ? 'mb' : 'kbps'}
          aria-label="Bitrate or size"
          onchange={e => set('target_mb', e.currentTarget.value === 'mb' ? DEFAULT_SIZE : null)}
        >
          <option value="kbps">kb/s</option>
          <option value="mb">MB (file size)</option>
        </NativeSelect>
      {:else if value.rate_control === 'abr'}
        <span class="text-sm text-muted-foreground">kb/s</span>
      {/if}
    </div>
    {#if sized}
      <span></span>
      <div class="text-xs text-muted-foreground">
        The video gets what the size leaves: less the audio, subtitles, attachments, HDR metadata and container overhead, over
        the length (StaxRip's sum). Pass 2 counts the encoded audio's files.
        {#if budget === null}
          <span class="block">Worked out once the job is planned.</span>
        {:else if budget}
          <span class="mt-1 block text-foreground">
            ≈ {budget.kbps.toLocaleString()} kb/s for the video ({mb(budget.video)} over {duration(budget.seconds)}){spent.length
              ? `: ${mb(budget.target)} less ${spent.join(', ')}`
              : ''}
          </span>
          {#if budget.video <= 0}
            <span class="mt-1 block text-destructive">The size leaves nothing for the video.</span>
          {/if}
          {#if budget.unknown.length}
            <span class="mt-1 block text-warning">Not counted (size not known): {budget.unknown.join(', ')}.</span>
          {/if}
        {/if}
      </div>
    {/if}

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
        (vspipe passes none on){value.encoder === 'x265' ? ', with --repeat-headers --hrd --aud for HDR10 as StaxRip sets them' : ''}.
        An option below with the same flag wins (--no-hrd turns one off). Untick it when the script changes the colours.
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
        x265: carries a source's Dolby Vision into the encode as profile 8.1, or a profile 5 as 5 (dovi_tool reads the RPU and moves its active
        area with the crop and resize). Needs a 10-bit encode, --vbv-maxrate and --vbv-bufsize (or --level-idc, whose max
        bitrate fills the ones not set), and a script that keeps every
        frame. A FEL's enhancement layer is baked into the picture first (felbaker). 8.4 (HLG) isn't carried yet.
      </span>
      {#if dv !== undefined}
        {#if dv === null}
          <span class="block text-xs text-muted-foreground">Known once the source is probed.</span>
        {:else if !dv || !dv.dv_profile}
          <span class="block text-xs text-muted-foreground">The source has no Dolby Vision.</span>
        {:else if dv.dv_profile === 5 && (value.encoder !== 'x265' || !value.dolby_vision)}
          <span class="mt-1 block text-xs text-warning">Profile 5 has no HDR10 layer: without its RPU the encode's colours look wrong, unless the script maps them.</span>
        {:else if value.encoder !== 'x265'}
          <span class="mt-1 block text-xs text-warning">x264 can't carry Dolby Vision: the encode keeps the HDR10 layer.</span>
        {:else}
          <code class="mt-1 block font-mono text-xs break-all {value.dolby_vision ? '' : 'text-muted-foreground line-through'}"
            >--dolby-vision-profile {dv.dv_profile === 5 ? '5' : '8.1'} --dolby-vision-rpu dv_rpu.bin{levelVbv?.length ? ' ' + levelVbv.join(' ') : ''}</code
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
            {#if levelVbv === null}
              <span class="mt-1 block text-xs text-warning"
                >Add --vbv-maxrate and --vbv-bufsize below, or --level-idc to fill them with its max bitrate (x265 needs VBV for Dolby
                Vision).</span
              >
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
