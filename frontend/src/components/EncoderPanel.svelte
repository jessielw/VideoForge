<script lang="ts">
  import type { ComponentProps } from 'svelte'
  import EncoderSettingsEditor from './EncoderSettingsEditor.svelte'
  import EncoderPresetMenu from './EncoderPresetMenu.svelte'

  let {
    ruleSet,
    ...settings
  }: Omit<ComponentProps<typeof EncoderSettingsEditor>, 'presetControl'> & { ruleSet?: string } = $props()
</script>

{#snippet presetControl()}
  {#if ruleSet}<EncoderPresetMenu
      {ruleSet}
      current={settings.value}
      apply={settings.onchange}
      disabled={settings.disabled}
    />{/if}
{/snippet}

<EncoderSettingsEditor {...settings} presetControl={ruleSet ? presetControl : undefined} />
