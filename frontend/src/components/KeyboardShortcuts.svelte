<script lang="ts">
  // The keyboard shortcuts, on one sheet: the menu's button opens it, and so does ? anywhere but a text field.
  // Keep it in step with the handlers it lists (Queue's keys, FramePreview's onkey, VideoTab's and
  // ScriptEditor's onkeydown).
  import KeyboardIcon from '@lucide/svelte/icons/keyboard'
  import { Button } from '$lib/components/ui/button'
  import * as Dialog from '$lib/components/ui/dialog'
  import Tip from './Tip.svelte'

  let { compact = false }: { compact?: boolean } = $props()
  let open = $state(false)

  // Each row's keys are pressed together (shown with +); a slash in one is either of two keys.
  const SECTIONS: { title: string; keys: [string[], string][] }[] = [
    {
      title: 'Queue list',
      keys: [
        [['Click'], 'Select a job'],
        [['Ctrl / ⌘', 'Click'], 'Add a job to the selection, or take it out'],
        [['Shift', 'Click'], 'Select the jobs between'],
        [['Drag'], 'Select the rows dragged across'],
        [['↑ / ↓'], 'The previous or next job'],
        [['Home / End'], 'The first or last job'],
        [['Shift', '↑ / ↓'], 'Grow the selection'],
        [['Ctrl / ⌘', 'A'], 'Select every matching job'],
        [['Esc'], 'Hide the list when it is over the editor'],
      ],
    },
    {
      title: 'Frame preview (click it first)',
      keys: [
        [['← / →'], 'A frame back or on'],
        [['Shift', '← / →'], '10 frames back or on'],
        [['Page Up / Page Down'], 'A second back or on'],
        [['Home / End'], 'The first or last frame'],
        [['+ / -'], 'Zoom in or out'],
        [['S'], 'Save the frame as a PNG'],
      ],
    },
    {
      title: 'Video tab',
      keys: [
        [['F5'], 'Refresh the preview (in the script editor: run the script)'],
        [['C'], 'Compare: flip between Input and Encoded'],
        [['Esc'], 'Leave the expanded view'],
      ],
    },
    {
      title: 'Script editor',
      keys: [
        [['Ctrl / ⌘', 'Enter'], 'Run the script'],
        [['Tab'], 'Indent'],
        [['Enter'], 'New line, keeping the indent (one more after a colon)'],
      ],
    },
  ]

  function typing(t: EventTarget | null) {
    return t instanceof HTMLElement && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName))
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key !== '?' || e.ctrlKey || e.altKey || e.metaKey || e.defaultPrevented || typing(e.target)) return
    e.preventDefault()
    open = !open
  }
</script>

<svelte:window {onkeydown} />

<Tip side="right" class="grid" text={compact ? 'Keyboard shortcuts (?)' : undefined}>
  <Button
    variant="ghost"
    size={compact ? 'icon' : 'default'}
    class="text-muted-foreground {compact ? '' : 'justify-start gap-3 px-3'}"
    onclick={() => (open = true)}
    aria-label="Keyboard shortcuts"
    aria-keyshortcuts="?"
  >
    <KeyboardIcon />{#if !compact}Shortcuts{/if}
  </Button>
</Tip>

<Dialog.Root bind:open>
  <Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
    <Dialog.Header>
      <Dialog.Title>Keyboard shortcuts</Dialog.Title>
      <Dialog.Description>Press ? anywhere but a text field to open this again.</Dialog.Description>
    </Dialog.Header>
    <div class="grid gap-x-8 gap-y-5 md:grid-cols-2">
      {#each SECTIONS as section (section.title)}
        <section aria-label={section.title}>
          <h3 class="section-label mb-2">{section.title}</h3>
          <dl class="space-y-1.5 text-sm">
            {#each section.keys as [keys, what] (what)}
              <div class="flex items-baseline justify-between gap-4">
                <dt class="flex shrink-0 flex-wrap items-center gap-1">
                  {#each keys as key, i (i)}
                    {#if i}<span class="text-xs text-muted-foreground">+</span>{/if}
                    <kbd class="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs whitespace-nowrap">{key}</kbd>
                  {/each}
                </dt>
                <dd class="text-right text-muted-foreground">{what}</dd>
              </div>
            {/each}
          </dl>
        </section>
      {/each}
    </div>
  </Dialog.Content>
</Dialog.Root>
