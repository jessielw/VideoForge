<script lang="ts">
  // An import dialog's choice for presets whose name is taken: replace yours (the default; one with the same
  // settings is left alone), or Keep both (a numbered copy). Shows what the import will do with the selection.
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { importSummary } from '../lib/importPlan'
  import type { ImportAction } from '../lib/types'

  let {
    keepBoth,
    actions,
    disabled = false,
    onchange,
  }: {
    keepBoth: boolean
    actions: ImportAction[] // the selected entries'
    disabled?: boolean
    onchange: (keepBoth: boolean) => void
  } = $props()
  const summary = $derived(importSummary(actions))
</script>

<div class="space-y-1.5 rounded-md bg-muted/50 p-2 text-sm">
  <label class="flex items-start gap-2">
    <Checkbox checked={keepBoth} {disabled} onCheckedChange={onchange} />
    <span
      >Keep both<span class="block text-xs text-muted-foreground"
        >Add a numbered copy instead of replacing a preset with the same name.</span
      ></span
    >
  </label>
  {#if summary}<p class="text-xs text-muted-foreground" aria-live="polite">{summary}</p>{/if}
</div>
