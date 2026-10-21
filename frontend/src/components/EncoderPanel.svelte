<script lang="ts">
  import type { ComponentProps } from 'svelte'
  import EncoderSettingsEditor from './EncoderSettingsEditor.svelte'
  import EncoderPresetMenu from './EncoderPresetMenu.svelte'

  let { profile, ...settings }: Omit<ComponentProps<typeof EncoderSettingsEditor>, 'presetControl'> & { profile?: string } = $props()
</script>

{#snippet presetControl()}
  {#if profile}<EncoderPresetMenu {profile} current={settings.value} apply={settings.onchange} disabled={settings.disabled} />{/if}
{/snippet}

<EncoderSettingsEditor {...settings} presetControl={profile ? presetControl : undefined} />
