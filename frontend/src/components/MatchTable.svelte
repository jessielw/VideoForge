<script lang="ts">
  // The jobs a set of inputs makes (source, video, subtitles, chapters) and the files left over, those first.
  // A source already in the queue is kept unless it is ticked to be replaced. Each subtitle is a line: an
  // icon for how sure its match is, a short tag (language, format, name tags) and its file name, the part
  // it shares with the source dimmed. Clicking it unticks it from its job; a job with a different number of
  // subtitles than most is flagged. A file no source claimed can be matched by hand (assign), its closest
  // sources offered first; one matched by hand has an undo button. Clicking any file's match icon opens Review
  // matches (onreview) on that file, to move it to another source or none; its tooltip says what a guess went
  // on. A second chapters file or encode for one source is left over, and subtitles that look like the same
  // track twice are flagged.
  import SparklesIcon from '@lucide/svelte/icons/sparkles'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import XIcon from '@lucide/svelte/icons/x'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { basename } from '../lib/format'
  import { MATCH_NOTE, nameParts, type OddSubtitles } from '../lib/matchCheck'
  import { MATCH_ICONS, matchTone } from '../lib/matchIcons'
  import { duplicateSubtitles, kindOf } from '../lib/matchReview'
  import { router } from '../lib/router.svelte'
  import type { MatchResult, SubtitleLabel, SubtitleMatch } from '../lib/types'
  import Tip from './Tip.svelte'

  let {
    result,
    replacements = $bindable([]),
    excluded = $bindable([]),
    assign = $bindable({}),
    odd = new Map(),
    onreview,
  }: {
    result: MatchResult
    replacements?: string[]
    excluded?: string[]
    assign?: Record<string, string | null>
    odd?: ReadonlyMap<string, OddSubtitles>
    onreview?: (path: string) => void // open Review matches on this file
  } = $props()

  const sources = $derived(result.jobs.map((j) => j.source))
  const held = $derived(new Set(result.held ?? []))
  // Unmatched files with a best guess, for "Use the suggestions".
  const suggested = $derived(result.unmatched.filter((p) => !held.has(p) && result.suggestions?.[p]?.length))

  function tag(s: SubtitleLabel): string {
    return [s.language, s.format, ...s.tags, s.track === null ? '' : `track ${s.track}`].filter(Boolean).join(' · ')
  }
  function toggle(path: string) {
    excluded = excluded.includes(path) ? excluded.filter((p) => p !== path) : [...excluded, path]
  }
  function matchTo(path: string, source: string) {
    assign = { ...assign, [path]: source }
  }
  function unmatch(path: string) {
    const { [path]: _, ...rest } = assign
    assign = rest
  }
  function matchSuggested() {
    assign = { ...assign, ...Object.fromEntries(suggested.map((p) => [p, result.suggestions[p][0].source])) }
  }
</script>

