<script lang="ts">
  import GroupedPresetMenu from './GroupedPresetMenu.svelte'
  import AudioSettingsEditor from './AudioSettingsEditor.svelte'
  import AudioTransfer from './AudioTransfer.svelte'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { audioPresetDefaults, audioPresetProblem, audioPresetSettings } from '../lib/audioPresets'
  import type { AudioPresetSettings, AudioTrack } from '../lib/types'

  let {
    current,
    apply,
    source,
    disabled = false,
    manageOnly = false,
  }: {
    current: AudioPresetSettings
    apply: (settings: AudioPresetSettings) => void | Promise<void>
    source?: AudioTrack
    disabled?: boolean
    manageOnly?: boolean
  } = $props()

  const savedChoices = () => app.presets.audio.map((c) => ({ ...c, data: audioPresetSettings(c.data), builtin: false }))
  const choices = $derived([...audioPresetDefaults(app.encodes), ...savedChoices()])
  const parents = $derived<[string, string][]>([
    ['copy', 'Copy'],
    ...app.encodes.map((e) => [e.id, e.label] as [string, string]),
  ])
  const summary = (settings: AudioPresetSettings) =>
    settings.action === 'copy'
      ? 'Copy the source audio'
      : `${settings.layout ?? 'Auto channels'} · ${settings.bitrate_kbps ? `${settings.bitrate_kbps} kb/s` : 'encoder default bitrate / quality'}`
</script>

<GroupedPresetMenu
  title="Audio"
  showTitle
  current={audioPresetSettings(current)}
  {apply}
  {disabled}
  {choices}
  {parents}
  {manageOnly}
  parentOf={(data) => data.action}
  {summary}
  problem={(data) => audioPresetProblem(data, app.encodes, source)}
  nameExample="5.1 640 kbps"
  folderExample="Surround / Compatibility"
  folderHint="Use / for nested folders. A custom track title is saved with the preset. Language, flags, and timing stay with the track."
  savePreset={async (preset) => {
    app.presets = await api.saveAudioPreset(preset)
    return [...audioPresetDefaults(app.encodes), ...savedChoices()]
  }}
  removePreset={async (name) => {
    app.presets = await api.deletePreset('audio', name)
  }}
  removePresets={async (names) => {
    app.presets = await api.deletePresets('audio', names)
  }}
  applyLabel="Apply to this output"
>
  {#snippet editor(value, onchange)}<AudioSettingsEditor {value} {onchange} editTitle />{/snippet}
  {#snippet transfer(current, disabled)}<AudioTransfer {current} {disabled} />{/snippet}
</GroupedPresetMenu>
