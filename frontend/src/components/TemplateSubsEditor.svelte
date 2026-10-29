<script lang="ts">
  // A template's subtitles as rules: each track (source tracks and added files) takes the first rule
  // matching its language, format and traits, and is kept (with a title and flags) or left out; the
  // tracks no rule matches are kept or left out. Kept tracks go in rule order, and a default set by a
  // rule goes to the first track it reaches only.
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import TrackFlags from './TrackFlags.svelte'
  import type { SubFormat, SubRule, TemplateSubs, TrackProperty } from '../lib/types'
  import LanguagePicker from './LanguagePicker.svelte'

  let {
    value,
    onchange,
    flags,
    disabled = false,
    toggleLabel = 'Set the subtitle tracks',
    offNote = "Off: applying the template leaves each job's subtitles as they are.",
    appliedNote = "Applying the template replaces a job's subtitle choices.",
  }: {
    value: TemplateSubs | null
    onchange: (v: TemplateSubs | null) => void
    flags: TrackProperty[]
    disabled?: boolean
    toggleLabel?: string
    offNote?: string
    appliedNote?: string
  } = $props()

  const FORMATS: { id: SubFormat; label: string }[] = [
    { id: 'srt', label: 'SRT' },
    { id: 'pgs', label: 'PGS' },
    { id: 'ass', label: 'ASS' },
    { id: 'vobsub', label: 'VobSub' },
  ]
  const TRAITS = [
    { key: 'forced', label: 'Forced', help: 'By its flag, or "forced" / "foreign" in its title' },
    { key: 'hearing_impaired', label: 'SDH', help: 'By its flag, or "SDH" / "CC" in its title' },
    { key: 'commentary', label: 'Commentary', help: 'By its flag, or "commentary" in its title' },
  ] as const

  const rule = (): SubRule => ({
    languages: [],
    formats: [],
    forced: null,
    hearing_impaired: null,
    commentary: null,
    track: { exclude: null, language: null, title: null, flags: {}, action: null, bitrate_kbps: null, layout: null, options: {} },
  })

  function change(fn: (s: TemplateSubs) => void) {
    if (!value) return
    const next = structuredClone($state.snapshot(value)) as TemplateSubs
    fn(next)
    onchange(next)
  }
  const tri = (v: boolean | null) => (v === null ? 'any' : v ? 'yes' : 'no')
  const fromTri = (v: string) => (v === 'any' ? null : v === 'yes')

  function move(i: number, by: number) {
    change(s => {
      const [r] = s.rules.splice(i, 1)
      s.rules.splice(i + by, 0, r)
    })
  }
</script>

