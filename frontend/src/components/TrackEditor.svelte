<script lang="ts">
  // The full track editor, for profiles that follow it (track_editor, e.g. manual): the audio or
  // the subtitle tracks (one kind per tab) in output order. Drag a track by its handle (or use
  // the arrows) to reorder, untick it to leave it out, edit its title, language and flags, and
  // copy or encode each audio track, or burn one subtitle track into the video. Every change saves and
  // replans; each track shows its source at a glance and what will be written.
  // Files can be added to the job here and removed again, and an audio track can be used more
  // than once ("Add a track from…": a copy with its own encode, title and flags).
  import type { InputChanges } from '../lib/api'
  import { emptyOverride, isEmpty, shownOptions, subtitleName } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import type { AudioAction, AudioEncodeInfo, AudioTrack, EncodeOptionInfo, JobDetail, Overrides, PlannedAudio, SubTrack, TrackOverride } from '../lib/types'
  import FileBrowser from './FileBrowser.svelte'
  import SubtitleSelectionMenu from './SubtitleSelectionMenu.svelte'
  import AudioPresetMenu from './AudioPresetMenu.svelte'
  import { applyAudioPreset, audioEncodeLayouts, audioPresetSettings } from '../lib/audioPresets'
  import { selectSubtitles } from '../lib/subtitleSelection'
  import { drops, pathDrop } from '../lib/dropPaths.svelte'
  import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import AudioLinesIcon from '@lucide/svelte/icons/audio-lines'
  import CaptionsIcon from '@lucide/svelte/icons/captions'
  import CheckIcon from '@lucide/svelte/icons/check'
  import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
  import CopyPlusIcon from '@lucide/svelte/icons/copy-plus'
  import FilePlusIcon from '@lucide/svelte/icons/file-plus'
  import FlameIcon from '@lucide/svelte/icons/flame'
  import GripVerticalIcon from '@lucide/svelte/icons/grip-vertical'
  import LayoutTemplateIcon from '@lucide/svelte/icons/layout-template'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import SlidersHorizontalIcon from '@lucide/svelte/icons/sliders-horizontal'
  import TagIcon from '@lucide/svelte/icons/tag'
  import XIcon from '@lucide/svelte/icons/x'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { Toggle } from '$lib/components/ui/toggle'
  import LanguagePicker from './LanguagePicker.svelte'

  type Kind = 'audio' | 'sub'
  type Track = AudioTrack | SubTrack

  let {
    job,
    save,
    saveInputs,
    editable,
    kind,
  }: {
    job: JobDetail
    save: (o: Overrides) => Promise<void>
    saveInputs: (inputs: InputChanges) => Promise<void>
    editable: boolean
    kind: Kind
  } = $props()

  // --- the job's files ---
  const SUB_EXTENSIONS = ['.srt', '.ass', '.ssa', '.sup', '.idx']
  const AUDIO_EXTENSIONS = ['.ac3', '.eac3', '.ec3', '.dts', '.dtshd', '.thd', '.truehd', '.mlp', '.flac', '.wav', '.w64',
    '.m4a', '.aac', '.mka', '.opus', '.ogg']
  let browsing = $state(false)
  const sourceDir = $derived(job.spec.inputs.source.replace(/[\\/][^\\/]*$/, ''))
  const sameFile = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()
  const inputList = (k: Kind) => (k === 'audio' ? job.spec.inputs.audio : job.spec.inputs.subtitles)
  const listChange = (k: Kind, list: string[]): InputChanges => (k === 'audio' ? { audio: list } : { subtitles: list })

  // Picked files (or folders: the server takes each one's files of this kind) join this kind's list.
  function addFiles(paths: string[]) {
    const have = inputList(kind)
    const add = paths.filter(p => !have.some(s => sameFile(s, p)))
    if (add.length) saveInputs(listChange(kind, [...have, ...add]))
  }

  const removeFile = (path: string) => saveInputs(listChange(kind, inputList(kind).filter(s => !sameFile(s, path))))

  const overrides = $derived(job.spec.overrides)
  const plan = $derived(job.plan)
  const tracks = $derived(job.tracks)
  const properties = $derived(app.profiles.find(p => p.id === job.profile)?.track_properties.filter(p => p.kind === kind) ?? [])

  const isAudio = (t: Track): t is AudioTrack => 'codec' in t
  const basename = (p: string) => p.split(/[\\/]/).pop() ?? p

  // Output order: the saved order (track keys) first, the rest in source order. A list of
  // audio track ids (set from the simpler tracks tab) leads for audio when it's there.
  function inOrder<T extends Track>(list: T[]): T[] {
    const ids = overrides.audio_track_ids
    const order = overrides.order ?? []
    const rank = (t: T) => {
      const i = ids && isAudio(t) && !t.external_path && !t.copy ? ids.indexOf(t.id) : order.indexOf(t.key)
      return i < 0 ? 10_000 + list.indexOf(t) : i
    }
    return [...list].sort((a, b) => rank(a) - rank(b))
  }

  const audioRows = $derived(inOrder(tracks?.audio ?? []))
  const subRows = $derived(inOrder(tracks?.subs ?? []))
  const rows = $derived<Track[]>(kind === 'audio' ? audioRows : subRows)
  // Planned audio by track key: ids repeat across added files and copies.
  const audioKey = (t: Pick<AudioTrack, 'id' | 'index' | 'external_path' | 'copy'>) =>
    (t.external_path ? `ext:${basename(t.external_path)}${t.index ? `#${t.index}` : ''}` : `id:${t.id}`) +
    (t.copy ? `+${t.copy}` : '')
  const plannedAudio = $derived(new Map((plan?.audio ?? []).map((a, i) => [audioKey(a.source), { pos: i, a }])))
  const plannedSubs = $derived(
    new Map(
      (plan?.subs ?? []).map((s, i) => [s.source.external_path ? `ext:${basename(s.source.external_path)}` : `id:${s.source.id}`, i]),
    ),
  )

  const ovOf = (t: Track): TrackOverride | undefined => overrides.tracks[t.key]
  const excluded = (t: Track) =>
    !!ovOf(t)?.exclude ||
    (!!overrides.audio_track_ids && isAudio(t) && !t.external_path && !t.copy && !overrides.audio_track_ids.includes(t.id))
  const outPos = (t: Track) => (isAudio(t) ? plannedAudio.get(t.key)?.pos : plannedSubs.get(t.key))

  // A copy of the overrides to change, in the editor's terms: an audio id list becomes
  // order + exclusions, so the two ways of choosing tracks never disagree.
  function draft(): Overrides {
    const o = structuredClone($state.snapshot(overrides)) as Overrides
    o.copies ??= []
    if (o.audio_track_ids) {
      for (const t of audioRows)
        if (!t.external_path && !t.copy && !o.audio_track_ids.includes(t.id)) edit(o, t.key, ov => (ov.exclude = true))
      o.audio_track_ids = null
    }
    return o
  }

  function edit(o: Overrides, key: string, change: (ov: TrackOverride) => void) {
    const ov = o.tracks[key] ?? emptyOverride()
    change(ov)
    if (isEmpty(ov)) delete o.tracks[key]
    else o.tracks[key] = ov
  }

  function commit(o: Overrides, audio: Track[] = audioRows, subs: Track[] = subRows) {
    o.order = [...audio, ...subs].map(t => t.key)
    save(o)
  }

  function editTrack(t: Track, change: (ov: TrackOverride) => void) {
    const o = draft()
    edit(o, t.key, change)
    commit(o)
  }

  const setIncluded = (t: Track, on: boolean) => editTrack(t, ov => (ov.exclude = on ? null : true))

  function selectSubs(include: (t: SubTrack) => boolean) {
    const o = draft()
    selectSubtitles(o, subRows, include)
    commit(o)
  }

  // Name the kept subtitles from their language and flags ("English (SDH)"), StaxRip's "Set names": the
  // untitled ones, or all. A flag the profile doesn't offer is the track's own.
  const titleOf = (t: Track) => ovOf(t)?.title ?? t.title
  const nameFlag = (t: SubTrack, key: 'forced' | 'hearing_impaired' | 'commentary') =>
    properties.some(p => p.key === key) ? flagOn(t, key) : t[key]
  const subName = (t: SubTrack) =>
    subtitleName(ovOf(t)?.language ?? t.language, {
      forced: nameFlag(t, 'forced'),
      hearing_impaired: nameFlag(t, 'hearing_impaired'),
      commentary: nameFlag(t, 'commentary'),
    })
  const untitled = $derived(subRows.filter(t => !excluded(t) && !titleOf(t).trim()).length)
  function nameSubs(all: boolean) {
    const o = draft()
    for (const t of subRows as SubTrack[]) {
      if (excluded(t) || (!all && titleOf(t).trim())) continue
      const name = subName(t)
      edit(o, t.key, ov => (ov.title = name === t.title ? null : name))
    }
    commit(o)
  }

  // Burning a subtitle in: one track per job (marking one unmarks the others); it leaves the mux. Only an
  // encode can take it, and only the formats SubText draws (core.video.burn).
  const BURNS = ['srt', 'ass', 'pgs', 'vobsub']
  const burnKey = $derived(plan?.burn ? (plan.burn.external_path ? `ext:${basename(plan.burn.external_path)}` : `id:${plan.burn.id}`) : null)
  const canBurn = (t: Track) => !isAudio(t) && !job.spec.inputs.encode && BURNS.includes(t.format)
  function setBurn(t: Track, on: boolean) {
    const o = draft()
    for (const s of subRows) edit(o, s.key, ov => (ov.burn = s.key === t.key && on ? true : null))
    commit(o)
  }
  const setTitle = (t: Track, v: string) => editTrack(t, ov => (ov.title = v === t.title ? null : v))
  const setLanguage = (t: Track, v: string) => editTrack(t, ov => (ov.language = !v || v === t.language ? null : v))

  // Where a set value comes from: the last template set it for this track, or a hand edit
  // (a template's value changed counts as one). Unset: as the profile has it, no mark.
  type Mark = 'template' | 'hand' | null
  const chosen = $derived(kind === 'audio' ? job.spec.audio_from_template : job.spec.subs_from_template)
  function mark(t: Track, get: (ov: TrackOverride | undefined) => unknown): Mark {
    const now = get(ovOf(t))
    if (now === null || now === undefined) return null
    const tpl = chosen?.tracks[t.key]
    return tpl && get(tpl) === now ? 'template' : 'hand'
  }
  const NOTE = { template: ' (from the template)', hand: ' (changed by you)' }
  const note = (m: Mark) => (m ? NOTE[m] : '')
  const INPUT_MARK = { template: 'border-info/60', hand: 'border-warning/60' }
  const SELECT_MARK = { template: '[&>select]:border-info/60', hand: '[&>select]:border-warning/60' }
  const FLAG_MARK = {
    template: 'underline decoration-info decoration-dotted underline-offset-2',
    hand: 'underline decoration-warning decoration-dotted underline-offset-2',
  }

  const flagOn = (t: Track, key: string) => ovOf(t)?.flags[key] ?? t.detected[key] ?? false
  const flagMark = (t: Track, key: string) => mark(t, ov => ov?.flags[key])
  function toggleFlag(t: Track, key: string) {
    const on = !flagOn(t, key)
    editTrack(t, ov => {
      if (on === (t.detected[key] ?? false)) delete ov.flags[key]
      else ov.flags[key] = on
    })
  }

  // --- copies: another output track from the same audio track ---
  const isCopyOf = (t: AudioTrack, base: AudioTrack) => t.key === base.key || t.key.startsWith(`${base.key}+`)
  function addCopy(base: AudioTrack) {
    const o = draft()
    let n = 1
    while (o.copies.includes(`${base.key}+${n}`)) n++
    const key = `${base.key}+${n}`
    o.copies = [...o.copies, key]
    const keys = audioRows.map(t => t.key)
    const last = Math.max(...audioRows.map((t, i) => (isCopyOf(t, base) ? i : -1)))
    keys.splice(last + 1, 0, key) // just after the track and its other copies
    o.order = [...keys, ...subRows.map(t => t.key)]
    save(o)
  }

  function removeCopy(t: AudioTrack) {
    const o = draft()
    o.copies = o.copies.filter(k => k !== t.key)
    delete o.tracks[t.key]
    o.order = (o.order ?? []).filter(k => k !== t.key)
    save(o)
  }

  // --- audio encodes ---
  const CODEC: Record<string, string> = {
    eac3: 'E-AC-3', ac3: 'AC-3', aac: 'AAC', truehd: 'TrueHD', dts: 'DTS', dts_hd_ma: 'DTS-HD MA',
    dts_hd_hra: 'DTS-HD HRA', lpcm: 'LPCM', flac: 'FLAC', opus: 'Opus',
  }
  const channels = (layout: string) => layout.split('.').reduce((n, x) => n + +x, 0)
  const actionOf = (t: AudioTrack): AudioAction => ovOf(t)?.action ?? 'copy'
  const canAtmos = (t: AudioTrack) => t.atmos && t.codec === 'truehd'
  // The encodes come from the server; one whose tools are missing can't be picked (one already
  // picked stays, and blocks the job). Atmos is offered for TrueHD Atmos sources only.
  const encodeOf = (a: AudioAction) => app.encodes.find(e => e.id === a)
  const needs = (e: AudioEncodeInfo) => (e.missing.length ? ` (needs ${e.missing.join(', ')})` : '')
  const offered = (t: AudioTrack, current: AudioAction) => app.encodes.filter(e => e.id !== 'atmos' || canAtmos(t) || current === 'atmos')

  // The layouts an encode can make from this track: no upmix (DDP's 5.0 -> 5.1 aside).
  function layoutChoices(t: AudioTrack, e: AudioEncodeInfo): string[] {
    return audioEncodeLayouts(e, ovOf(t)?.options).filter(l => channels(l) <= channels(t.layout) || (e.id === 'ddp' && t.layout === '5.0' && l === '5.1'))
  }

  const setAction = (t: AudioTrack, a: AudioAction) =>
    editTrack(t, ov => {
      ov.action = a === 'copy' ? null : a
      ov.layout = ov.bitrate_kbps = null
      ov.options = {}
    })

  // The encode's own settings, folded away under a "Settings" toggle per track.
  let openSettings = $state<Record<string, boolean>>({})
  const setOption = (t: AudioTrack, o: EncodeOptionInfo, v: string) =>
    editTrack(t, ov => {
      ov.options ??= {}
      if (v.trim() === o.default || !v.trim() && !o.choices.length && !o.range) delete ov.options[o.key]
      else ov.options[o.key] = v.trim()
      if (o.key === 'ddp_mode' && v.trim() === 'bluray' && ov.layout !== '7.1') ov.layout = null
    })
  const changedOptions = (t: AudioTrack, e: AudioEncodeInfo) =>
    e.options.filter(o => ovOf(t)?.options?.[o.key] !== undefined).length
  const setLayout = (t: AudioTrack, v: string) => editTrack(t, ov => (ov.layout = v || null))
  function setDelay(t: AudioTrack, input: HTMLInputElement) {
    const v = input.value
    const n = Math.round(Number(v))
    // Show the total delay, but keep the saved correction relative to the source so its
    // timestamps (or an encoder's built-in delay) aren't applied a second time.
    const correction = v.trim() && Number.isFinite(n) ? n - t.delay_ms : 0
    // Restore the visible value even when clearing an already unmodified delay; its
    // saved value doesn't change, so Svelte otherwise leaves the input blank.
    input.value = String(t.delay_ms + correction)
    editTrack(t, ov => (ov.sync_ms = correction || null))
  }
  function setBitrate(t: AudioTrack, v: string) {
    const n = Math.round(+v)
    editTrack(t, ov => (ov.bitrate_kbps = v.trim() && n > 0 ? n : null))
  }

  function audioOut(p: PlannedAudio): string {
    const codec = (CODEC[p.out_codec] ?? p.out_codec) + (p.out_atmos ? ' Atmos' : '')
    if (p.action === 'copy') return `copied · ${codec} ${p.out_layout}`
    const rate = p.bitrate_kbps ? `${p.bitrate_kbps} kb/s` : encodeOf(p.action as AudioAction)?.bitrates === null ? 'lossless' : 'quality VBR'
    return `${codec} ${p.out_layout} · ${rate}${p.upmix_50 ? ' · 5.0 upmixed to 5.1' : ''}`
  }

  // --- the source at a glance ---
  function sourceLabel(t: Track): string {
    if (isAudio(t)) {
      const fmt = t.format_name || CODEC[t.codec] || t.codec
      const where = t.external_path ? `${basename(t.external_path)}${t.index ? ` #${t.index + 1}` : ''}:` : `#${t.id}`
      return `${where} ${fmt}${t.atmos ? ' Atmos' : t.dtsx ? ' DTS:X' : ''} ${t.layout}`
    }
    return t.external_path ? `${basename(t.external_path)} (${t.format.toUpperCase()})` : `#${t.id} ${t.format.toUpperCase()}`
  }

  function duration(ms: number): string {
    const s = Math.round(ms / 1000)
    const [h, m] = [Math.floor(s / 3600), Math.floor((s % 3600) / 60)]
    return `${h ? `${h}:${String(m).padStart(2, '0')}` : m}:${String(s % 60).padStart(2, '0')}`
  }

  function size(bytes: number): string {
    const units = ['B', 'KB', 'MB', 'GB']
    let n = bytes
    let u = 0
    while (n >= 1024 && u < units.length - 1) [n, u] = [n / 1024, u + 1]
    return `${n.toFixed(u && n < 10 ? 1 : 0)} ${units[u]}`
  }

  function details(t: Track): string[] {
    if (!isAudio(t)) {
      const images = t.format === 'pgs' || t.format === 'vobsub'
      return t.element_count ? [`${t.element_count.toLocaleString()} ${images ? 'images' : 'lines'}`] : []
    }
    return [
      t.sample_rate ? `${+(t.sample_rate / 1000).toFixed(1)} kHz` : '',
      t.bit_depth ? `${t.bit_depth}-bit` : '',
      t.bitrate_kbps ? `${t.bitrate_kbps.toLocaleString()} kb/s` : '',
      t.delay_ms ? `delay ${t.delay_ms > 0 ? '+' : ''}${t.delay_ms} ms` : '',
      t.duration_ms ? duration(t.duration_ms) : '',
      t.size_bytes ? size(t.size_bytes) : '',
    ].filter(Boolean)
  }

  // --- reordering: drag the handle, or the arrows ---
  let drag = $state<string | null>(null)
  let dropAt = $state<number | null>(null) // insert before this row

  function move(key: string, to: number) {
    const list = [...rows]
    const from = list.findIndex(t => t.key === key)
    const target = to > from ? to - 1 : to
    if (from < 0 || target === from || target < 0 || target >= list.length) return
    const [t] = list.splice(from, 1)
    list.splice(target, 0, t)
    const o = draft()
    if (kind === 'audio') commit(o, list, subRows)
    else commit(o, audioRows, list)
  }

  function dragStart(e: DragEvent, t: Track) {
    drag = t.key
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', t.key)
      const row = (e.currentTarget as HTMLElement).closest('[data-row]')
      if (row) e.dataTransfer.setDragImage(row, 16, 16)
    }
  }

  function dragOver(e: DragEvent, i: number) {
    if (drag === null) return
    e.preventDefault()
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    dropAt = e.clientY < r.top + r.height / 2 ? i : i + 1
  }

  function drop(e: DragEvent) {
    e.preventDefault()
    if (drag !== null && dropAt !== null) move(drag, dropAt)
    drag = dropAt = null
  }

  // Back to the profile's choices for this kind (the other tab's edits stay).
  function reset() {
    const o = draft()
    const mine = new Set(rows.map(t => t.key))
    for (const key of Object.keys(o.tracks)) if (mine.has(key)) delete o.tracks[key]
    if (kind === 'audio') o.copies = []
    o.order = (o.order ?? []).filter(key => !mine.has(key))
    save(o)
  }

  // Back to what the last template set for this kind: its tracks, copies and order; tracks it
  // didn't decide (e.g. added files) go back to the profile's choices.
  function backToTemplate() {
    if (!chosen) return
    const tpl = $state.snapshot(chosen) as typeof chosen
    const o = draft()
    const mine = new Set([...rows.map(t => t.key), ...Object.keys(tpl.tracks)])
    for (const key of Object.keys(o.tracks)) if (mine.has(key)) delete o.tracks[key]
    for (const [key, ov] of Object.entries(tpl.tracks)) if (!isEmpty(ov)) o.tracks[key] = ov
    if (kind === 'audio') o.copies = [...tpl.copies]
    o.order = [...(o.order ?? []).filter(key => !mine.has(key)), ...(tpl.order ?? [])]
    save(o)
  }

  function setOriginal(tag: string) {
    const o = draft()
    o.original_language = tag || null
    save(o)
  }

  const title = $derived(kind === 'audio' ? 'Audio' : 'Subtitles')
