<script lang="ts">
  // A template's audio: one slot per source audio track, by position (track 1 = the source's first
  // audio track). Slots past a source's tracks are ignored; tracks past the slots are kept or left
  // out. Each slot copies or encodes its track and can make more outputs from it.
  import PlusIcon from '@lucide/svelte/icons/plus'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import AudioOutputEditor from './AudioOutputEditor.svelte'
  import type { TemplateAudio, TrackOverride, TrackProperty } from '../lib/types'

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

  function change(fn: (a: TemplateAudio) => void) {
    if (!value) return
    const next = structuredClone($state.snapshot(value)) as TemplateAudio
    fn(next)
    onchange(next)
  }
</script>

<div class="space-y-3">
  <label class="flex items-center gap-2 text-sm">
    <Checkbox
      checked={value !== null}
      {disabled}
      onCheckedChange={on => onchange(on ? { slots: [{ track: empty(), extra: [] }], others: 'keep' } : null)}
    />
    Set the audio tracks
  </label>
  {#if value === null}
    <p class="text-xs text-muted-foreground">Off: applying the template leaves each job's audio as it is.</p>
  {:else}
    <p class="text-xs text-muted-foreground">
      By position: track 1 is the source's first audio track. A source with fewer tracks skips the rest; added audio files keep their own
      settings. A slot asking for more than its track has gets the best that fits (2.0 stays 2.0, DDP Atmos needs a TrueHD
      Atmos track). Applying the template replaces a job's audio choices.
    </p>
    {#each value.slots as slot, i (i)}
      <div class="space-y-3 rounded-lg border p-3">
        <div class="flex items-center gap-3">
          <span class="text-sm font-medium">Audio track {i + 1}</span>
          <label class="flex items-center gap-2 text-sm text-muted-foreground">
            <Checkbox
              checked={slot.track.exclude === true}
              {disabled}
              onCheckedChange={on => change(a => (a.slots[i] = on ? { track: { ...empty(), exclude: true }, extra: [] } : { track: empty(), extra: [] }))}
            />
            Leave out
          </label>
          <Button
            variant="ghost"
            size="icon-sm"
            class="ml-auto hover:text-destructive"
            title="Remove audio track {i + 1}"
            aria-label="Remove audio track {i + 1}"
            {disabled}
            onclick={() => change(a => a.slots.splice(i, 1))}><XIcon /></Button
          >
        </div>
        {#if !slot.track.exclude}
          <AudioOutputEditor value={slot.track} {flags} {disabled} label="Audio track {i + 1}" onchange={v => change(a => (a.slots[i].track = v))} />
          {#each slot.extra as x, n (n)}
            <div class="space-y-2 border-l-2 border-primary/40 pl-3">
              <div class="flex items-center gap-2 text-sm text-muted-foreground">
                Another output from track {i + 1}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  class="hover:text-destructive"
                  title="Remove this output"
                  aria-label="Remove output {n + 1} from track {i + 1}"
                  {disabled}
                  onclick={() => change(a => a.slots[i].extra.splice(n, 1))}><XIcon /></Button
                >
              </div>
              <AudioOutputEditor
                value={x}
                {flags}
                {disabled}
                label="Audio track {i + 1}, output {n + 2}"
                onchange={v => change(a => (a.slots[i].extra[n] = v))}
              />
            </div>
          {/each}
          <Button variant="ghost" size="sm" {disabled} onclick={() => change(a => a.slots[i].extra.push({ ...empty(), action: 'ddp' }))}>
            <PlusIcon />Another output from this track
          </Button>
        {/if}
      </div>
    {/each}
    <div class="flex flex-wrap items-center gap-3">
      <Button variant="outline" size="sm" {disabled} onclick={() => change(a => a.slots.push({ track: empty(), extra: [] }))}>
        <PlusIcon />Audio track {value.slots.length + 1}
      </Button>
      <label class="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
        Audio tracks past these
        <NativeSelect value={value.others} {disabled} onchange={e => change(a => (a.others = e.currentTarget.value as TemplateAudio['others']))}>
          <option value="keep">Keep (as the profile decides)</option>
          <option value="exclude">Leave out</option>
        </NativeSelect>
      </label>
    </div>
  {/if}
</div>
