<script lang="ts">
  import { Input } from '$lib/components/ui/input'
  import TrackFlags from './TrackFlags.svelte'
  import AudioPresetMenu from './AudioPresetMenu.svelte'
  import AudioSettingsEditor from './AudioSettingsEditor.svelte'
  import { applyAudioPreset, audioPresetSettings } from '../lib/audioPresets'
  import type { TrackOverride, TrackProperty } from '../lib/types'

  let { value, onchange, flags, label, disabled = false }: {
    value: TrackOverride
    onchange: (value: TrackOverride) => void
    flags: TrackProperty[]
    label: string
    disabled?: boolean
  } = $props()
</script>

<div class="space-y-3" role="group" aria-label={label}>
  <AudioPresetMenu current={audioPresetSettings(value)} {disabled} apply={preset => onchange(applyAudioPreset(value, preset))} />
  <AudioSettingsEditor value={audioPresetSettings(value)} {disabled} onchange={preset => onchange(applyAudioPreset(value, preset))} />
  <div class="flex flex-wrap items-center gap-2">
    <Input class="w-56" aria-label="Title" placeholder="Title: the source's" value={value.title ?? ''} {disabled}
      onchange={e => onchange({ ...value, title: e.currentTarget.value.trim() || null })} />
    <TrackFlags value={value.flags ?? {}} {flags} {disabled} onchange={flags => onchange({ ...value, flags })} />
  </div>
</div>
