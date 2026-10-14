<script lang="ts">
  // The full track editor, for profiles that follow it (track_editor, e.g. manual): the audio or
  // the subtitle tracks (one kind per tab) in output order. Drag a track by its handle (or use
  // the arrows) to reorder, untick it to leave it out, edit its title, language and flags, and
  // copy or encode each audio track. Every change saves and replans; each track shows its source
  // at a glance and what will be written.
  // Files can be added to the job here and removed again, and an audio track can be used more
  // than once ("Add a track from…": a copy with its own encode, title and flags).
  import type { InputChanges } from '../lib/api'
  import { emptyOverride, isEmpty, LANGUAGES } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import type { AudioAction, AudioEncodeInfo, AudioTrack, EncodeOptionInfo, JobDetail, Overrides, PlannedAudio, SubTrack, TrackOverride } from '../lib/types'
  import FileBrowser from './FileBrowser.svelte'
  import Icon from './Icon.svelte'

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
  const setTitle = (t: Track, v: string) => editTrack(t, ov => (ov.title = v === t.title ? null : v))
  const setLanguage = (t: Track, v: string) => editTrack(t, ov => (ov.language = !v || v === t.language ? null : v))

  const flagOn = (t: Track, key: string) => ovOf(t)?.flags[key] ?? t.detected[key] ?? false
  const flagSet = (t: Track, key: string) => key in (ovOf(t)?.flags ?? {})
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
    return e.layouts.filter(l => channels(l) <= channels(t.layout) || (e.id === 'ddp' && t.layout === '5.0' && l === '5.1'))
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
    })
  const changedOptions = (t: AudioTrack, e: AudioEncodeInfo) =>
    e.options.filter(o => ovOf(t)?.options?.[o.key] !== undefined).length
  const setLayout = (t: AudioTrack, v: string) => editTrack(t, ov => (ov.layout = v || null))
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

  function setOriginal(tag: string) {
    const o = draft()
    o.original_language = tag || null
    save(o)
  }

  const title = $derived(kind === 'audio' ? 'Audio' : 'Subtitles')
</script>

