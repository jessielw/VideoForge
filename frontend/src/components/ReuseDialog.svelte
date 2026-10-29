<script lang="ts">
  // Asked on Start queue / Run selected when the jobs have finished files from an earlier run (any job on
  // the same source): per section (video, each audio encode), reuse it or make it again, StaxRip-like.
  // Files made with today's settings start ticked; ones made with other settings start unticked. A file another
  // job on the source made the same way is linked into this job's folder (origin: that job's folder).
  import PlayIcon from '@lucide/svelte/icons/play'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { basename, bytes, duration } from '../lib/format'
  import type { ReuseJob } from '../lib/types'

  let {
    open = $bindable(false),
    jobs,
    onstart,
  }: { open?: boolean; jobs: ReuseJob[]; onstart: (reuse: Record<string, string[]>) => void } = $props()

  let chosen = $state<Record<string, string[]>>({})
  $effect(() => {
    chosen = Object.fromEntries(jobs.map((j) => [j.id, j.offers.filter((o) => o.current).map((o) => o.id)]))
  })

  function toggle(job: string, offer: string, on: boolean) {
    const now = chosen[job] ?? []
    chosen[job] = on ? [...now.filter((o) => o !== offer), offer] : now.filter((o) => o !== offer)
  }

  function all(on: boolean) {
    chosen = Object.fromEntries(jobs.map((j) => [j.id, on ? j.offers.map((o) => o.id) : []]))
  }

  function when(epoch: number | null): string {
    return epoch == null
      ? ''
      : new Date(epoch * 1000).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  }

  const stale = $derived(jobs.some((j) => j.offers.some((o) => !o.current)))
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="sm:max-w-2xl">
    <Dialog.Header>
      <Dialog.Title>Reuse finished files?</Dialog.Title>
      <Dialog.Description>
        An earlier run already made these. Ticked ones are reused as they are; the others are made again.
        {#if stale}Files marked <em>other settings</em> were made before the job was changed.{/if}
      </Dialog.Description>
    </Dialog.Header>
    <div class="max-h-[60vh] space-y-4 overflow-y-auto pr-1" aria-label="Finished files">
      {#each jobs as job (job.id)}
        <section aria-label={job.name}>
          {#if jobs.length > 1}<h3 class="mb-1 truncate text-sm font-medium" title={job.name}>
              {job.name}{job.label ? ` (${job.label})` : ''}
            </h3>{/if}
          <ul class="divide-y divide-border rounded-md border border-border">
            {#each job.offers as offer (offer.id)}
              <li>
                <label class="flex cursor-pointer items-start gap-3 px-3 py-2 hover:bg-muted/50">
                  <Checkbox
                    class="mt-0.5"
                    checked={chosen[job.id]?.includes(offer.id) ?? false}
                    onCheckedChange={(v) => toggle(job.id, offer.id, v === true)}
                    aria-label="Reuse {offer.label}"
                  />
                  <span class="min-w-0 flex-1">
                    <span class="flex items-center gap-2 text-sm">
                      <span class="truncate">{offer.label}</span>
                      {#if offer.origin}
                        <Badge
                          variant="outline"
                          title="Made by the job in {offer.origin}/: linked into this job's folder"
                          >from {offer.origin}</Badge
                        >
                      {/if}
                      {#if !offer.current}
                        <Badge variant="outline" class="border-warning/40 bg-warning/10 text-warning"
                          >other settings</Badge
                        >
                      {/if}
                    </span>
                    <span class="block truncate text-xs text-muted-foreground" title={offer.file}>
                      {[
                        basename(offer.file),
                        bytes(offer.size),
                        offer.seconds ? `took ${duration(offer.seconds)}` : '',
                        when(offer.finished),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                </label>
              </li>
            {/each}
          </ul>
        </section>
      {/each}
    </div>
    <Dialog.Footer class="gap-2 sm:justify-between">
      <div class="flex gap-2">
        <Button variant="ghost" size="sm" onclick={() => all(true)}>Reuse all</Button>
        <Button variant="ghost" size="sm" onclick={() => all(false)}>Make all again</Button>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" onclick={() => (open = false)}>Cancel</Button>
        <Button onclick={() => onstart($state.snapshot(chosen))}><PlayIcon />Start</Button>
      </div>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