<div class="space-y-3">
  <label class="flex items-center gap-2 text-sm">
    <Checkbox checked={value !== null} {disabled} onCheckedChange={on => onchange(on ? { rules: [rule()], others: 'exclude' } : null)} />
    {toggleLabel}
  </label>
  {#if value === null}
    <p class="text-xs text-muted-foreground">{offNote}</p>
  {:else}
    <p class="text-xs text-muted-foreground">
      Each subtitle track, added files too, takes the first rule it matches (empty = any). Kept tracks go in rule order; a rule that
      sets Default gives it to the first track it reaches, and every other subtitle has it off. {appliedNote}
    </p>
    {#each value.rules as r, i (i)}
      <div class="space-y-3 rounded-lg border p-3" role="group" aria-label="Rule {i + 1}">
        <div class="flex items-center gap-1">
          <span class="mr-2 text-sm font-medium">Rule {i + 1}</span>
          <NativeSelect
            aria-label="Rule {i + 1}: keep, leave out or burn in"
            value={r.track.exclude ? 'exclude' : r.track.burn ? 'burn' : 'keep'}
            {disabled}
            onchange={e =>
              change(
                s =>
                  (s.rules[i].track = {
                    ...rule().track,
                    exclude: e.currentTarget.value === 'exclude' || null,
                    burn: e.currentTarget.value === 'burn' || null,
                  }),
              )}
          >
            <option value="keep">Keep</option>
            <option value="exclude">Leave out</option>
            <option value="burn" title="Burned into the video instead of muxed: the first track a burn-in rule matches">Burn in</option>
          </NativeSelect>
          <Button
            variant="ghost"
            size="icon-sm"
            class="ml-auto"
            title="Move rule {i + 1} up"
            aria-label="Move rule {i + 1} up"
            disabled={disabled || i === 0}
            onclick={() => move(i, -1)}><ArrowUpIcon /></Button
          >
          <Button
            variant="ghost"
            size="icon-sm"
            title="Move rule {i + 1} down"
            aria-label="Move rule {i + 1} down"
            disabled={disabled || i === value.rules.length - 1}
            onclick={() => move(i, 1)}><ArrowDownIcon /></Button
          >
          <Button
            variant="ghost"
            size="icon-sm"
            class="hover:text-destructive"
            title="Remove rule {i + 1}"
            aria-label="Remove rule {i + 1}"
            {disabled}
            onclick={() => change(s => s.rules.splice(i, 1))}><XIcon /></Button
          >
        </div>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
          <span class="w-8 text-xs text-muted-foreground">Match</span>
          <LanguagePicker
            class="w-56"
            aria-label="Rule {i + 1}: languages"
            placeholder="Language: any"
            title="Languages (en matches en-US too; es-419 only itself)"
            value={r.languages}
            {disabled}
            onchange={(v: string[]) => change(s => (s.rules[i].languages = v))}
          />
          <NativeSelect
            aria-label="Rule {i + 1}: format"
            value={r.formats[0] ?? ''}
            {disabled}
            onchange={e => change(s => (s.rules[i].formats = e.currentTarget.value ? [e.currentTarget.value as SubFormat] : []))}
          >
            <option value="">Any format</option>
            {#each FORMATS as f (f.id)}<option value={f.id}>{f.label}</option>{/each}
          </NativeSelect>
          {#each TRAITS as t (t.key)}
            <label class="flex items-center gap-1.5 text-muted-foreground" title={t.help}>
              {t.label}
              <NativeSelect
                aria-label="Rule {i + 1}: {t.label}"
                value={tri(r[t.key])}
                {disabled}
                onchange={e => change(s => (s.rules[i][t.key] = fromTri(e.currentTarget.value)))}
              >
                <option value="any">any</option>
                <option value="yes">yes</option>
                <option value="no">no</option>
              </NativeSelect>
            </label>
          {/each}
        </div>
        {#if !r.track.exclude && !r.track.burn}
          <div class="flex flex-wrap items-center gap-2">
            <span class="mr-1 w-8 text-xs text-muted-foreground">Set</span>
            <Input
              class="w-56"
              aria-label="Rule {i + 1}: title"
              placeholder="Title: the source's"
              value={r.track.title ?? ''}
              {disabled}
              onchange={e => change(s => (s.rules[i].track.title = e.currentTarget.value.trim() || null))}
            />
            <TrackFlags value={r.track.flags} {flags} {disabled} onchange={f => change(s => (s.rules[i].track.flags = f))} />
          </div>
        {/if}
      </div>
    {/each}
    <div class="flex flex-wrap items-center gap-3">
      <Button variant="outline" size="sm" {disabled} onclick={() => change(s => s.rules.push(rule()))}>
        <PlusIcon />Rule {value.rules.length + 1}
      </Button>
      <label class="flex items-center gap-2 text-sm" title="A kept track with no title (none from its rule or the source) is named from its language and flags">
        <Checkbox
          checked={!!value.name_untitled}
          {disabled}
          aria-label="Name untitled tracks"
          onCheckedChange={on => change(s => (s.name_untitled = on))}
        />
        Name untitled tracks <span class="text-xs text-muted-foreground">English (SDH)</span>
      </label>
      <label class="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
        Tracks no rule matches
        <NativeSelect value={value.others} {disabled} onchange={e => change(s => (s.others = e.currentTarget.value as TemplateSubs['others']))}>
          <option value="exclude">Leave out</option>
          <option value="keep">Keep (after the rest)</option>
        </NativeSelect>
      </label>
    </div>
  {/if}
</div>
