<script lang="ts">
  // Settings > Appearance: light / dark / system, a colour palette, and how round the corners are.
  // All of it is remembered in this browser only (it is a viewing preference, not job configuration).
  import CheckIcon from '@lucide/svelte/icons/check'
  import MonitorIcon from '@lucide/svelte/icons/monitor'
  import MoonIcon from '@lucide/svelte/icons/moon'
  import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw'
  import SunIcon from '@lucide/svelte/icons/sun'
  import { mode, setMode, userPrefersMode } from 'mode-watcher'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { DENSITIES, PALETTES, RADII } from '../lib/appearance'
  import { appearance } from '../lib/appearance.svelte'
  import { cn } from '$lib/utils'

  const MODES = [
    { id: 'light', label: 'Light', icon: SunIcon },
    { id: 'dark', label: 'Dark', icon: MoonIcon },
    { id: 'system', label: 'System', icon: MonitorIcon },
  ] as const

  const dark = $derived(mode.current === 'dark')
  const modeIsDefault = $derived(userPrefersMode.current === 'system')

  const choice = (on: boolean) =>
    cn(
      'rounded-lg border p-3 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
      on ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40 hover:bg-accent/50',
    )
</script>

<section class="col-span-full min-w-0 space-y-4" aria-label="Appearance">
  <div class="flex flex-wrap items-center gap-3">
    <h2 class="font-medium">Appearance</h2>
    <span class="text-sm text-muted-foreground">Remembered in this browser.</span>
    <Button
      variant="ghost"
      size="sm"
      class="ml-auto"
      disabled={appearance.isDefault && modeIsDefault}
      onclick={() => {
        appearance.reset()
        setMode('system')
      }}
    >
      <RotateCcwIcon />Reset
    </Button>
  </div>

  <div class="space-y-2">
    <p class="section-label">Mode</p>
    <div class="grid max-w-md grid-cols-3 gap-2" role="radiogroup" aria-label="Mode">
      {#each MODES as m (m.id)}
        {@const on = userPrefersMode.current === m.id}
        <button
          type="button"
          role="radio"
          aria-checked={on}
          class={cn(choice(on), 'flex items-center justify-center gap-2')}
          onclick={() => setMode(m.id)}
        >
          <m.icon class="size-4" />{m.label}
        </button>
      {/each}
    </div>
  </div>

  <div class="space-y-2">
    <p class="section-label">Palette</p>
    <div class="grid gap-3 sm:grid-cols-2 @min-[80rem]/settings:grid-cols-4" role="radiogroup" aria-label="Palette">
      {#each PALETTES as p (p.id)}
        {@const on = appearance.palette === p.id}
        {@const sw = dark ? p.dark : p.light}
        <button
          type="button"
          role="radio"
          aria-checked={on}
          class={choice(on)}
          onclick={() => (appearance.palette = p.id)}
        >
          <div class="flex items-start justify-between gap-2">
            <span class="font-medium">{p.label}</span>
            {#if on}
              <span
                class="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"
              >
                <CheckIcon class="size-3.5" />
              </span>
            {/if}
          </div>
          <p class="mt-1 text-xs text-muted-foreground">{p.description}</p>
          <!-- A tiny mock of the app: page, card, accent button. -->
          <div
            class="mt-3 flex items-center gap-2 rounded-md p-2 ring-1 ring-border"
            style="background-color: {sw[0]}"
            aria-hidden="true"
          >
            <span class="h-6 flex-1 rounded-sm ring-1 ring-black/10" style="background-color: {sw[1]}"></span>
            <span class="h-6 w-8 rounded-sm" style="background-color: {sw[2]}"></span>
          </div>
        </button>
      {/each}
    </div>
  </div>

  <div class="space-y-2">
    <p class="section-label">Accent color</p>
    <div class="flex flex-wrap items-center gap-3">
      <input
        type="color"
        aria-label="Custom accent color"
        class="h-9 w-14 cursor-pointer rounded-md border border-border bg-transparent p-1"
        value={appearance.accent ??
          (PALETTES.find((p) => p.id === appearance.palette) ?? PALETTES[0])[dark ? 'dark' : 'light'][2]}
        oninput={(e) => (appearance.accent = e.currentTarget.value)}
      />
      <span class="text-sm text-muted-foreground">
        {appearance.accent
          ? `Custom ${appearance.accent}, used with every palette.`
          : "Using the palette's own accent."}
      </span>
      {#if appearance.accent}
        <Button variant="ghost" size="sm" onclick={() => (appearance.accent = null)}>Use palette accent</Button>
      {/if}
    </div>
  </div>

  <div class="space-y-2">
    <p class="section-label">Density</p>
    <div class="grid max-w-md grid-cols-3 gap-2" role="radiogroup" aria-label="Density">
      {#each DENSITIES as d (d.id)}
        {@const on = appearance.density === d.id}
        <button
          type="button"
          role="radio"
          aria-checked={on}
          class={cn(choice(on), 'text-center')}
          onclick={() => (appearance.density = d.id)}
        >
          {d.label}
        </button>
      {/each}
    </div>
  </div>

  <label class="flex items-start gap-3">
    <Checkbox checked={appearance.oled} onCheckedChange={(v) => (appearance.oled = v === true)} class="mt-0.5" />
    <span>
      <span class="block">Pure black dark mode</span>
      <span class="block text-sm text-muted-foreground">
        Near-black surfaces for OLED screens. Only shows in dark mode{dark ? '' : ' (you are in light mode now)'}.
      </span>
    </span>
  </label>

  <div class="space-y-2">
    <p class="section-label">Corners</p>
    <div class="grid max-w-2xl grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Corners">
      {#each RADII as r (r.id)}
        {@const on = appearance.radius === r.id}
        <button
          type="button"
          role="radio"
          aria-checked={on}
          class={cn(choice(on), 'flex items-center gap-3')}
          onclick={() => (appearance.radius = r.id)}
        >
          <span
            class="size-8 shrink-0 border-t-2 border-l-2 border-primary"
            style="border-top-left-radius: {r.rem * 1.6}rem"
            aria-hidden="true"
          ></span>
          {r.label}
        </button>
      {/each}
    </div>
  </div>
</section>