{#snippet trackRow(t: Track, i: number, count: number)}
  {@const ov = ovOf(t)}
  {@const off = excluded(t)}
  {@const pos = outPos(t)}
  {@const copy = isAudio(t) && t.copy ? t : null}
  {#if dropAt === i}<div class="-my-1 h-0.5 rounded bg-accent"></div>{/if}
  <div
    data-row
    role="listitem"
    class="rounded-md border border-line bg-panel {drag === t.key ? 'opacity-40' : ''}"
    ondragover={e => dragOver(e, i)}
    ondrop={drop}
  >
    <div class="flex items-center gap-2 px-2 py-1.5">
      <span
        class="rounded p-0.5 text-muted {editable ? 'cursor-grab hover:bg-raised hover:text-text' : 'opacity-40'}"
        draggable={editable}
        ondragstart={e => dragStart(e, t)}
        ondragend={() => (drag = dropAt = null)}
        title="Drag to reorder"
        role="button"
        tabindex="-1"><Icon name="grip" /></span
      >
      <input type="checkbox" checked={!off} title="In the output" onchange={e => setIncluded(t, e.currentTarget.checked)} />
      <span class="w-5 text-center text-xs {off ? 'text-muted' : 'text-accent'}">{pos === undefined ? '–' : pos + 1}</span>
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm {off ? 'text-muted line-through' : ''}" title={t.title}>
          <span class="font-medium">{sourceLabel(t)}</span>
          <span class="text-muted">· {t.language}{t.title ? ` · ${t.title}` : ''}</span>
        </div>
        {#if details(t).length}
          <div class="flex flex-wrap gap-x-3 text-xs text-muted tabular-nums" data-details>
            {#each details(t) as d (d)}<span>{d}</span>{/each}
          </div>
        {/if}
      </div>
      {#if copy}
        <span class="rounded bg-accent/15 px-1.5 text-xs text-accent" title="Another output track from {sourceLabel(t)}">copy {copy.copy}</span>
        <button class="btn-ghost px-1 hover:text-bad" onclick={() => removeCopy(copy)} title="Remove this copy">
          <Icon name="x" size={14} />
        </button>
      {:else if t.external_path}
        {@const path = t.external_path}
        <span class="rounded bg-raised px-1.5 text-xs text-muted" title={path}>added</span>
        <button class="btn-ghost px-1 hover:text-bad" onclick={() => removeFile(path)} title="Remove this file from the job">
          <Icon name="x" size={14} />
        </button>
      {/if}
      <button class="btn-ghost px-1" disabled={i === 0} onclick={() => move(t.key, i - 1)} aria-label="Move up">
        <Icon name="up" size={14} />
      </button>
      <button class="btn-ghost px-1" disabled={i === count - 1} onclick={() => move(t.key, i + 2)} aria-label="Move down">
        <Icon name="down" size={14} />
      </button>
    </div>
    {#if !off}
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line/60 px-3 py-2 text-sm">
        <input
          class="field w-64 {ov?.title !== null && ov?.title !== undefined ? 'border-warn/60' : ''}"
          placeholder="No title"
          value={ov?.title ?? t.title}
          aria-label="Title"
          onchange={e => setTitle(t, e.currentTarget.value)}
        />
        <input
          class="field w-24 {ov?.language ? 'border-warn/60' : ''}"
          list="track-languages"
          value={ov?.language ?? t.language}
          aria-label="Language"
          onchange={e => setLanguage(t, e.currentTarget.value.trim())}
        />
        <div class="flex flex-wrap gap-1" role="group" aria-label="Track flags">
          {#each properties as f (f.key)}
            {@const on = flagOn(t, f.key)}
            <button
              class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs {on
                ? 'border-accent bg-accent/15 text-accent'
                : 'border-line text-muted hover:text-text'} {flagSet(t, f.key) ? 'underline decoration-dotted' : ''}"
              aria-pressed={on}
              title="{f.help}{flagSet(t, f.key) ? ' (set by you)' : ''}"
              onclick={() => toggleFlag(t, f.key)}
              >{#if on}<Icon name="check" size={12} />{/if}{f.label}</button
            >
          {/each}
        </div>
      </div>
      {#if isAudio(t)}
        {@const action = actionOf(t)}
        {@const planned = plannedAudio.get(t.key)?.a}
        {@const enc = encodeOf(action)}
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line/60 px-3 py-2 text-sm">
          <select class="field" value={action} aria-label="Copy or encode" onchange={e => setAction(t, e.currentTarget.value as AudioAction)}>
            <option value="copy">Copy</option>
            {#each offered(t, action) as e (e.id)}
              <option value={e.id} disabled={!!e.missing.length && action !== e.id}>Encode: {e.label}{needs(e)}</option>
            {/each}
          </select>
          {#if enc && enc.layouts.length > 1}
            <select class="field" value={ov?.layout ?? ''} aria-label="Channels" onchange={e => setLayout(t, e.currentTarget.value)}>
              <option value="">Channels: auto{planned && !ov?.layout ? ` (${planned.out_layout})` : ''}</option>
              {#each layoutChoices(t, enc) as l (l)}<option value={l}>{l}</option>{/each}
            </select>
          {/if}
          {#if enc && enc.bitrates !== null}
            <label class="flex items-center gap-1.5 text-muted">
              {#if enc.bitrate_choices.length}
                <select class="field" value={ov?.bitrate_kbps ?? ''} aria-label="Bitrate" onchange={e => setBitrate(t, e.currentTarget.value)}>
                  <option value="">auto{planned?.bitrate_kbps && !ov?.bitrate_kbps ? ` (${planned.bitrate_kbps})` : ''}</option>
                  {#each enc.bitrate_choices as b (b)}<option value={b}>{b}</option>{/each}
                </select>
              {:else}
                <input
                  class="field w-24"
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
          {#if enc?.options.length}
            {@const changed = changedOptions(t, enc)}
            <button
              class="btn-ghost text-xs {openSettings[t.key] ? 'text-accent' : ''}"
              onclick={() => (openSettings[t.key] = !openSettings[t.key])}
              title="{enc.label} settings"
            >
              <Icon name="settings" size={14} />Settings{changed ? ` (${changed})` : ''}
            </button>
          {/if}
          {#if planned}<span class="text-xs text-muted">→ {audioOut(planned)}</span>{/if}
        </div>
        {#if enc?.options.length && openSettings[t.key]}
          <div class="grid gap-x-4 gap-y-2 border-t border-line/60 px-3 py-2 text-sm sm:grid-cols-[12rem_1fr]">
            {#each enc.options as o (o.key)}
              {@const value = ov?.options?.[o.key] ?? planned?.options?.[o.key] ?? o.default}
              <label class="text-muted" for="opt-{t.key}-{o.key}" title={o.help}>{o.label}</label>
              <div class="flex items-center gap-2">
                {#if o.choices.length}
                  <select id="opt-{t.key}-{o.key}" class="field" {value} onchange={e => setOption(t, o, e.currentTarget.value)}>
                    {#each o.choices as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
                  </select>
                {:else if o.range}
                  <input id="opt-{t.key}-{o.key}" class="field w-24" type="number" min={o.range[0]} max={o.range[1]}
                    {value} onchange={e => setOption(t, o, e.currentTarget.value)} />
                {:else}
                  <input id="opt-{t.key}-{o.key}" class="field min-w-0 flex-1 font-mono text-xs" {value} placeholder={o.help}
                    onchange={e => setOption(t, o, e.currentTarget.value)} />
                {/if}
                {#if o.help && (o.choices.length || o.range)}<span class="text-xs text-muted">{o.help}</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    {/if}
  </div>
  {#if i === count - 1 && dropAt === count}<div class="-my-1 h-0.5 rounded bg-accent"></div>{/if}
{/snippet}

{#if !tracks || !plan}
  <div class="p-6 text-muted">{job.status === 'probing' ? 'Probing the source…' : 'No tracks: the source could not be read.'}</div>
{:else}
  <fieldset disabled={!editable} class="max-w-5xl space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <label class="flex items-center gap-2 text-sm text-muted">
        Original language
        <input
          class="field w-40"
          list="track-languages"
          value={overrides.original_language ?? ''}
          onchange={e => setOriginal(e.currentTarget.value.trim())}
        />
      </label>
      <datalist id="track-languages">
        {#each LANGUAGES as [tag, name] (tag)}<option value={tag}>{name}</option>{/each}
      </datalist>
      <div class="ml-auto flex flex-wrap gap-2">
        {#if kind === 'audio'}
          <select
            class="field"
            value=""
            aria-label="Add a track from"
            title="Use a track again: another output track with its own encode, title and flags"
            onchange={e => {
              const base = audioRows.find(t => t.key === e.currentTarget.value)
              e.currentTarget.value = ''
              if (base) addCopy(base)
            }}
          >
            <option value="">+ Add a track from…</option>
            {#each audioRows.filter(t => !t.copy) as t (t.key)}
              <option value={t.key}>{sourceLabel(t)} · {t.language}{t.title ? ` · ${t.title}` : ''}</option>
            {/each}
          </select>
        {/if}
        <button class="btn" onclick={() => (browsing = true)} title="Add {kind === 'audio' ? 'audio' : 'subtitle'} files to this job">
          <Icon name="new" />Add files…
        </button>
        <button class="btn" onclick={reset} title="Back to the profile's choices for these tracks"><Icon name="refresh" />Reset</button>
      </div>
    </div>

    <section>
      <div class="mb-2 flex items-center gap-2">
        <Icon name={kind === 'audio' ? 'audio' : 'sub'} class="text-accent" /><span class="font-medium">{title}</span>
        <span class="text-xs text-muted">{rows.filter(t => !excluded(t)).length} of {rows.length} in the output</span>
        <span class="ml-auto text-xs text-muted">Drag a track by its handle to reorder; every change saves.</span>
      </div>
      {#if rows.length}
        <div class="space-y-2" role="list">
          {#each rows as t, i (t.key)}
            {@render trackRow(t, i, rows.length)}
          {/each}
        </div>
      {:else}
        <p class="text-sm text-muted">None in the source or added.</p>
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
