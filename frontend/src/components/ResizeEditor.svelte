<script lang="ts">
  // The resize section (a job's Video tab, a template), as in StaxRip: with Keep aspect ratio the height
  // follows the width, so the output keeps the display aspect ratio of the picture going in (the cropped
  // source; an anamorphic one's pixel aspect included), both sides on the mod. Shows that picture, the
  // output's aspect ratio and how far it is off. Without `input` (a template, a job not probed yet) a
  // keep-AR height is each job's: the server fits it once the source is known (and on every crop change).
  // The encode is told its pixels' shape (--sar): an anamorphic source unresized keeps its own, and a
  // fixed size that stretches the picture gets the shape that undoes it, so it plays at the source's shape.
  import {
    arError,
    displayAspect,
    fitHeight,
    fitWidth,
    fitted,
    KERNELS,
    MODS,
    outputShape,
    snap,
    WIDTHS,
    type Geometry,
  } from '../lib/resize'
  import type { Resize } from '../lib/types'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'

  let {
    resize = $bindable(),
    input = null,
    disabled = false,
    onchange = () => {},
  }: { resize: Resize | null; input?: Geometry | null; disabled?: boolean; onchange?: () => void } = $props()

  function set(r: Resize | null) {
    resize = r
    onchange()
  }

  function toggle(on: boolean) {
    if (!on) return set(null)
    const width = input ? snap(input.width, 2) : 1920
    set(fitted({ width, height: 1080, kernel: 'Spline36', keep_ar: true, mod: 2 }, input))
  }

  // A width typed or picked: a keep-AR height follows; a fixed one is fitted once if the source is known.
  function setWidth(r: Resize, value: number) {
    const width = snap(value, r.mod)
    const height = input ? fitHeight(width, input, r.mod) : r.keep_ar ? r.height : snap((width * 9) / 16, r.mod)
    set({ ...r, width, height })
  }

  function setHeight(r: Resize, value: number) {
    if (r.keep_ar && input) set(fitted({ ...r, width: fitWidth(snap(value, r.mod), input, r.mod) }, input))
    else set({ ...r, height: snap(value, r.mod) })
  }

  const ratio = (x: number) => `${x.toFixed(x < 10 ? 3 : 2).replace(/\.?0+$/, '')}:1`
  const anamorphic = $derived(!!input && input.sarNum !== input.sarDen)
  const error = $derived(resize && input && resize.height > 0 ? arError(resize.width, resize.height, input) : null)
  const upscale = $derived(!!resize && !!input && (resize.width > input.width || resize.height > input.height))
  const auto = $derived(!!resize?.keep_ar && !input) // the height is each job's
  const shape = $derived(input ? outputShape(resize, input) : 1) // the encode's pixels
</script>

<section class="space-y-2">
  <div class="flex items-center justify-between">
    <label class="flex items-center gap-2">
      <Checkbox checked={!!resize} {disabled} onCheckedChange={toggle} />
      <span class="section-label">Resize</span>
    </label>
    {#if resize}<span class="text-xs text-muted-foreground tabular-nums"
        >{resize.width}×{auto ? 'auto' : resize.height}</span
      >{/if}
  </div>
  {#if !resize && input && anamorphic}
    <p class="text-xs text-muted-foreground tabular-nums">
      Anamorphic source (pixels {input.sarNum}:{input.sarDen}): the encode keeps them and plays at {ratio(
        displayAspect(input),
      )}.
    </p>
  {/if}
  {#if resize}
    {@const r = resize}
    <div class="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-sm">
      <Input
        type="number"
        step={r.mod}
        min={r.mod}
        aria-label="Width"
        {disabled}
        value={r.width}
        onchange={(e) => setWidth(r, +(e.target as HTMLInputElement).value)}
      />
      ×
      {#if auto}
        <Input aria-label="Height" disabled value="auto" title="Each job's: the width at the source's aspect ratio" />
      {:else}
        <Input
          type="number"
          step={r.mod}
          min={r.mod}
          aria-label="Height"
          {disabled}
          value={r.height}
          title={r.keep_ar ? 'Typing a height sets the width that makes it' : undefined}
          onchange={(e) => setHeight(r, +(e.target as HTMLInputElement).value)}
        />
      {/if}
    </div>
    <div class="flex flex-wrap gap-1">
      {#each WIDTHS as w (w.width)}
        <button
          type="button"
          class="rounded border px-1.5 py-0.5 text-xs tabular-nums hover:bg-accent disabled:opacity-50 {r.width ===
          w.width
            ? 'border-primary text-primary'
            : 'text-muted-foreground'}"
          {disabled}
          title="{w.width} wide{input && w.width > input.width ? ' (upscales)' : ''}"
          onclick={() => setWidth(r, w.width)}>{w.label}</button
        >
      {/each}
    </div>
    <div class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
      <NativeSelect
        class="w-full"
        aria-label="Kernel"
        {disabled}
        value={r.kernel}
        onchange={(e) => set({ ...r, kernel: (e.target as HTMLSelectElement).value })}
      >
        {#each KERNELS as k (k)}<option value={k}>{k}</option>{/each}
      </NativeSelect>
      <NativeSelect
        aria-label="Mod"
        title="Both sides a multiple of this"
        {disabled}
        value={String(r.mod)}
        onchange={(e) => {
          const mod = +(e.target as HTMLSelectElement).value
          set(
            r.keep_ar
              ? fitted({ ...r, mod }, input)
              : { ...r, mod, width: snap(r.width, mod), height: snap(r.height, mod) },
          )
        }}
      >
        {#each MODS as m (m)}<option value={String(m)}>Mod {m}</option>{/each}
      </NativeSelect>
    </div>
    <label class="flex items-center gap-2 text-sm">
      <Checkbox checked={r.keep_ar} {disabled} onCheckedChange={(on) => set(fitted({ ...r, keep_ar: on }, input))} />
      Keep aspect ratio
    </label>
    {#if input && shape !== 1}
      <p class="text-xs text-muted-foreground tabular-nums">
        In {input.width}×{input.height}{anamorphic ? ` (pixels ${input.sarNum}:${input.sarDen})` : ''} · {ratio(
          displayAspect(input),
        )}
        → {r.width}×{r.height} with {ratio(shape)} pixels (anamorphic), playing at {ratio((r.width / r.height) * shape)}
      </p>
      {#if upscale}<p class="text-xs text-warning">
          Upscaling: bigger than the {input.width}×{input.height} going in.
        </p>{/if}
    {:else if input}
      <p class="text-xs text-muted-foreground tabular-nums">
        In {input.width}×{input.height}{anamorphic ? ` (pixels ${input.sarNum}:${input.sarDen})` : ''} · {ratio(
          displayAspect(input),
        )}
        → {ratio(r.width / r.height)}
        {#if error !== null}
          · <span class={Math.abs(error) > 1 ? 'text-warning' : ''}>off {error >= 0 ? '+' : ''}{error.toFixed(2)}%</span
          >
        {/if}
      </p>
      {#if upscale}<p class="text-xs text-warning">
          Upscaling: bigger than the {input.width}×{input.height} going in.
        </p>{/if}
    {:else if r.keep_ar}
      <p class="text-xs text-muted-foreground">The height is fitted to each job's source and crop.</p>
    {/if}
  {/if}
</section>
