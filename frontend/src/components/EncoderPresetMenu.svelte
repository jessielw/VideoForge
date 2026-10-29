<script lang="ts">
  import GroupedPresetMenu from './GroupedPresetMenu.svelte'
  import EncoderSettingsEditor from './EncoderSettingsEditor.svelte'
  import EncoderTransfer from './EncoderTransfer.svelte'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { ENCODERS, type EncoderSettings } from '../lib/types'

  let { profile, current, apply, disabled = false, manageOnly = false }: {
    profile: string
    current: EncoderSettings
    apply: (settings: EncoderSettings) => void | Promise<void>
    disabled?: boolean
    manageOnly?: boolean
  } = $props()

  const summary = (data: EncoderSettings) => {
    const rate = data.rate_control === 'crf' ? `CRF ${data.crf}`
      : data.target_mb && data.rate_control === '2pass' ? `${data.target_mb} MB` : `${data.bitrate_kbps} kb/s`
    return `${rate} · ${data.depth}-bit · ${data.preset || 'default speed'}`
  }
</script>

<GroupedPresetMenu
  title="Encoder" {current} {apply} {disabled} {manageOnly}
  choices={app.presetChoices('encoder', profile)} parents={ENCODERS}
  parentOf={data => data.encoder} {summary} builtinLabel="profile"
  nameExample="Grain" folderExample="1080p / SDR"
  folderHint="Use / for nested folders. Folder names do not change resize or HDR processing."
  savePreset={async preset => {
    app.presets = await api.saveEncoderPreset(preset)
    return app.presetChoices('encoder', profile)
  }}
  removePreset={async name => { app.presets = await api.deletePreset('encoder', name) }}
  removePresets={async names => { app.presets = await api.deletePresets('encoder', names) }}
  applyLabel="Apply encoder settings"
>
  {#snippet editor(value, onchange)}<EncoderSettingsEditor {value} {onchange} advancedCollapsed />{/snippet}
  {#snippet transfer(current, disabled)}<EncoderTransfer {current} {disabled} />{/snippet}
</GroupedPresetMenu>
