<script lang="ts">
  // A text (or number) box with suggestions in its own list, in place of the browser's datalist popup:
  // the list opens on focus and filters as you type (by value or label); arrows pick one out and Enter takes
  // it. Enter with nothing picked out goes to the box's own onkeydown, so a box that adds on Enter still does.
  // A suggestion taken sets the value and calls onpick (a programmatic value fires no change event).
  import type { HTMLInputAttributes } from 'svelte/elements'
  import { Input } from '$lib/components/ui/input'
  import * as Popover from '$lib/components/ui/popover'
  import { cn } from '$lib/utils'

  export type Suggestion = { value: string; label?: string }
  type Props = Omit<HTMLInputAttributes, 'type' | 'list' | 'files'> & {
    value?: string | number | null
    type?: 'text' | 'number'
    suggestions: Suggestion[]
    onpick?: (value: string) => void
    wrapClass?: string // the box's size and place; class styles the input
  }
  let {
    value = $bindable(),
    type = 'text',
    suggestions,
    onpick,
    wrapClass = '',
    class: className = '',
    onkeydown: keydown,
    oninput: input,
    onfocus: focus,
    onblur: blur,
    ...rest
  }: Props = $props()

  const uid = $props.id()
  let open = $state(false)
  let typed = $state(false) // filter only once the user types: a box with a value still lists every suggestion
  let active = $state(-1)
  let anchor = $state<HTMLElement | null>(null)
  let ref = $state<HTMLInputElement | null>(null)
  let list = $state<HTMLElement | null>(null)

  const items = $derived.by(() => {
    const q = typed
      ? String(value ?? '')
          .trim()
          .replace(/^-+/, '')
          .toLowerCase()
      : ''
    if (!q) return suggestions
    // the value starting with it, then holding it, then the label holding it
    const rank = (s: Suggestion) => {
      const v = s.value.toLowerCase()
      return v.startsWith(q) ? 0 : v.includes(q) ? 1 : s.label?.toLowerCase().includes(q) ? 2 : -1
    }
    return suggestions
      .map((s) => ({ s, r: rank(s) }))
      .filter((x) => x.r >= 0)
      .sort((a, b) => a.r - b.r)
      .map((x) => x.s)
  })

  function begin() {
    if (rest.disabled || open || !suggestions.length) return
    typed = false
    active = -1
    open = true
  }

  function scroll() {
    requestAnimationFrame(() => list?.querySelector('[data-active]')?.scrollIntoView({ block: 'nearest' }))
  }

  function pick(s: Suggestion) {
    value = type === 'number' ? (Number(s.value) as never) : s.value
    if (ref) ref.value = s.value
    open = false
    onpick?.(s.value)
  }

  // Arrows step through the list and back to the typed value (-1); a number box keeps them for stepping.
  function onkeydown(e: KeyboardEvent & { currentTarget: EventTarget & HTMLInputElement }) {
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && type === 'text') {
      e.preventDefault()
      if (!open) return begin()
      const n = items.length
      if (e.key === 'ArrowDown') active = active + 1 >= n ? -1 : active + 1
      else active = active <= -1 ? n - 1 : active - 1
      scroll()
      return
    }
    if (e.key === 'Enter' && open && items[active]) {
      e.preventDefault()
      pick(items[active])
      return
    }
    if (e.key === 'Escape' && open) {
      e.preventDefault()
      open = false
      return
    }
    if (e.key === 'Enter') open = false // the box's own Enter (e.g. add) is done with the list
    keydown?.(e)
  }
</script>

<Popover.Root
  {open}
  onOpenChange={(o) => {
    if (!o) open = false
  }}
>
  <div bind:this={anchor} class={cn('min-w-0', wrapClass)}>
    <Input
      {...rest}
      bind:ref
      bind:value
      {type}
      class={cn('w-full', className)}
      role="combobox"
      aria-expanded={open}
      aria-controls="{uid}-list"
      aria-autocomplete="list"
      aria-activedescendant={open && items[active] ? `${uid}-${active}` : undefined}
      autocomplete="off"
      spellcheck="false"
      onfocus={(e) => {
        begin()
        focus?.(e)
      }}
      onclick={begin}
      oninput={(e) => {
        typed = true
        active = -1
        if (!open) begin()
        input?.(e)
      }}
      onblur={(e) => {
        open = false
        blur?.(e)
      }}
      {onkeydown}
    />
  </div>
  <Popover.Content
    customAnchor={anchor}
    align="start"
    class="w-auto min-w-56 max-w-96 gap-0 p-1"
    trapFocus={false}
    onOpenAutoFocus={(e) => e.preventDefault()}
    onCloseAutoFocus={(e) => e.preventDefault()}
    onInteractOutside={(e) => {
      if (anchor?.contains(e.target as Node)) e.preventDefault()
    }}
  >
    <div bind:this={list} id="{uid}-list" role="listbox" class="max-h-64 overflow-y-auto">
      {#each items as s, i (s.value)}
        <div
          id="{uid}-{i}"
          role="option"
          tabindex="-1"
          aria-selected={i === active}
          data-active={i === active ? '' : undefined}
          class="flex cursor-default items-baseline gap-3 rounded-md px-2 py-1.5 text-sm select-none {i === active
            ? 'bg-accent text-accent-foreground'
            : ''}"
          onmousedown={(e) => e.preventDefault()}
          onmousemove={() => (active = i)}
          onclick={() => pick(s)}
          onkeydown={() => {}}
        >
          <span class="shrink-0 font-mono text-xs">{s.value}</span>
          {#if s.label}<span class="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={s.label}
              >{s.label}</span
            >{/if}
        </div>
      {:else}
        <div class="px-2 py-1.5 text-sm text-muted-foreground">No match: the typed value is used as it is.</div>
      {/each}
    </div>
  </Popover.Content>
</Popover.Root>
