<script lang="ts">
  // A job's (or template's) filter chain: the steps in order, each switched on or off, moved, removed, or
  // its lines edited; Add filter offers the built-in filters by category, a click puts one in its place.
  // The crop and resize steps are only moved here: their values are set in their own sections.
  import { app } from '../lib/state.svelte'
  import { addFilter, moveStep } from '../lib/filterChain'
  import { FILTER_CATEGORIES, type Crop, type FilterPreset, type FilterStep, type Resize } from '../lib/types'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import ChevronUpIcon from '@lucide/svelte/icons/chevron-up'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Popover from '$lib/components/ui/popover'
  import { Textarea } from '$lib/components/ui/textarea'
  import Tip from './Tip.svelte'

  let {
    filters = $bindable(),
    crop,
    resize,
    template = false,
    disabled = false,
    onchange = () => {},
  }: {
    filters: FilterStep[]
    crop?: Crop // shown on the crop step (a template's crop may be per job: none)
    resize: Resize | null
    template?: boolean // a keep-AR resize's height is each job's
    disabled?: boolean
    onchange?: () => void
  } = $props()

  let open = $state(false)
  let expanded = $state<number | null>(null)

  // The add menu: per category (chain order), its filters, each family's strengths side by side.
  const groups = $derived(
    FILTER_CATEGORIES.map((c) => {
      const families = new Map<string, FilterPreset[]>()
      for (const p of app.filterPresets.filter((p) => p.category === c.id))
        families.set(p.family, [...(families.get(p.family) ?? []), p])
      return { ...c, families: [...families.entries()] }
    }).filter((g) => g.families.length),
  )
  const inChain = $derived(new Set(filters.map((s) => s.name)))

  function set(chain: FilterStep[]) {
    filters = chain
    onchange()
  }

  function add(p: FilterPreset) {
    const [chain, at] = addFilter(filters, p, app.filterPresets)
    set(chain)
    expanded = p.fill_in ? at : null // opens to type its values in
    open = false
  }

  function summary(s: FilterStep): string {
    if (s.category === 'crop') {
      if (!crop) return 'per job'
      const { left, top, right, bottom } = crop
      return left || top || right || bottom ? `${left}/${top}/${right}/${bottom}` : 'none'
    }
    if (s.category === 'resize')
      return resize ? `${resize.width}×${resize.keep_ar && template ? 'auto' : resize.height}` : 'off'
    return FILTER_CATEGORIES.find((c) => c.id === s.category)?.label ?? s.category
  }
</script>

<section class="space-y-2">
  <div class="flex items-center justify-between">
    <span class="section-label">Filters</span>
    <Popover.Root bind:open>
      <Tip text="Add a built-in filter: it goes in its category's place">
        <Popover.Trigger {disabled}>
          {#snippet child({ props })}
            <Button {...props} variant="outline" size="sm"><PlusIcon />Add filter</Button>
          {/snippet}
        </Popover.Trigger>
      </Tip>
      <!-- To the side, two columns: the whole menu fits without scrolling on most screens. -->
      <Popover.Content
        side="left"
        align="start"
        class="block max-h-(--bits-floating-available-height) w-[44rem] max-w-[90vw] columns-2 gap-6 overflow-auto p-3"
        onEscapeKeydown={(e) => e.stopPropagation()}
      >
        {#each groups as g (g.id)}
          <div class="mb-3 break-inside-avoid space-y-1">
            <Tip class="section-label block" text={g.title}>{g.label}</Tip>
            {#each g.families as [family, presets] (family)}
              <!-- Every row alike: the filter, then a button per variant (Add when it has none). -->
              <Tip class="flex items-center gap-1" side="left" text={presets[0].description}>
                <span class="w-36 shrink-0 truncate text-sm">{family}</span>
                {#each presets as p (p.name)}
                  <Button size="xs" variant={inChain.has(p.name) ? 'default' : 'outline'} onclick={() => add(p)}
                    >{p.variant || 'Add'}</Button
                  >
                {/each}
              </Tip>
            {/each}
          </div>
        {/each}
        {#if !groups.length}<p class="text-sm text-muted-foreground">
            No built-in filters (the server didn't send them).
          </p>{/if}
      </Popover.Content>
    </Popover.Root>
  </div>

  <ol class="divide-y rounded-lg border text-sm" class:opacity-50={disabled}>
    {#each filters as s, i (i)}
      {@const fixed = s.category === 'crop' || s.category === 'resize'}
      <li>
        <div class="flex items-center gap-1 py-1 pr-1 pl-2">
          {#if fixed}
            <span class="size-4 shrink-0"></span>
          {:else}
            <Checkbox
              checked={s.enabled}
              {disabled}
              aria-label="Use {s.name}"
              onCheckedChange={(on) => set(filters.map((x, j) => (j === i ? { ...x, enabled: !!on } : x)))}
            />
          {/if}
          <Tip class="flex min-w-0 flex-1" text={fixed ? `Set in the ${s.name} section` : 'Show its lines'}>
            <button
              class="flex min-w-0 flex-1 items-baseline gap-2 text-left disabled:cursor-default"
              disabled={fixed}
              onclick={() => (expanded = expanded === i ? null : i)}
            >
              <span
                class="truncate {fixed ? 'font-medium' : ''} {s.enabled ? '' : 'text-muted-foreground line-through'}"
                >{s.name}</span
              >
              <span class="ml-auto shrink-0 text-xs text-muted-foreground">{summary(s)}</span>
            </button>
          </Tip>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Move {s.name} up"
            disabled={disabled || i === 0}
            onclick={() => set(moveStep(filters, i, -1))}
          >
            <ChevronUpIcon />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Move {s.name} down"
            disabled={disabled || i === filters.length - 1}
            onclick={() => set(moveStep(filters, i, 1))}
          >
            <ChevronDownIcon />
          </Button>
          {#if fixed}
            <span class="size-6 shrink-0"></span>
          {:else}
            <Button
              variant="ghost"
              size="icon-xs"
              class="hover:text-destructive"
              aria-label="Remove {s.name}"
              {disabled}
              onclick={() => {
                expanded = null
                set(filters.filter((_, j) => j !== i))
              }}
            >
              <XIcon />
            </Button>
          {/if}
        </div>
        {#if expanded === i && !fixed}
          <div class="px-2 pb-2">
            <Textarea
              class="h-24 w-full font-mono text-xs"
              aria-label="{s.name} lines"
              placeholder="clip = core.std.Levels(clip, ...)"
              bind:value={s.script}
              {disabled}
              onchange={() => onchange()}
            />
          </div>
        {/if}
      </li>
    {/each}
  </ol>
</section>
