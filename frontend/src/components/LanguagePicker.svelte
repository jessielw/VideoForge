<script lang="ts">
  // A language box: type to filter the list (by name or tag) or pick from it; any other IETF tag can be
  // typed and taken with Enter. One language (value: a tag, '' = none) or several (value: tags, shown as
  // chips). Its own list replaces the browser's datalist / autofill popup.
  import CheckIcon from '@lucide/svelte/icons/check'
  import XIcon from '@lucide/svelte/icons/x'
  import * as Popover from '$lib/components/ui/popover'
  import { cn } from '$lib/utils'
  import Tip from './Tip.svelte'
  import { languageName, PICKER_LANGUAGES } from '../lib/format'

  type Props = {
    value: string | string[]
    onchange: (next: string & string[]) => void
    placeholder?: string
    disabled?: boolean
    clearable?: boolean // one language: an x sets it to ''
    show?: 'name' | 'tag' // one language: what the closed box shows (a narrow track row: the tag)
    class?: string
    'aria-label'?: string
  }
  let {
    value,
    onchange,
    placeholder = '',
    disabled = false,
    clearable = true,
    show = 'name',
    class: className = '',
    'aria-label': ariaLabel,
  }: Props = $props()

  const uid = $props.id()
  const many = $derived(Array.isArray(value))
  const chosen = $derived(Array.isArray(value) ? value : value ? [value] : [])
  const isChosen = (tag: string) => chosen.some((c) => c.toLowerCase() === tag.toLowerCase())

  let open = $state(false)
  let query = $state('')
  let active = $state(0)
  let anchor = $state<HTMLElement | null>(null)
  let input = $state<HTMLInputElement | null>(null)
  let list = $state<HTMLElement | null>(null)

  // A typed tag that isn't listed, when it names a language ("pt-PT"; not "jap")
  const TAG = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/
  const realTag = (t: string) => TAG.test(t) && languageName(t).toLowerCase() !== t.toLowerCase()
  const items = $derived.by(() => {
    const q = query.trim().toLowerCase()
    const found = PICKER_LANGUAGES.filter(
      ([tag, name]) => !q || tag.toLowerCase().startsWith(q) || name.toLowerCase().includes(q),
    )
    const typed = query.trim()
    if (realTag(typed) && !found.some(([tag, name]) => tag.toLowerCase() === q || name === languageName(typed)))
      found.push([typed, languageName(typed)])
    return found
  })
  // What was typed, when it names one language exactly (a tag or a name): taken when the box loses focus.
  function typedTag(): string | null {
    const q = query.trim().toLowerCase()
    if (!q) return null
    const hit = PICKER_LANGUAGES.find(([tag, name]) => tag.toLowerCase() === q || name.toLowerCase() === q)
    return hit ? hit[0] : realTag(query.trim()) ? query.trim() : null
  }
  const shown = $derived(many || !value ? '' : show === 'tag' ? (value as string) : languageName(value as string))

  function emit(next: string | string[]) {
    onchange(next as string & string[])
  }

  function begin() {
    if (disabled || open) return
    query = ''
    const at =
      chosen.length === 1 ? PICKER_LANGUAGES.findIndex(([tag]) => tag.toLowerCase() === chosen[0].toLowerCase()) : -1
    active = Math.max(at, 0)
    open = true
    requestAnimationFrame(() => list?.querySelector('[data-active]')?.scrollIntoView({ block: 'nearest' }))
  }

  function end() {
    open = false
    query = ''
  }

  function pick(tag: string) {
    if (Array.isArray(value)) {
      emit(isChosen(tag) ? value.filter((v) => v.toLowerCase() !== tag.toLowerCase()) : [...value, tag])
      query = ''
      active = 0
      input?.focus()
    } else {
      if (tag !== value) emit(tag)
      end()
      input?.blur()
    }
  }

  function remove(tag: string) {
    if (Array.isArray(value)) emit(value.filter((v) => v !== tag))
  }

  function onkeydown(e: KeyboardEvent) {
    if (disabled) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) return begin()
      active = items.length ? (active + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length : 0
      requestAnimationFrame(() => list?.querySelector('[data-active]')?.scrollIntoView({ block: 'nearest' }))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (open && items[active]) pick(items[active][0])
      else if (!many && clearable && open && !query.trim()) pick('')
    } else if (e.key === 'Escape' && open) {
      e.preventDefault()
      end()
    } else if (e.key === 'Backspace' && many && !query && chosen.length) {
      remove(chosen[chosen.length - 1])
    }
  }