<!-- How a file matched; a button that opens Review matches on it. -->
{#snippet how(path: string, match: SubtitleMatch | null | undefined, detail = '', off = false)}
  {#if match}
    {@const note = MATCH_NOTE[match]}
    {@const Icon = MATCH_ICONS[match]}
    <Tip text="{note.text}.{detail ? ` ${detail}.` : ''} Click to change its match.">
      <button
        class="mt-0.5 shrink-0 rounded-sm"
        aria-label="{note.text}. Change the match of {basename(path)}"
        onclick={() => onreview?.(path)}
        ><Icon aria-hidden="true" class="size-3.5 {matchTone(match, note.sure, off)}" /></button
      >
    </Tip>
  {/if}
{/snippet}

{#snippet undo(path: string)}
  <Tip text="You matched this file. Click to undo.">
    <button
      class="mt-0.5 shrink-0 rounded-sm text-muted-foreground hover:text-foreground"
      aria-label="Undo match: {basename(path)}"
      onclick={() => unmatch(path)}><XIcon class="size-3.5" /></button
    >
  </Tip>
{/snippet}

<table class="w-full text-sm">
  <thead class="sticky top-0 bg-card text-left text-xs text-muted-foreground">
    <tr><th class="px-4 py-2">Source</th><th>Video</th><th>Subtitles</th><th>Chapters</th></tr>
  </thead>
  <tbody>
    {#if suggested.length > 1}
      <tr class="border-t border-border/60">
        <td class="px-4 py-1.5" colspan="4">
          <Button size="sm" variant="outline" onclick={matchSuggested}
            ><SparklesIcon />Use the suggested source for {suggested.length} unmatched files</Button
          >
        </td>
      </tr>
    {/if}
    {#each result.unmatched as p (p)}
      {@const offer = result.suggestions?.[p] ?? []}
      {@const lostTo = result.spare?.[p]}
      <tr class="border-t border-border/60">
        <td class="px-4 py-1.5" colspan="4">
          {#if held.has(p)}
            <span class="flex min-w-0 items-start gap-1.5 text-muted-foreground [overflow-wrap:anywhere]"
              ><Tip text={p}>Set to no source by you: {basename(p)}</Tip>{@render undo(p)}</span
            >
          {:else}
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span class="flex min-w-0 items-center gap-1.5 text-warning [overflow-wrap:anywhere]"
                ><TriangleAlertIcon class="size-3.5 shrink-0" /><Tip text={p}
                  >{#if lostTo}Left over: {basename(lostTo)} already has {kindOf(p) === 'video'
                      ? 'an encode'
                      : 'chapters'}, so {basename(p)} isn't used{:else}Not matched to any source: {basename(
                      p,
                    )}{/if}</Tip
                ></span
              >
              <NativeSelect
                size="sm"
                class="max-w-full min-w-0"
                aria-label="Match {basename(p)} to a source"
                value=""
                onchange={(e) => e.currentTarget.value && matchTo(p, e.currentTarget.value)}
              >
                <option value="">Match to…</option>
                {#if offer.length}
                  <optgroup label="Suggested">
                    {#each offer as s (s.source)}<option value={s.source} title={s.detail}
                        >{basename(s.source)}{s.why === 'pattern' ? ' (like your match)' : ''}</option
                      >{/each}
                  </optgroup>
                {/if}
                <optgroup label="All sources">
                  {#each sources as s (s)}<option value={s}>{basename(s)}</option>{/each}
                </optgroup>
              </NativeSelect>
              {#if offer.length}
                <button class="text-xs underline underline-offset-2" onclick={() => matchTo(p, offer[0].source)}
                  >Use {basename(offer[0].source)}</button
                >
              {/if}
            </div>
          {/if}
        </td>
      </tr>
    {/each}
    {#each result.jobs as j (j.source)}
      {@const flag = odd.get(j.source)}
      {@const alike = duplicateSubtitles(j.subtitle_info, excluded)}
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
          <span class="flex items-start gap-1.5"
            >{#if j.encode}{@render how(j.encode, j.matches?.[j.encode], j.details?.[j.encode])}{/if}{j.encode
              ? basename(j.encode) + (j.encode_state === 'in_progress' ? ' (still encoding)' : '')
              : 'new encode'}{#if j.encode && j.matches?.[j.encode] === 'manual'}{@render undo(j.encode)}{/if}</span
          >
        </td>
        <td class="py-1.5 pr-3 text-muted-foreground">
          {#if j.subtitle_info.length}
            <ul class="flex flex-col gap-0.5">
              {#each j.subtitle_info as s (s.path)}
                {@const off = excluded.includes(s.path)}
                {@const name = nameParts(basename(s.path), basename(j.source))}
                <li class="flex min-w-0 items-start gap-1.5">
                  {@render how(s.path, s.match, j.details?.[s.path], off)}
                  <Tip
                    class="min-w-0"
                    text="{s.path} ({s.language_name}). {off
                      ? 'Left out: click to add it back.'
                      : 'Click to leave it out.'}"
                  >
                    <button
                      class="flex min-w-0 flex-1 items-start gap-1.5 rounded-md text-left text-xs {off
                        ? 'text-muted-foreground/60 line-through'
                        : ''}"
                      aria-pressed={!off}
                      aria-label="{tag(s)}: {basename(s.path)}"
                      onclick={() => toggle(s.path)}
                      ><span
                        class="shrink-0 rounded-md px-1.5 whitespace-nowrap {off ? '' : 'bg-muted text-foreground'}"
                        >{tag(s)}</span
                      ><span class="min-w-0 [overflow-wrap:anywhere]"
                        ><span class="text-muted-foreground">{name.shared}</span><span
                          class={off ? '' : 'text-foreground'}>{name.rest}</span
                        ></span
                      ></button
                    >
                  </Tip>
                  {#if s.match === 'manual'}{@render undo(s.path)}{/if}
                </li>
              {/each}
            </ul>
          {:else}—{/if}
          {#if flag}
            <div class="mt-1 flex items-center gap-1 text-xs text-warning">
              <TriangleAlertIcon class="size-3 shrink-0" />{flag.count === 0
                ? 'No subtitles'
                : `${flag.count} subtitle${flag.count === 1 ? '' : 's'}`}; most have {flag.usual}
            </div>
          {/if}
          {#each alike as group (group[0])}
            <div class="mt-1 flex items-start gap-1 text-xs text-warning">
              <TriangleAlertIcon class="mt-0.5 size-3 shrink-0" /><span
                >{group.length} alike (same language and type): {group.map(basename).join(', ')}</span
              >
            </div>
          {/each}
        </td>
        <td class="text-muted-foreground">
          <span class="flex items-start gap-1.5"
            >{#if j.chapters}{@render how(j.chapters, j.matches?.[j.chapters], j.details?.[j.chapters])}{/if}{j.chapters
              ? basename(j.chapters)
              : 'AutoQPF'}{#if j.chapters && j.matches?.[j.chapters] === 'manual'}{@render undo(j.chapters)}{/if}</span
          >
        </td>
      </tr>
    {/each}
  </tbody>
</table>
