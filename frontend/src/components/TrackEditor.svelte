<script lang="ts">
  // The full track editor, for profiles that follow it (track_editor, e.g. manual): every audio
  // and subtitle track in output order. Drag a track by its handle (or use the arrows) to reorder,
  // untick it to leave it out, edit its title, language and flags, and copy or encode each audio
  // track. Every change saves and replans; each track shows what will be written.
  // Files can be added to the job here (subtitles, audio, chapters) and removed again.
  import type { InputChanges } from '../lib/api'
  import { emptyOverride, isEmpty, LANGUAGES } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import type { AudioAction, AudioEncodeInfo, AudioTrack, EncodeOptionInfo, JobDetail, Overrides, PlannedAudio, SubTrack, TrackOverride } from '../lib/types'
  import FileBrowser from './FileBrowser.svelte'
  import Icon from './Icon.svelte'

  let {
    job,
    save,
    saveInputs,
    editable,
  }: {
    job: JobDetail
    save: (o: Overrides) => Promise<void>
    saveInputs: (inputs: InputChanges) => Promise<void>
    editable: boolean
  } = $props()

  // --- the job's files ---
  const SUB_EXTENSIONS = ['.srt', '.ass', '.ssa', '.sup', '.idx']
  const AUDIO_EXTENSIONS = ['.ac3', '.eac3', '.ec3', '.dts', '.dtshd', '.thd', '.truehd', '.mlp', '.flac', '.wav', '.w64',
    '.m4a', '.aac', '.mka', '.opus', '.ogg']
  const extOf = (p: string) => (p.match(/\.[^.\\/]+$/)?.[0] ?? '').toLowerCase()
  const CHAPTER_EXTENSIONS = ['.xml', '.txt']
  let browsing = $state<'files' | 'chapters' | null>(null)
  const sourceDir = $derived(job.spec.inputs.source.replace(/[\\/][^\\/]*$/, ''))
  const sameFile = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

  // Picked files go to subtitles or audio by extension; a folder goes to both (each takes its kind).
  function addFiles(paths: string[]) {
    const { subtitles, audio } = job.spec.inputs
    const isSub = (p: string) => SUB_EXTENSIONS.includes(extOf(p))
    const isAudioFile = (p: string) => AUDIO_EXTENSIONS.includes(extOf(p))
    const newSubs = paths.filter(p => !isAudioFile(p) && !subtitles.some(s => sameFile(s, p)))
    const newAudio = paths.filter(p => !isSub(p) && !audio.some(s => sameFile(s, p)))
    const changes: InputChanges = {}
    if (newSubs.length) changes.subtitles = [...subtitles, ...newSubs]
    if (newAudio.length) changes.audio = [...audio, ...newAudio]
    if (Object.keys(changes).length) saveInputs(changes)
  }

  function removeFile(path: string, kind: Kind) {
    const keep = (list: string[]) => list.filter(s => !sameFile(s, path))
    saveInputs(kind === 'audio' ? { audio: keep(job.spec.inputs.audio) } : { subtitles: keep(job.spec.inputs.subtitles) })
  }

  type Kind = 'audio' | 'sub'
  type Track = AudioTrack | SubTrack

  const overrides = $derived(job.spec.overrides)
  const plan = $derived(job.plan)
  const tracks = $derived(job.tracks)
  const properties = $derived(app.profiles.find(p => p.id === job.profile)?.track_properties ?? [])

  const isAudio = (t: Track): t is AudioTrack => 'codec' in t
  const basename = (p: string) => p.split(/[\\/]/).pop() ?? p

  // Output order: the saved order (track keys) first, the rest in source order. A list of
  // audio track ids (set from the simpler tracks tab) leads for audio when it's there.
  function inOrder<T extends Track>(list: T[]): T[] {
    const ids = overrides.audio_track_ids
    const order = overrides.order ?? []
    const rank = (t: T) => {
      const i = ids && isAudio(t) && !t.external_path ? ids.indexOf(t.id) : order.indexOf(t.key)
      return i < 0 ? 10_000 + list.indexOf(t) : i
    }
    return [...list].sort((a, b) => rank(a) - rank(b))
  }

  const audioRows = $derived(inOrder(tracks?.audio ?? []))
  const subRows = $derived(inOrder(tracks?.subs ?? []))
  // Planned audio by track key: ids repeat across added files.
  const audioKey = (t: Pick<AudioTrack, 'id' | 'index' | 'external_path'>) =>
    t.external_path ? `ext:${basename(t.external_path)}${t.index ? `#${t.index}` : ''}` : `id:${t.id}`
  const plannedAudio = $derived(new Map((plan?.audio ?? []).map((a, i) => [audioKey(a.source), { pos: i, a }])))
  const plannedSubs = $derived(
    new Map(
      (plan?.subs ?? []).map((s, i) => [s.source.external_path ? `ext:${basename(s.source.external_path)}` : `id:${s.source.id}`, i]),
    ),
  )

  const ovOf = (t: Track): TrackOverride | undefined => overrides.tracks[t.key]
  const excluded = (t: Track) =>
    !!ovOf(t)?.exclude ||
    (!!overrides.audio_track_ids && isAudio(t) && !t.external_path && !overrides.audio_track_ids.includes(t.id))
  const outPos = (t: Track) => (isAudio(t) ? plannedAudio.get(t.key)?.pos : plannedSubs.get(t.key))

  // A copy of the overrides to change, in the editor's terms: an audio id list becomes
  // order + exclusions, so the two ways of choosing tracks never disagree.
  function draft(): Overrides {
    const o = structuredClone($state.snapshot(overrides)) as Overrides
    if (o.audio_track_ids) {
      for (const t of audioRows)
        if (!t.external_path && !o.audio_track_ids.includes(t.id)) edit(o, t.key, ov => (ov.exclude = true))
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

  function sourceLabel(t: Track): string {
    if (isAudio(t)) {
      const fmt = t.format_name || CODEC[t.codec] || t.codec
      const where = t.external_path ? `${basename(t.external_path)}${t.index ? ` #${t.index + 1}` : ''}:` : `#${t.id}`
      return `${where} ${fmt}${t.atmos ? ' Atmos' : t.dtsx ? ' DTS:X' : ''} ${t.layout}`
    }
    return t.external_path ? `${basename(t.external_path)} (${t.format})` : `#${t.id} ${t.format.toUpperCase()}`
  }

  // --- reordering: drag the handle, or the arrows ---
  let drag = $state<{ kind: Kind; key: string } | null>(null)
  let dropAt = $state<{ kind: Kind; index: number } | null>(null) // insert before this row

  function move(kind: Kind, key: string, to: number) {
    const rows = [...(kind === 'audio' ? audioRows : subRows)] as Track[]
    const from = rows.findIndex(t => t.key === key)
    const target = to > from ? to - 1 : to
    if (from < 0 || target === from || target < 0 || target >= rows.length) return
    const [t] = rows.splice(from, 1)
    rows.splice(target, 0, t)
    const o = draft()
    if (kind === 'audio') commit(o, rows, subRows)
    else commit(o, audioRows, rows)
  }

  function dragStart(e: DragEvent, kind: Kind, t: Track) {
    drag = { kind, key: t.key }
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', t.key)
      const row = (e.currentTarget as HTMLElement).closest('[data-row]')
      if (row) e.dataTransfer.setDragImage(row, 16, 16)
    }
  }

  function dragOver(e: DragEvent, kind: Kind, i: number) {
    if (drag?.kind !== kind) return
    e.preventDefault()
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    dropAt = { kind, index: e.clientY < r.top + r.height / 2 ? i : i + 1 }
  }

  function drop(e: DragEvent, kind: Kind) {
    e.preventDefault()
    if (drag?.kind === kind && dropAt?.kind === kind) move(kind, drag.key, dropAt.index)
    drag = dropAt = null
  }

  function reset() {
    save({ original_language: overrides.original_language, audio_track_ids: null, tracks: {}, order: null })
  }

  function setOriginal(tag: string) {
    const o = draft()
    o.original_language = tag || null
    save(o)
  }
</script>

{#snippet trackRow(kind: Kind, t: Track, i: number, count: number)}
  {@const ov = ovOf(t)}
  {@const off = excluded(t)}
  {@const pos = outPos(t)}
  {#if dropAt?.kind === kind && dropAt.index === i}<div class="-my-1 h-0.5 rounded bg-accent"></div>{/if}
  <div
    data-row
    role="listitem"
    class="rounded-md border border-line bg-panel {drag?.key === t.key ? 'opacity-40' : ''}"
    ondragover={e => dragOver(e, kind, i)}
    ondrop={e => drop(e, kind)}
  >
    <div class="flex items-center gap-2 px-2 py-1.5">
      <span
        class="rounded p-0.5 text-muted {editable ? 'cursor-grab hover:bg-raised hover:text-text' : 'opacity-40'}"
        draggable={editable}
        ondragstart={e => dragStart(e, kind, t)}
        ondragend={() => (drag = dropAt = null)}
        title="Drag to reorder"
        role="button"
        tabindex="-1"><Icon name="grip" /></span
      >
      <input type="checkbox" checked={!off} title="In the output" onchange={e => setIncluded(t, e.currentTarget.checked)} />
      <span class="w-5 text-center text-xs {off ? 'text-muted' : 'text-accent'}">{pos === undefined ? '–' : pos + 1}</span>
      <span class="min-w-0 flex-1 truncate text-sm {off ? 'text-muted line-through' : ''}" title={t.title}>
        {sourceLabel(t)} <span class="text-muted">· {t.language}{t.title ? ` · ${t.title}` : ''}</span>
      </span>
      {#if t.external_path}
        {@const path = t.external_path}
        <span class="rounded bg-raised px-1.5 text-xs text-muted" title={path}>added</span>
        <button class="btn-ghost px-1 hover:text-bad" onclick={() => removeFile(path, kind)} title="Remove this file from the job">
          <Icon name="x" size={14} />
        </button>
      {/if}
      <button class="btn-ghost px-1" disabled={i === 0} onclick={() => move(kind, t.key, i - 1)} aria-label="Move up">
        <Icon name="up" size={14} />
      </button>
      <button class="btn-ghost px-1" disabled={i === count - 1} onclick={() => move(kind, t.key, i + 2)} aria-label="Move down">
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
        <div class="flex flex-wrap gap-1">
          {#each properties.filter(p => p.kind === kind) as f (f.key)}
            {@const on = flagOn(t, f.key)}
            <button
              class="rounded-full border px-2 py-0.5 text-xs {on
                ? 'border-accent bg-accent/15 text-accent'
                : 'border-line text-muted hover:text-text'} {flagSet(t, f.key) ? 'underline decoration-dotted' : ''}"
              aria-pressed={on}
              title="{f.help}{flagSet(t, f.key) ? ' (set by you)' : ''}"
              onclick={() => toggleFlag(t, f.key)}>{f.label}</button
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
                  class="field w-20 text-right"
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
                  <input id="opt-{t.key}-{o.key}" class="field w-24 text-right" type="number" min={o.range[0]} max={o.range[1]}
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
  {#if i === count - 1 && dropAt?.kind === kind && dropAt.index === count}<div class="-my-1 h-0.5 rounded bg-accent"></div>{/if}
{/snippet}

{#if !tracks || !plan}
  <div class="p-6 text-muted">{job.status === 'probing' ? 'Probing the source…' : 'No tracks: the source could not be read.'}</div>
{:else}
  <fieldset disabled={!editable} class="max-w-5xl space-y-6">
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
      <span class="text-xs text-muted">Drag a track by its handle to reorder; every change saves.</span>
      <button class="btn ml-auto" onclick={() => (browsing = 'files')} title="Add subtitle or audio files to this job">
        <Icon name="new" />Add files…
      </button>
      <button class="btn" onclick={reset}><Icon name="refresh" />Reset tracks</button>
    </div>

    {#each [{ kind: 'audio' as Kind, rows: audioRows, icon: 'audio' as const, title: 'Audio' }, { kind: 'sub' as Kind, rows: subRows, icon: 'sub' as const, title: 'Subtitles' }] as section (section.kind)}
      <section>
        <div class="mb-2 flex items-center gap-2">
          <Icon name={section.icon} class="text-accent" /><span class="font-medium">{section.title}</span>
          <span class="text-xs text-muted">
            {section.rows.filter(t => !excluded(t)).length} of {section.rows.length} in the output
          </span>
        </div>
        {#if section.rows.length}
          <div class="space-y-2" role="list">
            {#each section.rows as t, i (t.key)}
              {@render trackRow(section.kind, t, i, section.rows.length)}
            {/each}
          </div>
        {:else}
          <p class="text-sm text-muted">None in the source or added.</p>
        {/if}
      </section>
    {/each}

    <section class="flex flex-wrap items-center gap-2 text-sm text-muted">
      <Icon name="chapters" class="text-accent" />
      Chapters: {job.spec.inputs.chapters
        ? basename(job.spec.inputs.chapters)
        : plan.chapters_path
          ? `${basename(plan.chapters_path)} (AutoQPF)`
          : tracks.has_chapters
            ? 'from the source'
            : 'none'}
      <button class="btn-ghost text-xs" onclick={() => (browsing = 'chapters')}>
        {job.spec.inputs.chapters ? 'Change…' : 'Use a file…'}
      </button>
      {#if job.spec.inputs.chapters}
        <button class="btn-ghost text-xs hover:text-bad" onclick={() => saveInputs({ chapters: null })}>Remove</button>
      {/if}
    </section>
  </fieldset>
{/if}

{#if browsing}
  <FileBrowser
    title={browsing === 'files' ? 'Add subtitle or audio files' : 'Chapters file'}
    extensions={browsing === 'files' ? [...SUB_EXTENSIONS, ...AUDIO_EXTENSIONS] : CHAPTER_EXTENSIONS}
    start={sourceDir}
    onpick={paths => {
      if (browsing === 'files') addFiles(paths)
      else if (paths[0]) saveInputs({ chapters: paths[0] })
      browsing = null
    }}
    onclose={() => (browsing = null)}
  />
{/if}
