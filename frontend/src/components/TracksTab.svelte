<script lang="ts">
  // Audio and subtitle choices: what the profile's rules picked, and per-job overrides
  // (audio tracks and order, subtitle use / language / the profile's flags). Every change
  // replans on the server; the output columns always show what the rules now produce.
  import { LANGUAGES } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import type { AudioTrack, JobDetail, Overrides, SubTrack, TrackOverride } from '../lib/types'
  import Icon from './Icon.svelte'

  let {
    job,
    save,
    editable,
  }: { job: JobDetail; save: (o: Overrides) => Promise<void>; editable: boolean } = $props()

  const overrides = $derived(job.spec.overrides)
  const plan = $derived(job.plan)
  const tracks = $derived(job.tracks)
  const flags = $derived(app.profiles.find(p => p.id === job.profile)?.track_properties.filter(t => t.kind === 'sub') ?? [])

  function copy(): Overrides {
    return structuredClone($state.snapshot(overrides)) as Overrides
  }

  // --- audio ---
  const plannedAudio = $derived(new Map((plan?.audio ?? []).map((a, i) => [a.source.id, { pos: i, a }])))
  const audioRows = $derived.by(() => {
    const all = tracks?.audio ?? []
    const order = overrides.audio_track_ids ?? (plan?.audio ?? []).map(a => a.source.id)
    const byId = new Map(all.map(t => [t.id, t]))
    return [...order.filter(i => byId.has(i)).map(i => byId.get(i)!), ...all.filter(t => !order.includes(t.id))]
  })

  function audioIds(rows: AudioTrack[], checked: (t: AudioTrack) => boolean): number[] {
    return rows.filter(checked).map(t => t.id)
  }

  function toggleAudio(t: AudioTrack, on: boolean) {
    const o = copy()
    o.audio_track_ids = audioIds(audioRows, x => (x.id === t.id ? on : plannedAudio.has(x.id)))
    save(o)
  }

  function moveAudio(t: AudioTrack, step: number) {
    const rows = [...audioRows]
    const i = rows.indexOf(t)
    const j = i + step
    if (j < 0 || j >= rows.length) return
    ;[rows[i], rows[j]] = [rows[j], rows[i]]
    const o = copy()
    o.audio_track_ids = audioIds(rows, x => plannedAudio.has(x.id))
    save(o)
  }

  function automaticAudio() {
    const o = copy()
    o.audio_track_ids = null
    save(o)
  }

  // --- subtitles ---
  const plannedSubs = $derived(
    new Map((plan?.subs ?? []).map((s, i) => [s.source.external_path ? `ext:${basename(s.source.external_path)}` : `id:${s.source.id}`, { pos: i, s }])),
  )
  const subRows = $derived(
    [...(tracks?.subs ?? [])].sort(
      (a, b) => (plannedSubs.get(a.key)?.pos ?? 999) - (plannedSubs.get(b.key)?.pos ?? 999),
    ),
  )

  function basename(p: string) {
    return p.split(/[\\/]/).pop() ?? p
  }

  function editTrack(key: string, change: (ov: TrackOverride) => void) {
    const o = copy()
    const ov = o.tracks[key] ?? { exclude: null, language: null, title: null, flags: {} }
    change(ov)
    if (ov.exclude === null && ov.language === null && ov.title === null && !Object.keys(ov.flags).length) delete o.tracks[key]
    else o.tracks[key] = ov
    save(o)
  }

  const subOverride = (t: SubTrack) => overrides.tracks[t.key]
  const subLanguage = (t: SubTrack) => subOverride(t)?.language ?? t.language
  const flagValue = (t: SubTrack, key: string) => subOverride(t)?.flags[key] ?? t.detected[key] ?? false
  const flagPinned = (t: SubTrack, key: string) => key in (subOverride(t)?.flags ?? {})

  function setFlag(t: SubTrack, key: string, on: boolean) {
    editTrack(t.key, ov => {
      if (on === (t.detected[key] ?? false)) delete ov.flags[key]
      else ov.flags[key] = on
    })
  }

  function setLanguage(t: SubTrack, tag: string) {
    editTrack(t.key, ov => (ov.language = !tag || tag === t.language ? null : tag))
  }

  function setLanguageOriginal(tag: string) {
    const o = copy()
    o.original_language = tag || null
    save(o)
  }

  function reset() {
    save({ original_language: overrides.original_language, audio_track_ids: null, tracks: {}, order: null })
  }

  function audioLabel(t: AudioTrack) {
    return `#${t.id} ${t.format_name || t.codec}${t.atmos ? ' Atmos' : t.dtsx ? ' DTS:X' : ''} ${t.layout}`
  }
</script>

