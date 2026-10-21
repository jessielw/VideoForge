<script lang="ts">
  // Encoder settings (x264 / x265, VP8 / VP9 through ffmpeg, SVT-AV1): rate control, preset, tune, bit depth, options, extra args.
  // Emits a fresh copy on every change; the parent decides when to save.
  import { ENCODERS, type EncoderName, type EncoderSettings, type RateControl, type SizeBudget, type VideoHdr } from '../lib/types'
  import type { Snippet } from 'svelte'
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
    presetControl,
    advancedCollapsed = false,
    disabled = false,
    colorArgs,
    hdr10plus,
    dv,
    budget,
  }: {
    value: EncoderSettings
    onchange: (v: EncoderSettings) => void
    presetControl?: Snippet
    advancedCollapsed?: boolean
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
  const hdr = $derived(
    !!colorArgs &&
      colorArgs.some(
        (a, i) =>
          (['--transfer', '-color_trc'].includes(colorArgs[i - 1]) && HDR_TRANSFERS.includes(a)) ||
          (colorArgs[i - 1] === '--transfer-characteristics' && ['16', '18'].includes(a)), // SVT-AV1's H.273 codes
      ),
  )

  const encoderLabel = $derived(ENCODERS.find(([e]) => e === value.encoder)?.[1] ?? value.encoder)
  // VP8 / VP9 run through ffmpeg (libvpx), as StaxRip's ffmpeg encoder does: its speed list is -cpu-used
  const vpx = $derived(value.encoder === 'vp8' || value.encoder === 'vp9')
  const svt = $derived(value.encoder === 'svtav1')
  // SvtAv1EncApp's CRF range, in quarter steps (encoders.SVTAV1_CRF)
  const SVT_CRF: [number, number] = [1, 70]
  const X26X_PRESETS: [string, string][] = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo'].map(
    p => [p, p],
  )
  const VPX_PRESETS: [string, string][] = [['6', '6 - Fastest'], ['5', '5 - Faster'], ['4', '4 - Fast'], ['3', '3 - Medium'], ['2', '2 - Slow'], ['1', '1 - Slower'], ['0', '0 - Slowest']]
  // StaxRip's names for SvtAv1EncApp's presets 0-13 (-1 is for debugging), fastest first
  const SVT_PRESETS: [string, string][] = [
    'Slowest', 'Extreme Slow', 'Ultra Slow', 'Very Slow', 'Slower', 'Slow', 'Medium', 'Fast', 'Faster', 'Very Fast', 'Mega Fast',
    'Ultra Fast', 'Extreme Fast', 'Fastest',
  ]
    .map((name, n): [string, string] => [String(n), `${n} - ${name}`])
    .reverse()
  const PRESETS: Record<EncoderName, [string, string][]> = {
    x264: X26X_PRESETS,
    x265: X26X_PRESETS,
    vp8: VPX_PRESETS,
    vp9: VPX_PRESETS,
    svtav1: SVT_PRESETS,
  }
  const DEFAULT_PRESET: Record<EncoderName, string> = { x264: 'slower', x265: 'slower', vp8: '1', vp9: '1', svtav1: '4' }
  const named = (names: string[]) => names.map((t): [string, string] => [t, t])
  // [value, label]
  const TUNES: Record<EncoderName, [string, string][]> = {
    x264: named(['film', 'animation', 'grain', 'stillimage', 'psnr', 'ssim', 'fastdecode', 'zerolatency']),
    x265: named(['animation', 'grain', 'psnr', 'ssim', 'fastdecode', 'zerolatency']),
    vp8: [],
    vp9: [],
    // SvtAv1EncApp's --tune (1, PSNR, is its default)
    svtav1: [['0', '0 - VQ'], ['1', '1 - PSNR'], ['2', '2 - SSIM'], ['3', '3 - Image quality'], ['4', '4 - MS-SSIM / SSIMULACRA2'], ['5', '5 - VMAF']],
  }
  const DEPTHS: Record<EncoderName, number[]> = { x264: [8, 10], x265: [8, 10, 12], vp8: [8], vp9: [8, 10, 12], svtav1: [8, 10] }
  // what encoders.VP9_DEFAULTS writes before the options (StaxRip's, plus row-mt)
  const VP9_DEFAULTS = '-tile-columns 6 -frame-parallel 1 -auto-alt-ref 1 -lag-in-frames 25 -row-mt 1'
  const dashes = $derived(vpx ? '-' : '--')

  let newKey = $state('')
  let newValue = $state('')

  function set<K extends keyof EncoderSettings>(key: K, v: EncoderSettings[K]) {
    const next: EncoderSettings = { ...value, options: { ...value.options }, [key]: v }
    if (key === 'encoder') {
      const enc = v as EncoderName
      if (!TUNES[enc].some(([t]) => t === next.tune)) next.tune = ''
      if (!DEPTHS[enc].includes(next.depth)) next.depth = 8
      if (next.preset && !PRESETS[enc].some(([p]) => p === next.preset)) next.preset = DEFAULT_PRESET[enc]
      if (enc === 'vp8' || enc === 'vp9') next.crf = Math.min(63, Math.round(next.crf))
      if (enc === 'svtav1') next.crf = Math.min(SVT_CRF[1], Math.max(SVT_CRF[0], Math.round(next.crf * 4) / 4))
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

<fieldset class="@container/encoder min-w-0 space-y-4" {disabled}>
  <!-- Respond to the panel's width: template cards can be narrow even in a wide window. -->
  <div class="grid grid-cols-[minmax(0,1fr)] items-center gap-x-4 gap-y-3 @min-[32rem]/encoder:grid-cols-[9rem_minmax(0,1fr)]">
    <span class="section-label">Encoder</span>
    <ToggleGroup.Root
      type="single"
      variant="outline"
      spacing={1}
      class="w-fit max-w-full flex-wrap"
      aria-label="Encoder"
      {disabled}
      value={value.encoder}
      onValueChange={v => v && set('encoder', v as EncoderName)}
    >
      {#each ENCODERS as [enc, label] (enc)}
        <ToggleGroup.Item value={enc} class="px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">{label}</ToggleGroup.Item>
      {/each}
    </ToggleGroup.Root>

    {#if presetControl}
      <span class="section-label">Encoder preset</span>
      <div class="min-w-0">{@render presetControl()}</div>
    {/if}

    <span class="section-label">Rate control</span>
    <div class="flex flex-wrap items-center gap-2">
      <NativeSelect value={value.rate_control} aria-label="Rate control" onchange={e => set('rate_control', e.currentTarget.value as RateControl)}>
        <option value="crf">CRF (constant quality)</option>
        <option value="abr">Bitrate, 1 pass</option>
        <option value="2pass">Bitrate, 2 passes</option>
      </NativeSelect>
      {#if value.rate_control === 'crf'}
        <Input
          class="w-24 max-w-full"
          type="number"
          aria-label="CRF"
          step={vpx ? 1 : svt ? 0.25 : 0.5}
          min={svt ? SVT_CRF[0] : 0}
          max={vpx ? 63 : svt ? SVT_CRF[1] : 51}
          value={value.crf}
          onchange={e => set('crf', +(e.target as HTMLInputElement).value)}
        />
      {:else if sized}
        <Input
          class="w-28 max-w-full"
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
          class="w-28 max-w-full"
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
      <span class="hidden @min-[32rem]/encoder:block"></span>
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

    <span class="section-label">Speed preset</span>
    <NativeSelect class="w-48 max-w-full" value={value.preset} aria-label="Speed preset" onchange={e => set('preset', e.currentTarget.value)}>
      <option value="">(encoder default)</option>
      {#each PRESETS[value.encoder] as [p, label] (p)}<option value={p}>{label}</option>{/each}
    </NativeSelect>

    {#if TUNES[value.encoder].length}
      <span class="section-label">Tune</span>
      <NativeSelect class="w-full max-w-sm" value={value.tune} aria-label="Tune" onchange={e => set('tune', e.currentTarget.value)}>
        <option value="">none</option>
        {#each TUNES[value.encoder] as [t, label] (t)}<option value={t}>{label}</option>{/each}
      </NativeSelect>
    {/if}

    <span class="section-label">Bit depth</span>
    <NativeSelect class="w-24 max-w-full" value={value.depth} aria-label="Bit depth" onchange={e => set('depth', +e.currentTarget.value)}>
      {#each DEPTHS[value.encoder] as d (d)}<option value={d}>{d}-bit</option>{/each}
    </NativeSelect>
  </div>

  <details open={!advancedCollapsed} class="rounded-lg border p-3">
    <summary class="cursor-pointer text-sm font-medium">Advanced settings and HDR</summary>
    <div class="space-y-4 pt-4">
  <label class="flex items-start gap-3 text-sm">
    <Checkbox class="mt-0.5" checked={value.source_color} {disabled} onCheckedChange={v => set('source_color', v)} />
    <span class="min-w-0">
      Colour from the source
      <span class="block text-xs text-muted-foreground">
        Tags the encode with the source's colour description{value.encoder === 'x265' || svt ? ' and HDR10 metadata' : ''}
        (vspipe passes none on){value.encoder === 'x265' ? ', with --repeat-headers --hrd --aud for HDR10 as StaxRip sets them' : ''}.
        {#if vpx}
          {value.encoder === 'vp9' ? 'VP9 holds the matrix and range in the stream' : 'VP8 holds none in the stream'}: the mux
          tags the container with the colour (and the pixel aspect). An HDR10 mastering display and light levels aren't carried yet.
        {:else if svt}
          AV1 holds them in the stream; the mux tags an MKV's track with them too (mkvmerge doesn't copy them), and the pixel
          aspect. An option below with the same flag wins.
        {:else}
          An option below with the same flag wins (--no-hrd turns one off).
        {/if}
        Untick it when the script changes the colours.
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
          <span class="mt-1 block text-xs text-warning">{encoderLabel} can't carry HDR10+: the encode keeps HDR10 only.</span>
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
          <span class="mt-1 block text-xs text-warning">{encoderLabel} can't carry Dolby Vision: the encode keeps the HDR10 layer.</span>
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
    <div class="section-label mb-2">Options ({dashes}name value, in order; an empty value is a flag)</div>
    {#if value.encoder === 'vp9'}
      <p class="mb-2 text-xs text-muted-foreground">
        ffmpeg's libvpx-vp9 options. Before them, StaxRip's VP9 defaults (one set here wins): <code class="font-mono">{VP9_DEFAULTS}</code>
      </p>
    {:else if vpx}
      <p class="mb-2 text-xs text-muted-foreground">ffmpeg's libvpx options.</p>
    {:else if svt}
      <p class="mb-2 text-xs text-muted-foreground">
        SvtAv1EncApp's options (--enable-variance-boost 1, --film-grain 8, ...). Before them, <code class="font-mono">--progress 2</code>
        (the progress the queue reads). The chapters' keyframes are forced in CRF only.
      </p>
    {/if}
    <div class="overflow-hidden rounded-lg border">
      {#each Object.entries(value.options) as [key, val] (key)}
        <div class="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2 border-b border-border/60 px-2 py-1 last:border-b-0">
          <span class="font-mono text-xs text-muted-foreground">{dashes}</span>
          <Input
            class="min-w-0 font-mono text-xs"
            value={key}
            aria-label="Option name"
            onchange={e => setOption(key, val, (e.target as HTMLInputElement).value.trim().replace(/^-+/, ''))}
          />
          <Input
            class="min-w-0 font-mono text-xs"
            value={val}
            aria-label="{dashes}{key} value"
            placeholder="(flag)"
            onchange={e => setOption(key, (e.target as HTMLInputElement).value.trim())}
          />
          <Button variant="ghost" size="icon-sm" class="text-muted-foreground hover:text-destructive" onclick={() => setOption(key, null)} aria-label="Remove">
            <XIcon />
          </Button>
        </div>
      {/each}
      <div class="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2 bg-muted/50 px-2 py-1">
        <span class="font-mono text-xs text-muted-foreground">{dashes}</span>
        <Input class="min-w-0 font-mono text-xs" placeholder="name" aria-label="New option name" bind:value={newKey} onkeydown={e => e.key === 'Enter' && addOption()} />
        <Input class="min-w-0 font-mono text-xs" placeholder="value" aria-label="New option value" bind:value={newValue} onkeydown={e => e.key === 'Enter' && addOption()} />
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
    </div>
  </details>
</fieldset>