</script>

{#snippet trackRow(t: Track, i: number, count: number)}
  {@const ov = ovOf(t)}
  {@const burned = burnKey === t.key}
  {@const off = excluded(t) || burned}
  {@const pos = outPos(t)}
  {@const copy = isAudio(t) && t.copy ? t : null}
  {#if dropAt === i}<div class="-my-1 h-0.5 rounded-full bg-primary"></div>{/if}
  <div
    data-row
    role="listitem"
    class="rounded-lg border bg-card {drag === t.key ? 'opacity-40' : ''}"
    ondragover={e => dragOver(e, i)}
    ondrop={drop}
  >
    <div class="flex items-center gap-2 px-2 py-1.5">
      <span
        class="rounded-md p-0.5 text-muted-foreground {editable ? 'cursor-grab hover:bg-accent hover:text-foreground' : 'opacity-40'}"
        draggable={editable}
        ondragstart={e => dragStart(e, t)}
        ondragend={() => (drag = dropAt = null)}
        title="Drag to reorder"
        role="button"
        tabindex="-1"><GripVerticalIcon class="size-4" /></span
      >
      <Checkbox
        checked={!off}
        title="In the output{note(mark(t, o => o?.exclude))}"
        aria-label="In the output"
        onCheckedChange={v => setIncluded(t, v)}
      />
      <span class="w-5 text-center text-xs {off ? 'text-muted-foreground' : 'text-primary'}">{pos === undefined ? '–' : pos + 1}</span>
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm {off ? 'text-muted-foreground line-through' : ''}" title={t.title}>
          <span class="font-medium">{sourceLabel(t)}</span>
          <span class="text-muted-foreground">· {t.language}{t.title ? ` · ${t.title}` : ''}</span>
        </div>
        {#if details(t).length}
          <div class="flex flex-wrap gap-x-3 text-xs text-muted-foreground tabular-nums" data-details>
            {#each details(t) as d (d)}<span>{d}</span>{/each}
          </div>
        {/if}
      </div>
      {#if !isAudio(t) && (canBurn(t) || ov?.burn)}
        <Toggle
          variant="outline"
          size="sm"
          class="h-6 rounded-full px-2 text-xs font-normal text-muted-foreground data-[state=on]:border-primary data-[state=on]:bg-primary/15
            data-[state=on]:text-primary"
          pressed={!!ov?.burn}
          title={burned
            ? 'Burned into the video (not muxed): image subtitles before the crop, text after it'
            : 'Burn this track into the video instead of muxing it (one per job)'}
          onPressedChange={on => setBurn(t, on)}><FlameIcon class="size-3" />Burn in</Toggle
        >
      {/if}
      {#if copy}
        <Badge variant="outline" class="border-primary/40 bg-primary/10 text-primary" title="Another output track from {sourceLabel(t)}"
          >copy {copy.copy}</Badge
        >
        <Button
          variant="ghost"
          size="icon-sm"
          class="hover:text-destructive"
          onclick={() => removeCopy(copy)}
          title="Remove this copy"
          aria-label="Remove this copy"
        >
          <XIcon />
        </Button>
      {:else if t.external_path}
        {@const path = t.external_path}
        <Badge variant="secondary" class="text-muted-foreground" title={path}>added</Badge>
        <Button
          variant="ghost"
          size="icon-sm"
          class="hover:text-destructive"
          onclick={() => removeFile(path)}
          title="Remove this file from the job"
          aria-label="Remove this file from the job"
        >
          <XIcon />
        </Button>
      {/if}
      <Button variant="ghost" size="icon-sm" disabled={i === 0} onclick={() => move(t.key, i - 1)} aria-label="Move up">
        <ArrowUpIcon />
      </Button>
      <Button variant="ghost" size="icon-sm" disabled={i === count - 1} onclick={() => move(t.key, i + 2)} aria-label="Move down">
        <ArrowDownIcon />
      </Button>
    </div>
    {#if !off}
      {@const titleMark = mark(t, o => o?.title)}
      {@const langMark = mark(t, o => o?.language)}
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border/60 px-3 py-2 text-sm">
        <Input
          class="w-64 {titleMark ? INPUT_MARK[titleMark] : ''}"
          placeholder="No title"
          value={ov?.title ?? t.title}
          title={titleMark ? `Title${note(titleMark)}` : undefined}
          aria-label="Title"
          onchange={e => setTitle(t, e.currentTarget.value)}
        />
        <LanguagePicker
          class="w-28 {langMark ? INPUT_MARK[langMark] : ''}"
          show="tag"
          clearable={false}
          value={ov?.language ?? t.language}
          title={langMark ? `Language${note(langMark)}` : undefined}
          aria-label="Language"
          onchange={(v: string) => setLanguage(t, v)}
        />
        <div class="flex flex-wrap gap-1" role="group" aria-label="Track flags">
          {#each properties as f (f.key)}
            {@const on = flagOn(t, f.key)}
            {@const fm = flagMark(t, f.key)}
            <Toggle
              variant="outline"
              size="sm"
              class="h-6 rounded-full px-2 text-xs font-normal text-muted-foreground data-[state=on]:border-primary data-[state=on]:bg-primary/15
                data-[state=on]:text-primary {fm ? FLAG_MARK[fm] : ''}"
              pressed={on}
              title="{f.help}{note(fm)}"
              onPressedChange={() => toggleFlag(t, f.key)}
              >{#if on}<CheckIcon class="size-3" />{/if}{f.label}</Toggle
            >
          {/each}
        </div>
      </div>
      {#if isAudio(t)}
        {@const action = actionOf(t)}
        {@const planned = plannedAudio.get(t.key)?.a}
        {@const enc = encodeOf(action)}
        {@const actionMark = mark(t, o => o?.action)}
        {@const layoutMark = mark(t, o => o?.layout)}
        {@const bitrateMark = mark(t, o => o?.bitrate_kbps)}
        {@const delayMark = mark(t, o => o?.sync_ms)}
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border/60 px-3 py-2 text-sm">
          <AudioPresetMenu current={audioPresetSettings(ov)} source={t} disabled={!editable}
            apply={preset => editTrack(t, value => Object.assign(value, applyAudioPreset(value, preset)))} />
          <NativeSelect
            value={action}
            class={actionMark ? SELECT_MARK[actionMark] : ''}
            title={actionMark ? `Copy or encode${note(actionMark)}` : undefined}
            aria-label="Copy or encode"
            onchange={e => setAction(t, e.currentTarget.value as AudioAction)}
          >
            <option value="copy">Copy</option>
            {#each offered(t, action) as e (e.id)}
              <option value={e.id} disabled={!!e.missing.length && action !== e.id}>Encode: {e.label}{needs(e)}</option>
            {/each}
          </NativeSelect>
          {#if enc && enc.layouts.length > 1}
            <NativeSelect
              value={ov?.layout ?? ''}
              class={layoutMark ? SELECT_MARK[layoutMark] : ''}
              title={layoutMark ? `Channels${note(layoutMark)}` : undefined}
              aria-label="Channels"
              onchange={e => setLayout(t, e.currentTarget.value)}
            >
              <option value="">Channels: auto{planned && !ov?.layout ? ` (${planned.out_layout})` : ''}</option>
              {#each layoutChoices(t, enc) as l (l)}<option value={l}>{l}</option>{/each}
            </NativeSelect>
          {/if}
          {#if enc && enc.bitrates !== null}
            <label class="flex items-center gap-1.5 text-muted-foreground">
              {#if enc.bitrate_choices.length}
                <NativeSelect
                  value={ov?.bitrate_kbps ?? ''}
                  class={bitrateMark ? SELECT_MARK[bitrateMark] : ''}
                  title={bitrateMark ? `Bitrate${note(bitrateMark)}` : undefined}
                  aria-label="Bitrate"
                  onchange={e => setBitrate(t, e.currentTarget.value)}
                >
                  <option value="">auto{planned?.bitrate_kbps && !ov?.bitrate_kbps ? ` (${planned.bitrate_kbps})` : ''}</option>
                  {#each enc.bitrate_choices as b (b)}<option value={b}>{b}</option>{/each}
                </NativeSelect>
              {:else}
                <Input
                  class="w-24 {bitrateMark ? INPUT_MARK[bitrateMark] : ''}"
                  title={bitrateMark ? `Bitrate${note(bitrateMark)}` : undefined}
                  type="number"
                  min="6"
                  step="8"
                  placeholder={enc.vbr_default ? 'VBR' : String(planned?.bitrate_kbps ?? '')}
                  value={ov?.bitrate_kbps ?? ''}
                  aria-label="Bitrate"
                  onchange={e => setBitrate(t, e.currentTarget.value)}
                />
              {/if}kb/s
            </label>
          {/if}
          <label
            class="flex items-center gap-1.5 text-muted-foreground"
            title="Total delay relative to video: + later, − earlier. Detected delay: {t.delay_ms > 0 ? '+' : ''}{t.delay_ms} ms. Clear to restore the detected delay. Only the mux changes: an encode isn't made again."
          >
            Delay
            <Input
              class="w-20 {delayMark ? INPUT_MARK[delayMark] : ''}"
              type="number"
              step="1"
              placeholder={String(t.delay_ms)}
              value={t.delay_ms + (ov?.sync_ms ?? 0)}
              aria-label="Delay (ms)"
              onchange={e => setDelay(t, e.currentTarget)}
            />ms
          </label>
          {#if enc?.options.length}
            {@const changed = changedOptions(t, enc)}
            <Button
              variant="ghost"
              size="sm"
              class={openSettings[t.key] ? 'text-primary hover:text-primary' : ''}
              aria-expanded={!!openSettings[t.key]}
              onclick={() => (openSettings[t.key] = !openSettings[t.key])}
              title="{enc.label} settings"
            >
              <SlidersHorizontalIcon />Settings{changed ? ` (${changed})` : ''}
            </Button>
          {/if}
          {#if planned}<span class="text-xs text-muted-foreground">→ {audioOut(planned)}</span>{/if}
        </div>
        {#if enc?.options.length && openSettings[t.key]}
          <div class="grid gap-x-4 gap-y-2 border-t border-border/60 px-3 py-2 text-sm sm:grid-cols-[12rem_1fr]">
            {#each shownOptions(enc.options, o => ov?.options?.[o.key] ?? planned?.options?.[o.key] ?? o.default) as o (o.key)}
              {@const value = ov?.options?.[o.key] ?? planned?.options?.[o.key] ?? o.default}
              <label class="text-muted-foreground" for="opt-{t.key}-{o.key}" title={o.help}>{o.label}</label>
              <div class="flex items-center gap-2">
                {#if o.choices.length}
                  <NativeSelect id="opt-{t.key}-{o.key}" {value} onchange={e => setOption(t, o, e.currentTarget.value)}>
                    {#each o.choices as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
                  </NativeSelect>
                {:else if o.range}
                  <Input id="opt-{t.key}-{o.key}" class="w-24" type="number" min={o.range[0]} max={o.range[1]} step={o.step}
                    {value} onchange={e => setOption(t, o, e.currentTarget.value)} />
                {:else}
                  <Input id="opt-{t.key}-{o.key}" class="min-w-0 flex-1 font-mono text-xs" {value} placeholder={o.help}
                    onchange={e => setOption(t, o, e.currentTarget.value)} />
                {/if}
                {#if o.help && (o.choices.length || o.range)}<span class="text-xs text-muted-foreground">{o.help}</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    {/if}
  </div>
  {#if i === count - 1 && dropAt === count}<div class="-my-1 h-0.5 rounded-full bg-primary"></div>{/if}
{/snippet}

{#if !tracks || !plan}
  <div class="p-6 text-muted-foreground">{job.status === 'probing' ? 'Probing the source…' : 'No tracks: the source could not be read.'}</div>
{:else}
  <fieldset disabled={!editable} class="max-w-5xl space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <label class="flex items-center gap-2 text-sm text-muted-foreground">
        Original language
        <LanguagePicker
          class="w-48"
          aria-label="Original language"
          placeholder="Not set"
          value={overrides.original_language ?? ''}
          onchange={(v: string) => setOriginal(v)}
        />
      </label>
      <div class="ml-auto flex flex-wrap gap-2">
        {#if kind === 'audio'}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger disabled={!editable} title="Use a track again: another output track with its own encode, title and flags">
              {#snippet child({ props })}
                <Button {...props} variant="outline"><CopyPlusIcon />Add a track from…</Button>
              {/snippet}
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end" class="w-auto max-w-[32rem]">
              {#each audioRows.filter(t => !t.copy) as t (t.key)}
                <DropdownMenu.Item onSelect={() => addCopy(t)}>
                  <span class="truncate">{sourceLabel(t)} · {t.language}{t.title ? ` · ${t.title}` : ''}</span>
                </DropdownMenu.Item>
              {/each}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        {/if}
        <Button variant="outline" onclick={() => (browsing = true)} title="Add {kind === 'audio' ? 'audio' : 'subtitle'} files to this job">
          <FilePlusIcon />Add files…
        </Button>
        {#if chosen}
          <Button variant="outline" onclick={backToTemplate} title="Back to what the template set for these tracks">
            <LayoutTemplateIcon />Back to template
          </Button>
        {/if}
        <Button variant="outline" onclick={reset} title="Back to the profile's choices for these tracks"><RefreshCwIcon />Reset</Button>
      </div>
    </div>

    <section
      class="-m-2 rounded-lg p-2 outline-none"
      aria-label="{title} (drop or paste files to add them)"
      use:pathDrop={{
        rule: { mode: 'files', extensions: kind === 'audio' ? AUDIO_EXTENSIONS : SUB_EXTENSIONS, label: title },
        accept: addFiles,
        disabled: !editable,
      }}
    >
      <div class="mb-2 flex items-center gap-2">
        {#if kind === 'audio'}<AudioLinesIcon class="size-4 text-primary" />{:else}<CaptionsIcon class="size-4 text-primary" />{/if}
        <span class="font-medium">{title}</span>
        <span class="text-xs text-muted-foreground">{rows.filter(t => !excluded(t)).length} of {rows.length} in the output</span>
        <span class="ml-auto text-xs text-muted-foreground"
          >Drag a track by its handle to reorder; {drops.desktop ? 'drop' : 'paste'} files here to add them; every change saves.</span
        >
      </div>
      {#if kind === 'sub'}
        <div class="mb-3 flex flex-wrap gap-2">
          <SubtitleSelectionMenu tracks={subRows} {overrides} disabled={!editable} onselect={selectSubs} />
          <DropdownMenu.Root>
            <DropdownMenu.Trigger disabled={!editable || !subRows.length} title="Title the kept subtitles from their language and flags">
              {#snippet child({ props })}
                <Button {...props} variant="outline" size="sm"><TagIcon />Name subtitles<ChevronDownIcon class="size-3.5 text-muted-foreground" /></Button>
              {/snippet}
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="start" class="w-72">
              <DropdownMenu.Label>Language and flags: English (Forced), English (SDH)</DropdownMenu.Label>
              <DropdownMenu.Item disabled={!untitled} onSelect={() => nameSubs(false)}>
                Name untitled tracks<span class="ml-auto text-xs text-muted-foreground tabular-nums">{untitled}</span>
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => nameSubs(true)}>Rename all kept tracks</DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      {/if}
      {#if rows.length}
        <div class="space-y-2" role="list">
          {#each rows as t, i (t.key)}
            {@render trackRow(t, i, rows.length)}
          {/each}
        </div>
      {:else}
        <p class="text-sm text-muted-foreground">None in the source or added.</p>
      {/if}
    </section>
  </fieldset>
{/if}

{#if browsing}
  <FileBrowser
    title={kind === 'audio' ? 'Add audio files' : 'Add subtitle files'}
    extensions={kind === 'audio' ? AUDIO_EXTENSIONS : SUB_EXTENSIONS}
    start={sourceDir}
    onpick={paths => {
      addFiles(paths)
      browsing = false
    }}
    onclose={() => (browsing = false)}
  />
{/if}
