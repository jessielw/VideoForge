<script lang="ts">
  // The jobs a set of inputs makes (source, video, subtitles, chapters) and the files left over, those first.
  // A source already in the queue is kept unless it is ticked to be replaced. Each subtitle is a short tag
  // (language, format, name tags) that unticks it from its job; a job with a different number of subtitles
  // than most is flagged.
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { basename } from '../lib/format'
  import type { OddSubtitles } from '../lib/matchCheck'
  import { router } from '../lib/router.svelte'
  import type { MatchResult, SubtitleLabel } from '../lib/types'
  import Tip from './Tip.svelte'

  let {
    result,
    replacements = $bindable([]),
    excluded = $bindable([]),
    odd = new Map(),
  }: {
    result: MatchResult
    replacements?: string[]
    excluded?: string[]
    odd?: ReadonlyMap<string, OddSubtitles>
  } = $props()

  function tag(s: SubtitleLabel): string {
    return [s.language, s.format, ...s.tags, s.track === null ? '' : `track ${s.track}`].filter(Boolean).join(' · ')
  }
  function toggle(path: string) {
    excluded = excluded.includes(path) ? excluded.filter((p) => p !== path) : [...excluded, path]
  }
</script>

<table class="w-full text-sm">
  <thead class="sticky top-0 bg-card text-left text-xs text-muted-foreground">
    <tr><th class="px-4 py-2">Source</th><th>Video</th><th>Subtitles</th><th>Chapters</th></tr>
  </thead>
  <tbody>
    {#each result.unmatched as p (p)}
      <tr class="border-t border-border/60 text-warning">
        <td class="px-4 py-1.5" colspan="4">
          <span class="flex items-center gap-1.5"
            ><TriangleAlertIcon class="size-3.5 shrink-0" />Not matched to any source: {basename(p)}</span
          >
        </td>
      </tr>
    {/each}
    {#each result.jobs as j (j.source)}
      {@const flag = odd.get(j.source)}
      <tr class="border-t border-border/60">
        <td class="px-4 py-1.5">
          <Tip text={j.source}>{basename(j.source)}</Tip>
          {#if j.existing_id}
            <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <button class="underline" onclick={() => router.go('queue', j.existing_id)}>Open existing job</button>
              {#if ['queued', 'running', 'indexing'].includes(j.existing_status ?? '')}
                <span>Kept because it's {j.existing_status}</span>
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
          {j.encode ? basename(j.encode) + (j.encode_state === 'in_progress' ? ' (still encoding)' : '') : 'new encode'}
        </td>
        <td class="py-1.5 pr-3 text-muted-foreground">
          {#if j.subtitle_info.length}
            <div class="flex flex-wrap gap-1">
              {#each j.subtitle_info as s (s.path)}
                {@const off = excluded.includes(s.path)}
                <Tip
                  text="{basename(s.path)} ({s.language_name}). {off
                    ? 'Left out: click to add it back.'
                    : 'Click to leave it out.'}"
                >
                  <button
                    class="rounded-md px-1.5 py-0.5 text-xs whitespace-nowrap {off
                      ? 'text-muted-foreground/60 line-through'
                      : 'bg-muted text-foreground'}"
                    aria-pressed={!off}
                    onclick={() => toggle(s.path)}>{tag(s)}</button
                  >
                </Tip>
              {/each}
            </div>
          {:else}—{/if}
          {#if flag}
            <div class="mt-1 flex items-center gap-1 text-xs text-warning">
              <TriangleAlertIcon class="size-3 shrink-0" />{flag.count === 0
                ? 'No subtitles'
                : `${flag.count} subtitle${flag.count === 1 ? '' : 's'}`}; most have {flag.usual}
            </div>
          {/if}
        </td>
        <td class="text-muted-foreground">{j.chapters ? basename(j.chapters) : 'AutoQPF'}</td>
      </tr>
    {/each}
  </tbody>
</table>
