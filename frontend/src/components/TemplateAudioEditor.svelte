<script lang="ts">
  // A template's audio, for the source's audio tracks (added audio files keep their own settings).
  // By position: one slot per source audio track (track 1 = the source's first); slots past a
  // source's tracks are ignored; tracks past the slots are kept or left out. By rules: each track
  // takes the first rule matching its language, codec, channels and traits ("only the first": the
  // first matching track takes it, the others go on to the next rules); kept tracks go in rule order.
  // Either way a track copies or encodes and can make more outputs.
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import * as ToggleGroup from '$lib/components/ui/toggle-group'
  import AudioOutputEditor from './AudioOutputEditor.svelte'
  import type { AudioCodec, AudioRule, TemplateAudio, TrackOverride, TrackProperty } from '../lib/types'
  import LanguagePicker from './LanguagePicker.svelte'
  import Tip from './Tip.svelte'

  let {
    value,
    onchange,
    flags,
    disabled = false,
  }: {
    value: TemplateAudio | null
    onchange: (v: TemplateAudio | null) => void
    flags: TrackProperty[]
    disabled?: boolean
  } = $props()

  const empty = (): TrackOverride => ({
    exclude: null,
    language: null,
    title: null,
    flags: {},
    action: null,
    bitrate_kbps: null,
    layout: null,
    options: {},
  })
  const rule = (): AudioRule => ({
    languages: [],
    original: null,
    codecs: [],
    min_channels: null,
    max_channels: null,
    commentary: null,
    visual_impaired: null,
    first_only: false,
    track: empty(),
    extra: [],
  })

  // Codec choices; a group matches any of its codecs.
  const CODECS: { label: string; codecs: AudioCodec[] }[] = [
    { label: 'Any codec', codecs: [] },
    { label: 'Lossless (any)', codecs: ['truehd', 'dts_hd_ma', 'lpcm', 'flac'] },
    { label: 'DTS (any)', codecs: ['dts', 'dts_hd_ma', 'dts_hd_hra'] },
    { label: 'TrueHD', codecs: ['truehd'] },
    { label: 'DTS-HD MA', codecs: ['dts_hd_ma'] },
    { label: 'DTS-HD HRA', codecs: ['dts_hd_hra'] },
    { label: 'DTS', codecs: ['dts'] },
    { label: 'LPCM', codecs: ['lpcm'] },
    { label: 'FLAC', codecs: ['flac'] },
    { label: 'E-AC-3', codecs: ['eac3'] },
    { label: 'AC-3', codecs: ['ac3'] },
    { label: 'AAC', codecs: ['aac'] },
    { label: 'Opus', codecs: ['opus'] },
  ]
  const MIN_CHANNELS = [
    { n: 2, label: '2.0' },
    { n: 6, label: '5.1' },
    { n: 8, label: '7.1' },
  ]
  const MAX_CHANNELS = [
    { n: 1, label: '1.0' },
    { n: 2, label: '2.0' },
    { n: 6, label: '5.1' },
  ]
  const TRAITS = [
    { key: 'commentary', label: 'Commentary', help: 'By its flag, or "commentary" in its title' },
    {
      key: 'visual_impaired',
      label: 'Audio description',
      help: 'By its flag, or "audio description", "descriptive" or "AD" in its title',
    },
  ] as const

  const mode = $derived(value?.mode ?? 'position')
  const rules = $derived(value?.rules ?? [])

  function change(fn: (a: TemplateAudio) => void) {
    if (!value) return
    const next = structuredClone($state.snapshot(value)) as TemplateAudio
    next.mode ??= 'position'
    next.rules ??= []
    fn(next)
    onchange(next)
  }
  // rules leave out what they don't match by default, slots keep what's past them
  const setMode = (m: TemplateAudio['mode']) =>
    change((a) => {
      a.mode = m
      a.others = m === 'rules' ? 'exclude' : 'keep'
      if (m === 'rules' && !a.rules.length) a.rules.push(rule())
    })
  const tri = (v: boolean | null) => (v === null ? 'any' : v ? 'yes' : 'no')
  const fromTri = (v: string) => (v === 'any' ? null : v === 'yes')
  const codecKey = (c: AudioCodec[]) => [...c].sort().join(',')
  const num = (v: string) => (v ? Number(v) : null)

  function move(i: number, by: number) {
    change((a) => {
      const [r] = a.rules.splice(i, 1)
      a.rules.splice(i + by, 0, r)
    })
  }