{#if !tracks || !plan}
  <div class="p-6 text-muted">{job.status === 'probing' ? 'Probing the source…' : 'No tracks: the source could not be read.'}</div>
{:else}
  <fieldset disabled={!editable} class="space-y-6">
    <div class="flex flex-wrap items-center gap-3">
      <label class="flex items-center gap-2 text-sm text-muted">
        Original language
        <input
          class="field w-40"
          list="languages-tracks"
          value={overrides.original_language ?? ''}
          onchange={e => setLanguageOriginal((e.target as HTMLInputElement).value.trim())}
        />
      </label>
      <datalist id="languages-tracks">
        {#each LANGUAGES as [tag, name] (tag)}<option value={tag}>{name}</option>{/each}
      </datalist>
      <button class="btn ml-auto" onclick={reset}><Icon name="refresh" />Reset overrides</button>
    </div>

    <section>
      <div class="mb-2 flex items-center gap-2">
        <Icon name="audio" class="text-accent" /><span class="font-medium">Audio</span>
        <button class="btn-ghost ml-auto text-xs" onclick={automaticAudio} disabled={overrides.audio_track_ids === null}>
          <Icon name="wand" size={14} />Automatic
        </button>
      </div>
      <table class="w-full text-sm">
        <thead class="text-left text-xs text-muted uppercase">
          <tr><th class="w-10"></th><th>Source</th><th>Lang</th><th>Title</th><th>Output</th><th class="w-16"></th></tr>
        </thead>
        <tbody>
          {#each audioRows as t (t.id)}
            {@const out = plannedAudio.get(t.id)}
            <tr class="border-t border-line/60 {out ? '' : 'text-muted'}">
              <td class="py-1.5"><input type="checkbox" checked={!!out} onchange={e => toggleAudio(t, (e.target as HTMLInputElement).checked)} /></td>
              <td>{audioLabel(t)}</td>
              <td>{t.language}</td>
              <td class="max-w-48 truncate" title={t.title}>{t.title}</td>
              <td>
                {#if out}
                  {out.pos + 1}. {out.a.title}
                  <span class="text-xs text-muted">[{out.a.action}{out.a.bitrate_kbps ? ` ${out.a.bitrate_kbps}k` : ''}{out.a.default ? ', default' : ''}]</span>
                {:else}—{/if}
              </td>
              <td class="text-right">
                <button class="btn-ghost px-1" onclick={() => moveAudio(t, -1)} aria-label="Up"><Icon name="up" size={14} /></button>
                <button class="btn-ghost px-1" onclick={() => moveAudio(t, 1)} aria-label="Down"><Icon name="down" size={14} /></button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>

    <section>
      <div class="mb-2 flex items-center gap-2"><Icon name="sub" class="text-accent" /><span class="font-medium">Subtitles</span></div>
      <table class="w-full text-sm">
        <thead class="text-left text-xs text-muted uppercase">
          <tr>
            <th class="w-10"></th><th>Source</th><th>Format</th><th>Lang</th>
            {#each flags as f (f.key)}<th title={f.help}>{f.label}</th>{/each}
            <th>Output</th>
          </tr>
        </thead>
        <tbody>
          {#each subRows as t (t.key)}
            {@const out = plannedSubs.get(t.key)}
            {@const ov = subOverride(t)}
            <tr class="border-t border-line/60 {out ? '' : 'text-muted'}">
              <td class="py-1.5">
                <input
                  type="checkbox"
                  checked={!ov?.exclude}
                  onchange={e => editTrack(t.key, o => (o.exclude = (e.target as HTMLInputElement).checked ? null : true))}
                />
              </td>
              <td class="max-w-56 truncate" title={t.external_path ?? t.title}>
                {t.external_path ? basename(t.external_path) : `#${t.id}${t.title ? ` · ${t.title}` : ''}`}
              </td>
              <td>{t.format}</td>
              <td>
                <input
                  class="field w-24 py-0.5 {ov?.language ? 'border-warn/60' : ''}"
                  list="languages-tracks"
                  value={subLanguage(t)}
                  onchange={e => setLanguage(t, (e.target as HTMLInputElement).value.trim())}
                />
              </td>
              {#each flags as f (f.key)}
                <td>
                  <input
                    type="checkbox"
                    class={flagPinned(t, f.key) ? 'outline-2 outline-warn' : ''}
                    title={flagPinned(t, f.key) ? 'Set by override' : 'As detected'}
                    checked={flagValue(t, f.key)}
                    onchange={e => setFlag(t, f.key, (e.target as HTMLInputElement).checked)}
                  />
                </td>
              {/each}
              <td>
                {#if out}
                  {out.pos + 1}. {out.s.title}
                  <span class="text-xs text-muted">
                    {[out.s.default && 'default', out.s.forced && 'forced', out.s.hearing_impaired && 'SDH'].filter(Boolean).join(', ')}
                  </span>
                {:else}—{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>

    <section class="text-sm text-muted">
      <Icon name="chapters" class="inline text-accent" />
      Chapters: {plan.chapters_path ? basename(plan.chapters_path) : tracks.has_chapters ? 'from the source' : 'none'}
    </section>
  </fieldset>
{/if}
