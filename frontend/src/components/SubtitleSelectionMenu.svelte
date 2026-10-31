<script lang="ts">
  import CheckCheckIcon from '@lucide/svelte/icons/check-check'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import CaptionsIcon from '@lucide/svelte/icons/captions'
  import LanguagesIcon from '@lucide/svelte/icons/languages'
  import ListFilterIcon from '@lucide/svelte/icons/list-filter'
  import SquareIcon from '@lucide/svelte/icons/square'
  import { Button } from '$lib/components/ui/button'
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu'
  import { LANGUAGES } from '../lib/format'
  import { subtitleFormat, subtitleLanguage } from '../lib/subtitleSelection'
  import type { Overrides, SubTrack } from '../lib/types'
  import Tip from './Tip.svelte'

  let {
    tracks,
    overrides,
    disabled = false,
    onselect,
  }: {
    tracks: SubTrack[]
    overrides: Overrides
    disabled?: boolean
    onselect: (include: (t: SubTrack) => boolean) => void
  } = $props()

  const names = new Intl.DisplayNames(['en'], { type: 'language' })
  function languageLabel(tag: string) {
    if (tag === 'und') return 'Unknown language'
    const known = LANGUAGES.find(([code]) => code.toLowerCase() === tag)?.[1]
    try {
      return `${known ?? names.of(tag) ?? tag} (${tag})`
    } catch {
      return tag
    }
  }

  function choices(valueOf: (t: SubTrack) => string, labelOf: (v: string) => string) {
    const counts = new Map<string, number>()
    for (const t of tracks) {
      const value = valueOf(t)
      counts.set(value, (counts.get(value) ?? 0) + 1)
    }
    return [...counts]
      .map(([value, count]) => ({ value, count, label: labelOf(value) }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }

  const languages = $derived(choices((t) => subtitleLanguage(t, overrides), languageLabel))
  const formats = $derived(
    choices(subtitleFormat, (f) => (f === 'vobsub' ? 'VobSub' : f === 'unknown' ? 'Unknown type' : f.toUpperCase())),
  )
  const selected = $derived(
    tracks.filter((t) => {
      const ov = overrides.tracks[t.key]
      return ov?.burn || (ov?.exclude ?? !(t.auto?.kept ?? true)) === false
    }).length,
  )

  function select(include: (t: SubTrack) => boolean) {
    if (!disabled && tracks.length) onselect(include)
  }
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger disabled={disabled || !tracks.length}>
    {#snippet child({ props })}
      <Button {...props} variant="outline" size="sm">
        <ListFilterIcon />Select subtitles
        <span class="text-xs text-muted-foreground tabular-nums" aria-label="{selected} of {tracks.length} selected"
          >{selected}/{tracks.length}</span
        >
        <ChevronDownIcon class="size-3.5 text-muted-foreground" />
      </Button>
    {/snippet}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="start" class="w-60">
    <DropdownMenu.Label>Subtitle selection</DropdownMenu.Label>
    <DropdownMenu.Item {disabled} onSelect={() => select(() => true)}>
      <CheckCheckIcon />Select all
      <span class="ml-auto text-xs text-muted-foreground tabular-nums">{tracks.length}</span>
    </DropdownMenu.Item>
    <DropdownMenu.Item {disabled} onSelect={() => select(() => false)}><SquareIcon />Deselect all</DropdownMenu.Item>
    <DropdownMenu.Separator />
    <DropdownMenu.Label>Select matching tracks; deselect the rest.</DropdownMenu.Label>
    <DropdownMenu.Sub>
      <DropdownMenu.SubTrigger {disabled}><LanguagesIcon />Select only by language</DropdownMenu.SubTrigger>
      <DropdownMenu.SubContent
        class="max-h-[min(24rem,var(--bits-dropdown-menu-content-available-height))] w-64 overflow-y-auto"
      >
        {#each languages as language (language.value)}
          <DropdownMenu.Item
            {disabled}
            onSelect={() => select((t) => subtitleLanguage(t, overrides) === language.value)}
          >
            <Tip class="block min-w-0 flex-1 truncate" text={language.label}>{language.label}</Tip>
            <span class="ml-auto text-xs text-muted-foreground tabular-nums">{language.count}</span>
          </DropdownMenu.Item>
        {/each}
      </DropdownMenu.SubContent>
    </DropdownMenu.Sub>
    <DropdownMenu.Sub>
      <DropdownMenu.SubTrigger {disabled}><CaptionsIcon />Select only by type</DropdownMenu.SubTrigger>
      <DropdownMenu.SubContent
        class="max-h-[min(24rem,var(--bits-dropdown-menu-content-available-height))] w-44 overflow-y-auto"
      >
        {#each formats as format (format.value)}
          <DropdownMenu.Item {disabled} onSelect={() => select((t) => subtitleFormat(t) === format.value)}>
            {format.label}<span class="ml-auto text-xs text-muted-foreground tabular-nums">{format.count}</span>
          </DropdownMenu.Item>
        {/each}
      </DropdownMenu.SubContent>
    </DropdownMenu.Sub>
  </DropdownMenu.Content>
</DropdownMenu.Root>
