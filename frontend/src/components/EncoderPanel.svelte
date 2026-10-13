<script lang="ts">
  // Encoder settings (x264 / x265): rate control, preset, tune, bit depth, --options, extra args.
  // Emits a fresh copy on every change; the parent decides when to save.
  import type { EncoderName, EncoderSettings, RateControl } from '../lib/types'
  import Icon from './Icon.svelte'

  let {
    value,
    onchange,
    disabled = false,
  }: { value: EncoderSettings; onchange: (v: EncoderSettings) => void; disabled?: boolean } = $props()

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
    <span class="label">Encoder</span>
    <div class="flex gap-2">
      {#each ['x264', 'x265'] as enc (enc)}
        <button
          class="btn {value.encoder === enc ? 'border-accent text-accent' : ''}"
          onclick={() => set('encoder', enc as EncoderName)}>{enc}</button
        >
      {/each}
    </div>

    <span class="label">Rate control</span>
    <div class="flex flex-wrap items-center gap-2">
      <select class="field" value={value.rate_control} onchange={e => set('rate_control', (e.target as HTMLSelectElement).value as RateControl)}>
        <option value="crf">CRF (constant quality)</option>
        <option value="abr">Bitrate, 1 pass</option>
        <option value="2pass">Bitrate, 2 passes</option>
      </select>
      {#if value.rate_control === 'crf'}
        <input
          class="field w-24"
          type="number"
          step="0.5"
          min="0"
          max="51"
          value={value.crf}
          onchange={e => set('crf', +(e.target as HTMLInputElement).value)}
        />
      {:else}
        <input
          class="field w-28"
          type="number"
          step="100"
          min="100"
          value={value.bitrate_kbps}
          onchange={e => set('bitrate_kbps', +(e.target as HTMLInputElement).value)}
        /><span class="text-sm text-muted">kb/s</span>
      {/if}
    </div>

    <span class="label">Preset</span>
    <select class="field w-48" value={value.preset} onchange={e => set('preset', (e.target as HTMLSelectElement).value)}>
      <option value="">(encoder default)</option>
      {#each PRESETS as p (p)}<option value={p}>{p}</option>{/each}
    </select>

    <span class="label">Tune</span>
    <select class="field w-48" value={value.tune} onchange={e => set('tune', (e.target as HTMLSelectElement).value)}>
      <option value="">none</option>
      {#each TUNES[value.encoder] as t (t)}<option value={t}>{t}</option>{/each}
    </select>

    <span class="label">Bit depth</span>
    <select class="field w-24" value={value.depth} onchange={e => set('depth', +(e.target as HTMLSelectElement).value)}>
      {#each DEPTHS[value.encoder] as d (d)}<option value={d}>{d}-bit</option>{/each}
    </select>
  </div>

  <div>
    <div class="label mb-2">Options (--name value, in order; an empty value is a flag)</div>
    <div class="overflow-hidden rounded-md border border-line">
      {#each Object.entries(value.options) as [key, val] (key)}
        <div class="flex items-center gap-2 border-b border-line/60 px-2 py-1 last:border-b-0">
          <span class="font-mono text-xs text-muted">--</span>
          <input
            class="field w-44 font-mono text-xs"
            value={key}
            onchange={e => setOption(key, val, (e.target as HTMLInputElement).value.trim().replace(/^-+/, ''))}
          />
          <input
            class="field flex-1 font-mono text-xs"
            value={val}
            placeholder="(flag)"
            onchange={e => setOption(key, (e.target as HTMLInputElement).value.trim())}
          />
          <button class="btn-ghost px-1.5 text-muted hover:text-bad" onclick={() => setOption(key, null)} aria-label="Remove">
            <Icon name="x" size={14} />
          </button>
        </div>
      {/each}
      <div class="flex items-center gap-2 bg-raised/50 px-2 py-1">
        <span class="font-mono text-xs text-muted">--</span>
        <input class="field w-44 font-mono text-xs" placeholder="name" bind:value={newKey} onkeydown={e => e.key === 'Enter' && addOption()} />
        <input class="field flex-1 font-mono text-xs" placeholder="value" bind:value={newValue} onkeydown={e => e.key === 'Enter' && addOption()} />
        <button class="btn-ghost px-1.5" onclick={addOption} aria-label="Add"><Icon name="new" size={14} /></button>
      </div>
    </div>
  </div>

  <label class="block">
    <span class="label">Extra arguments</span>
    <input
      class="field mt-1 w-full font-mono text-xs"
      value={value.extra}
      placeholder="appended as typed"
      onchange={e => set('extra', (e.target as HTMLInputElement).value)}
    />
  </label>
</fieldset>