</script>

<!-- A track's outputs: its own (copy or an encode; `main` labels it) and more made from it, labelled
     "<name>, output n". `from` says which track they're made from. `at` picks the slot/rule. -->
{#snippet outputs(
  track: TrackOverride,
  extra: TrackOverride[],
  name: string,
  main: string,
  from: string,
  at: (a: TemplateAudio) => { track: TrackOverride; extra: TrackOverride[] },
)}
  <AudioOutputEditor value={track} {flags} {disabled} label={main} onchange={(v) => change((a) => (at(a).track = v))} />
  {#each extra as x, n (n)}
    <div class="space-y-2 border-l-2 border-primary/40 pl-3">
      <div class="flex items-center gap-2 text-sm text-muted-foreground">
        Another output from {from}
        <Tip text="Remove this output">
          <Button
            variant="ghost"
            size="icon-sm"
            class="hover:text-destructive"
            aria-label="Remove output {n + 2} of {name}"
            {disabled}
            onclick={() => change((a) => at(a).extra.splice(n, 1))}><XIcon /></Button
          >
        </Tip>
      </div>
      <AudioOutputEditor
        value={x}
        {flags}
        {disabled}
        label="{name}, output {n + 2}"
        onchange={(v) => change((a) => (at(a).extra[n] = v))}
      />
    </div>
  {/each}
  <Button
    variant="ghost"
    size="sm"
    {disabled}
    onclick={() => change((a) => at(a).extra.push({ ...empty(), action: 'ddp' }))}
  >
    <PlusIcon />Another output from this track
  </Button>
{/snippet}

<div class="space-y-3">
  <label class="flex items-center gap-2 text-sm">
    <Checkbox
      checked={value !== null}
      {disabled}
      onCheckedChange={(on) =>
        onchange(on ? { mode: 'position', slots: [{ track: empty(), extra: [] }], rules: [], others: 'keep' } : null)}
    />
    Set the audio tracks
  </label>
  {#if value === null}
    <p class="text-xs text-muted-foreground">Off: applying the template leaves each job's audio as it is.</p>
  {:else}
    <ToggleGroup.Root
      type="single"
      variant="outline"
      class="w-fit"
      {disabled}
      value={mode}
      onValueChange={(v) => v && v !== mode && setMode(v as TemplateAudio['mode'])}
    >
      <ToggleGroup.Item value="position" class="px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
        >By position</ToggleGroup.Item
      >
      <ToggleGroup.Item value="rules" class="px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
        >By rules</ToggleGroup.Item
      >
    </ToggleGroup.Root>
    {#if mode === 'position'}
      <p class="text-xs text-muted-foreground">
        By position: track 1 is the source's first audio track. A source with fewer tracks skips the rest; added audio
        files keep their own settings. A slot asking for more than its track has gets the best that fits (2.0 stays 2.0,
        DDP Atmos needs a TrueHD Atmos track). Applying the template replaces a job's audio choices.
      </p>
      {#each value.slots as slot, i (i)}
        <div class="space-y-3 rounded-lg border p-3">
          <div class="flex items-center gap-3">
            <span class="text-sm font-medium">Audio track {i + 1}</span>
            <label class="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox
                checked={slot.track.exclude === true}
                {disabled}
                onCheckedChange={(on) =>
                  change(
                    (a) =>
                      (a.slots[i] = on
                        ? { track: { ...empty(), exclude: true }, extra: [] }
                        : { track: empty(), extra: [] }),
                  )}
              />
              Leave out
            </label>
            <Tip class="ml-auto" text="Remove audio track {i + 1}">
              <Button
                variant="ghost"
                size="icon-sm"
                class="hover:text-destructive"
                aria-label="Remove audio track {i + 1}"
                {disabled}
                onclick={() => change((a) => a.slots.splice(i, 1))}><XIcon /></Button
              >
            </Tip>
          </div>
          {#if !slot.track.exclude}
            {@render outputs(
              slot.track,
              slot.extra,
              `Audio track ${i + 1}`,
              `Audio track ${i + 1}`,
              `track ${i + 1}`,
              (a) => a.slots[i],
            )}
          {/if}
        </div>
      {/each}
      <div class="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          {disabled}
          onclick={() => change((a) => a.slots.push({ track: empty(), extra: [] }))}
        >
          <PlusIcon />Audio track {value.slots.length + 1}
        </Button>
        <label class="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
          Audio tracks past these
          <NativeSelect
            value={value.others}
            {disabled}
            onchange={(e) => change((a) => (a.others = e.currentTarget.value as TemplateAudio['others']))}
          >
            <option value="keep">Keep (as the profile decides)</option>
            <option value="exclude">Leave out</option>
          </NativeSelect>
        </label>
      </div>
    {:else}
      <p class="text-xs text-muted-foreground">
        Each source audio track takes the first rule it matches (empty = any); added audio files keep their own
        settings. "Only the first": the first matching track takes the rule, the others go on to the next rules. Kept
        tracks go in rule order; a rule that sets Default gives it to the first track it reaches, and every other one
        has it off. Outputs are fitted to each track as with slots.
      </p>
      {#each rules as r, i (i)}
        <div class="space-y-3 rounded-lg border p-3" role="group" aria-label="Audio rule {i + 1}">
          <div class="flex flex-wrap items-center gap-1">
            <span class="mr-2 text-sm font-medium">Rule {i + 1}</span>
            <NativeSelect
              aria-label="Audio rule {i + 1}: keep or leave out"
              value={r.track.exclude ? 'exclude' : 'keep'}
              {disabled}
              onchange={(e) =>
                change((a) => {
                  a.rules[i].track = { ...empty(), exclude: e.currentTarget.value === 'exclude' || null }
                  a.rules[i].extra = []
                })}
            >
              <option value="keep">Keep</option>
              <option value="exclude">Leave out</option>
            </NativeSelect>
            <Tip class="ml-2" text="Only the first matching track (in source order) takes this rule">
              <label class="flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={r.first_only}
                  {disabled}
                  onCheckedChange={(on) => change((a) => (a.rules[i].first_only = on))}
                />
                Only the first
              </label>
            </Tip>
            <Tip class="ml-auto" text="Move rule {i + 1} up">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Move audio rule {i + 1} up"
                disabled={disabled || i === 0}
                onclick={() => move(i, -1)}><ArrowUpIcon /></Button
              >
            </Tip>
            <Tip text="Move rule {i + 1} down">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Move audio rule {i + 1} down"
                disabled={disabled || i === rules.length - 1}
                onclick={() => move(i, 1)}><ArrowDownIcon /></Button
              >
            </Tip>
            <Tip text="Remove rule {i + 1}">
              <Button
                variant="ghost"
                size="icon-sm"
                class="hover:text-destructive"
                aria-label="Remove audio rule {i + 1}"
                {disabled}
                onclick={() => change((a) => a.rules.splice(i, 1))}><XIcon /></Button
              >
            </Tip>
          </div>
          <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            <span class="w-8 text-xs text-muted-foreground">Match</span>
            <Tip text="Languages (en matches en-US too; es-419 only itself)">
              <LanguagePicker
                class="w-56"
                aria-label="Audio rule {i + 1}: languages"
                placeholder="Language: any"
                value={r.languages}
                {disabled}
                onchange={(v: string[]) => change((a) => (a.rules[i].languages = v))}
              />
            </Tip>
            <Tip text="The job's original language (the profile's guess, or the one set on the job)">
              <NativeSelect
                aria-label="Audio rule {i + 1}: original language"
                value={tri(r.original)}
                {disabled}
                onchange={(e) => change((a) => (a.rules[i].original = fromTri(e.currentTarget.value)))}
              >
                <option value="any">Original or not</option>
                <option value="yes">Original language</option>
                <option value="no">Not the original</option>
              </NativeSelect>
            </Tip>
            <NativeSelect
              aria-label="Audio rule {i + 1}: codec"
              value={codecKey(r.codecs)}
              {disabled}
              onchange={(e) =>
                change(
                  (a) =>
                    (a.rules[i].codecs = (
                      e.currentTarget.value ? e.currentTarget.value.split(',') : []
                    ) as AudioCodec[]),
                )}
            >
              {#each CODECS as c (c.label)}<option value={codecKey(c.codecs)}>{c.label}</option>{/each}
              {#if !CODECS.some((c) => codecKey(c.codecs) === codecKey(r.codecs))}<option value={codecKey(r.codecs)}
                  >{r.codecs.join(', ')}</option
                >{/if}
            </NativeSelect>
            <label class="flex items-center gap-1.5 text-muted-foreground">
              Channels
              <NativeSelect
                aria-label="Audio rule {i + 1}: at least"
                value={r.min_channels ?? ''}
                {disabled}
                onchange={(e) => change((a) => (a.rules[i].min_channels = num(e.currentTarget.value)))}
              >
                <option value="">at least: any</option>
                {#each MIN_CHANNELS as c (c.n)}<option value={c.n}>at least {c.label}</option>{/each}
              </NativeSelect>
              <NativeSelect
                aria-label="Audio rule {i + 1}: at most"
                value={r.max_channels ?? ''}
                {disabled}
                onchange={(e) => change((a) => (a.rules[i].max_channels = num(e.currentTarget.value)))}
              >
                <option value="">at most: any</option>
                {#each MAX_CHANNELS as c (c.n)}<option value={c.n}>at most {c.label}</option>{/each}
              </NativeSelect>
            </label>
            {#each TRAITS as t (t.key)}
              <Tip text={t.help}>
                <label class="flex items-center gap-1.5 text-muted-foreground">
                  {t.label}
                  <NativeSelect
                    aria-label="Audio rule {i + 1}: {t.label}"
                    value={tri(r[t.key])}
                    {disabled}
                    onchange={(e) => change((a) => (a.rules[i][t.key] = fromTri(e.currentTarget.value)))}
                  >
                    <option value="any">any</option>
                    <option value="yes">yes</option>
                    <option value="no">no</option>
                  </NativeSelect>
                </label>
              </Tip>
            {/each}
          </div>
          {#if !r.track.exclude}
            {@render outputs(
              r.track,
              r.extra,
              `Audio rule ${i + 1}`,
              `Audio rule ${i + 1}, output 1`,
              'each track it matches',
              (a) => a.rules[i],
            )}
          {/if}
        </div>
      {/each}
      <div class="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" {disabled} onclick={() => change((a) => a.rules.push(rule()))}>
          <PlusIcon />Rule {rules.length + 1}
        </Button>
        <label class="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
          Tracks no rule matches
          <NativeSelect
            value={value.others}
            {disabled}
            onchange={(e) => change((a) => (a.others = e.currentTarget.value as TemplateAudio['others']))}
          >
            <option value="exclude">Leave out</option>
            <option value="keep">Keep (after the rest)</option>
          </NativeSelect>
        </label>
      </div>
    {/if}
  {/if}
</div>
