<script lang="ts">
  import GroupedPresetMenu from './GroupedPresetMenu.svelte'
  import AudioSettingsEditor from './AudioSettingsEditor.svelte'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { audioPresetDefaults, audioPresetProblem } from '../lib/audioPresets'
  import type { AudioPresetSettings, AudioTrack } from '../lib/types'

  let { current, apply, source, disabled = false }: {
    current: AudioPresetSettings
    apply: (settings: AudioPresetSettings) => void | Promise<void>
    source?: AudioTrack
    disabled?: boolean
  } = $props()

  const choices = $derived([...audioPresetDefaults(app.encodes), ...app.presets.audio.map(c => ({ ...c, builtin: false }))])
  const parents = $derived<[string, string][]>([['copy', 'Copy'], ...app.encodes.map(e => [e.id, e.label] as [string, string])])
  const summary = (settings: AudioPresetSettings) => settings.action === 'copy' ? 'Copy the source audio'
    : `${settings.layout ?? 'Auto channels'} · ${settings.bitrate_kbps ? `${settings.bitrate_kbps} kb/s` : 'encoder default bitrate / quality'}`
</script>

<GroupedPresetMenu
  title="Audio" showTitle {current} {apply} {disabled} {choices} {parents}
  parentOf={data => data.action} {summary}
  problem={data => audioPresetProblem(data, app.encodes, source)}
  nameExample="5.1 640 kbps" folderExample="Surround / Compatibility"
  folderHint="Use / for nested folders. Language, title, flags, and timing stay with the track."
  savePreset={async preset => {
    app.presets = await api.saveAudioPreset(preset)
    return [...audioPresetDefaults(app.encodes), ...app.presets.audio.map(c => ({ ...c, builtin: false }))]
  }}
  removePreset={async name => { app.presets = await api.deletePreset('audio', name) }}
  applyLabel="Apply to this output"
>
  {#snippet editor(value, onchange)}<AudioSettingsEditor {value} {onchange} />{/snippet}
</GroupedPresetMenu>