</script>

<Popover.Root
  {open}
  onOpenChange={(o) => {
    if (!o) end()
  }}
>
  <div
    bind:this={anchor}
    class={cn(
      'dark:bg-input/30 border-input focus-within:border-ring focus-within:ring-ring/50 flex min-h-8 min-w-0 flex-wrap items-center gap-1 rounded-lg border bg-transparent px-1.5 py-0.5 text-sm transition-colors focus-within:ring-3',
      disabled && 'bg-input/50 dark:bg-input/80 cursor-not-allowed opacity-50',
      className,
    )}
  >
    {#if many}
      {#each chosen as tag (tag)}
        <Tip
          class="max-w-full items-center gap-0.5 rounded-md bg-secondary py-0.5 pr-0.5 pl-1.5 text-xs text-secondary-foreground"
          text={tag}
        >
          <span class="truncate">{languageName(tag)}</span>
          {#if !disabled}
            <button
              type="button"
              class="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
              aria-label="Remove {languageName(tag)}"
              onclick={() => remove(tag)}><XIcon class="size-3" /></button
            >
          {/if}
        </Tip>
      {/each}
    {/if}
    <input
      bind:this={input}
      class="h-6 w-0 min-w-12 flex-1 bg-transparent px-1 outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
      role="combobox"
      aria-label={ariaLabel}
      aria-expanded={open}
      aria-controls="{uid}-list"
      aria-autocomplete="list"
      aria-activedescendant={open && items[active] ? `${uid}-${active}` : undefined}
      autocomplete="off"
      spellcheck="false"
      {disabled}
      placeholder={open && shown ? shown : many && chosen.length ? '' : placeholder}
      value={open ? query : shown}
      onfocus={begin}
      onclick={begin}
      oninput={(e) => {
        query = e.currentTarget.value
        active = 0
        if (!open) begin()
      }}
      onblur={() => {
        const tag = typedTag()
        if (tag && !isChosen(tag)) emit(Array.isArray(value) ? [...value, tag] : tag)
        end()
      }}
      {onkeydown}
    />
    {#if !many && clearable && value && !disabled}
      <Tip text="Clear">
        <button
          type="button"
          class="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
          aria-label="Clear the language"
          onmousedown={(e) => e.preventDefault()}
          onclick={() => emit('')}><XIcon class="size-3.5" /></button
        >
      </Tip>
    {/if}
  </div>
  <Popover.Content
    customAnchor={anchor}
    align="start"
    class="w-64 gap-0 p-1"
    trapFocus={false}
    onOpenAutoFocus={(e) => e.preventDefault()}
    onCloseAutoFocus={(e) => e.preventDefault()}
    onInteractOutside={(e) => {
      if (anchor?.contains(e.target as Node)) e.preventDefault()
    }}
  >
    <div bind:this={list} id="{uid}-list" role="listbox" aria-multiselectable={many} class="max-h-64 overflow-y-auto">
      {#each items as [tag, name], i (tag)}
        <div
          id="{uid}-{i}"
          role="option"
          tabindex="-1"
          aria-selected={isChosen(tag)}
          data-active={i === active ? '' : undefined}
          class="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm select-none {i === active
            ? 'bg-accent text-accent-foreground'
            : ''}"
          onmousedown={(e) => e.preventDefault()}
          onmousemove={() => (active = i)}
          onclick={() => pick(tag)}
          onkeydown={() => {}}
        >
          <CheckIcon class="size-3.5 shrink-0 {isChosen(tag) ? '' : 'invisible'}" />
          <span class="min-w-0 flex-1 truncate">{name}</span>
          <span class="text-xs text-muted-foreground">{tag}</span>
        </div>
      {:else}
        <div class="px-2 py-1.5 text-sm text-muted-foreground">No language matches; type a tag like pt-BR.</div>
      {/each}
    </div>
  </Popover.Content>
</Popover.Root>
