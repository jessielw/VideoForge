<script lang="ts">
  // A source track's details, as the probe read them (mkvmerge and MediaInfo): opened from the info button
  // on its row, so the row itself stays short.
  import { basename, bytes, duration } from '../lib/format'
  import type { AudioTrack, SubTrack } from '../lib/types'
  import InfoIcon from '@lucide/svelte/icons/info'
  import { buttonVariants } from '$lib/components/ui/button'
  import * as Popover from '$lib/components/ui/popover'
  import Tip from './Tip.svelte'

  let { track }: { track: AudioTrack | SubTrack } = $props()

  const FLAGS = [
    ['default', 'Default'],
    ['forced', 'Forced'],
    ['hearing_impaired', 'SDH'],
    ['visual_impaired', 'Audio description'],
    ['commentary', 'Commentary'],
    ['original', 'Original language'],
  ] as const

  const rows = $derived.by((): [string, string][] => {
    const t = track
    const flags = FLAGS.filter(([key]) => t[key]).map(([, label]) => label)
    const common: [string, string][] = [
      ['Source', t.external_path ? `${t.external_path}${t.index ? ` (track ${t.index + 1})` : ''}` : `Track #${t.id}`],
      ['Language', t.language],
      ['Title', t.title || '—'],
    ]
    if ('codec' in t)
      return [
        ...common,
        ['Format', `${t.format_name || t.codec}${t.atmos ? ' Atmos' : t.dtsx ? ' DTS:X' : ''}`],
        ['Codec', t.codec],
        ['Channels', t.layout],
        ['Sample rate', t.sample_rate ? `${+(t.sample_rate / 1000).toFixed(1)} kHz` : ''],
        ['Bit depth', t.bit_depth ? `${t.bit_depth}-bit` : ''],
        ['Bitrate', t.bitrate_kbps ? `${t.bitrate_kbps.toLocaleString()} kb/s` : ''],
        ['Delay', `${t.delay_ms > 0 ? '+' : ''}${t.delay_ms} ms`],
        ['Duration', t.duration_ms ? duration(t.duration_ms / 1000) : ''],
        ['Size', t.size_bytes ? bytes(t.size_bytes) : ''],
        ['Flags', flags.join(', ') || '—'],
      ].filter(([, v]) => v) as [string, string][]
    const images = t.format === 'pgs' || t.format === 'vobsub'
    return [
      ...common,
      ['Format', t.format.toUpperCase()],
      ['Elements', t.element_count ? `${t.element_count.toLocaleString()} ${images ? 'images' : 'lines'}` : ''],
      ['Flags', flags.join(', ') || '—'],
    ].filter(([, v]) => v) as [string, string][]
  })
</script>

<Popover.Root>
  <Tip text="Track details">
    <Popover.Trigger>
      <!-- Not a <button>: the editor's fieldset disables those on a job that can't be edited, and the details
           are still worth reading then. The trigger handles Enter and Space. -->
      {#snippet child({ props })}
        <span
          {...props}
          role="button"
          tabindex="0"
          class="{buttonVariants({ variant: 'ghost', size: 'icon-sm' })} text-muted-foreground"
          aria-label="Track details"><InfoIcon /></span
        >
      {/snippet}
    </Popover.Trigger>
  </Tip>
  <Popover.Content align="end" class="w-80">
    <div class="font-medium wrap-anywhere">
      {track.external_path ? basename(track.external_path) : `Track #${track.id}`}
    </div>
    <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      {#each rows as [label, value] (label)}
        <dt class="text-muted-foreground">{label}</dt>
        <dd class="wrap-anywhere tabular-nums">{value}</dd>
      {/each}
    </dl>
  </Popover.Content>
</Popover.Root>
