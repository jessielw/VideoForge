<script lang="ts">
  // The jobs a set of inputs makes (source, video, subtitles, chapters) and the files left over. A source
  // already in the queue is kept unless it is ticked to be replaced.
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { basename } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import type { MatchResult } from '../lib/types'
  import Tip from './Tip.svelte'

  let { result, replacements = $bindable([]) }: { result: MatchResult; replacements?: string[] } = $props()
</script>

<table class="w-full text-sm">
  <thead class="sticky top-0 bg-card text-left text-xs text-muted-foreground uppercase">
    <tr><th class="px-4 py-2">Source</th><th>Video</th><th>Subtitles</th><th>Chapters</th></tr>
  </thead>
  <tbody>
    {#each result.jobs as j (j.source)}
      <tr class="border-t border-border/60">
        <td class="px-4 py-1.5">
          <Tip text={j.source}>{basename(j.source)}</Tip>
          {#if j.existing_id}
            <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <button class="underline" onclick={() => router.go('queue', j.existing_id)}>Open existing job</button>
              {#if ['queued', 'running', 'indexing'].includes(j.existing_status ?? '')}
                <span>Kept: {j.existing_status}</span>
              {:else}
                <label class="flex items-center gap-1"
                  ><Checkbox
                    checked={replacements.includes(j.existing_id)}
                    onCheckedChange={(on) => {
                      replacements = on
                        ? [...replacements, j.existing_id!]
                        : replacements.filter((id) => id !== j.existing_id)
                    }}
                  />Replace and reset its edits</label
                >
              {/if}
            </div>
          {/if}
        </td>
        <td class={j.encode ? (j.encode_state === 'in_progress' ? 'text-warning' : '') : 'text-primary'}>
          {j.encode
            ? basename(j.encode) + (j.encode_state === 'in_progress' ? ' (still encoding)' : '')
            : 'encode with VapourSynth'}
        </td>
        <td class="text-muted-foreground">{j.subtitles.map(basename).join(', ') || '—'}</td>
        <td class="text-muted-foreground">{j.chapters ? basename(j.chapters) : 'AutoQPF'}</td>
      </tr>
    {/each}
    {#each result.unmatched as p (p)}
      <tr class="border-t border-border/60 text-muted-foreground">
        <td class="px-4 py-1.5" colspan="4">Not matched to any source: {basename(p)}</td>
      </tr>
    {/each}
  </tbody>
</table>
