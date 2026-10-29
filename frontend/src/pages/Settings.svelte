<script lang="ts">
  // Settings: where each tool is (found or not, and its version), what the folder browser
  // may show, the profile new jobs start with, whether batch indexing waits for an encode's disk, where
  // notifications go (Apprise URLs), the actions run after a job or the queue ends, and which plugins load.
  // Each change saves at once and is used by
  // new jobs and runs; Reset goes back to the server's configuration defaults.
  import { onMount } from 'svelte'
  import FileBrowser from '../components/FileBrowser.svelte'
  import ConfigurationTransfer from '../components/ConfigurationTransfer.svelte'
  import PresetPackTransfer from '../components/PresetPackTransfer.svelte'
  import PluginManager from '../components/PluginManager.svelte'
  import AudioPresetMenu from '../components/AudioPresetMenu.svelte'
  import EncoderPresetMenu from '../components/EncoderPresetMenu.svelte'
  import TemplateSubsEditor from '../components/TemplateSubsEditor.svelte'
  import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
  import CheckIcon from '@lucide/svelte/icons/check'
  import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import PowerIcon from '@lucide/svelte/icons/power'
  import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
  import SendIcon from '@lucide/svelte/icons/send'
  import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
  import XIcon from '@lucide/svelte/icons/x'
  import { toast } from 'svelte-sonner'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { api } from '../lib/api'
  import { configDraft } from '../lib/configDraft'
  import { saves } from '../lib/saves'
  import { drops } from '../lib/dropPaths.svelte'
  import { PRIORITY_LABEL } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import type {
    ActionKind,
    ActionSetting,
    ConfigState,
    NotificationDestination,
    NotificationEvent,
    Priority,
    ToolCheck,
    ToolSetting,
    TemplateSubs,
    ToolStatus,
  } from '../lib/types'

  let config = $state<ConfigState | null>(null)
  let pluginRefresh = $state(0)
  let checks = $state<Record<string, ToolCheck>>({})
  let checking = $state<Record<string, boolean>>({})
  let error = $state('')
  let pending = $state(0)
  let saveError = $state('')
  $effect(() =>
    saves.subscribe((message) => {
      saveError = message
    }),
  )
  let newRoot = $state('')
  let browse = $state<
    { kind: 'tool'; tool: ToolSetting } | { kind: 'root' } | { kind: 'action'; index: number | 'draft' } | null
  >(null)

  async function checkAll() {
    const names = config?.tools.map((t) => t.name) ?? []
    checking = Object.fromEntries(names.map((n) => [n, true]))
    try {
      const all = await api.toolChecks()
      checks = Object.fromEntries(all.map((c) => [c.name, c]))
    } finally {
      checking = {}
    }
  }

  onMount(async () => {
    try {
      await saves.flush()
      config = await api.config()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      return
    }
    draft.events = defaultEvents()
    checkAll()
  })

  async function change(changes: Parameters<typeof api.saveConfig>[0]): Promise<boolean> {
    if (!config) return false
    const snapshot = structuredClone($state.snapshot(changes))
    config = configDraft(config, snapshot)
    pending++
    try {
      const reply = await saves.add(() => api.saveConfig(snapshot))
      if (--pending === 0) config = reply
      return true
    } catch (e) {
      if (--pending === 0) config = await api.config().catch(() => config)
      toast.error("Couldn't save the settings", { description: e instanceof Error ? e.message : String(e) })
      return false
    }
  }

  async function recoverSaves(discard = false) {
    try {
      if (discard) saves.discard()
      else await saves.retry()
      config = await api.config()
      error = ''
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }

  async function setParallelAudio(input: HTMLInputElement) {
    if (!config) return
    const { parallel_audio: now, parallel_audio_default: fallback } = config
    const n = Math.round(Number(input.value))
    if (input.value.trim() === '' || !Number.isFinite(n) || n < 0 || n > 8) {
      input.value = String(now)
      return
    }
    if (!(await change({ parallel_audio: n === fallback ? null : n }))) input.value = String(now)
  }

  async function setTool(t: ToolSetting, value: string) {
    const path = value.trim()
    if (!(await change({ tools: { [t.name]: path && path !== t.default ? path : null } }))) return
    app.loadEncoders()
    checking = { ...checking, [t.name]: true }
    try {
      const now = config!.tools.find((x) => x.name === t.name)!
      checks = { ...checks, [t.name]: await api.checkTool(t.name, now.path) }
    } finally {
      checking = { ...checking, [t.name]: false }
    }
  }

  async function setProfile(id: string) {
    if (await change({ profile: id === config?.profile_default ? null : id })) app.profiles = await api.profiles()
  }

  // Subtitle rules for new jobs whose template sets none: shown as changed at once, saved in order.
  let subsEdit = $state<{ value: TemplateSubs | null } | null>(null)
  let subsSent = 0
  const subsDefault = $derived(subsEdit ? subsEdit.value : (app.presets.subs_default ?? null))
  const defaultProfile = $derived(app.profiles.find((p) => p.id === config?.profile) ?? app.defaultProfile)
  const subFlags = $derived(defaultProfile?.track_properties.filter((f) => f.kind === 'sub') ?? [])
  async function setSubsDefault(value: TemplateSubs | null) {
    const sent = ++subsSent
    subsEdit = { value }
    try {
      app.presets = await saves.add(() => api.setSubsDefault(value))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      if (sent === subsSent) subsEdit = null // the last change: show what the server has
    }
  }

  function setRoots(roots: string[] | null) {
    change({ roots })
  }

  async function addRoot(path: string) {
    const p = path.trim()
    if (!p || !config) return
    const current = config.roots_custom ? config.roots : []
    if (await change({ roots: [...current.filter((r) => r.toLowerCase() !== p.toLowerCase()), p] })) newRoot = ''
  }

  // Where Browse opens: the tool's folder (or the plugin folder itself).
  function startFolder(t: ToolSetting): string {
    const found = checks[t.name]?.found ?? ''
    return t.folder ? found : found.replace(/[\\/][^\\/]*$/, '')
  }

  const LOOK: Record<ToolStatus, { icon: typeof CheckIcon; tone: string; text: string }> = {
    ok: { icon: CheckIcon, tone: 'text-success', text: 'found' },
    unknown: { icon: TriangleAlertIcon, tone: 'text-warning', text: 'found, no version' },
    missing: { icon: XIcon, tone: 'text-destructive', text: 'missing' },
    broken: { icon: XIcon, tone: 'text-destructive', text: "won't start" },
  }

  // --- notifications: Apprise URLs, each with the events it wants; the whole list is saved on each change ---
  let draft = $state<NotificationDestination>({ name: '', url: '', enabled: true, events: [] })
  let testing = $state<Record<string, boolean>>({})

  function defaultEvents(): NotificationEvent[] {
    return config?.notification_events.filter((e) => e.default).map((e) => e.id) ?? []
  }

  function setNotifications(list: NotificationDestination[]): Promise<boolean> {
    return change({ notifications: list })
  }

  function editNotification(i: number, changes: Partial<NotificationDestination>) {
    if (!config) return
    setNotifications(config.notifications.map((d, j) => (j === i ? { ...d, ...changes } : d)))
  }

  function toggleEvent(events: NotificationEvent[], id: NotificationEvent, on: boolean): NotificationEvent[] {
    return on ? [...events.filter((e) => e !== id), id] : events.filter((e) => e !== id)
  }

  async function addNotification() {
    if (!config || !draft.url.trim()) return
    const events = draft.events.length ? draft.events : defaultEvents()
    if (await setNotifications([...config.notifications, { ...draft, url: draft.url.trim(), events }]))
      draft = { name: '', url: '', enabled: true, events: defaultEvents() }
  }

  async function removeNotification(i: number) {
    if (!config) return
    const before = config.notifications
    if (await setNotifications(before.filter((_, j) => j !== i)))
      toast(`Removed ${before[i].name}`, { action: { label: 'Undo', onClick: () => setNotifications(before) } })
  }

  async function testNotification(key: string, url: string) {
    testing = { ...testing, [key]: true }
    try {
      await api.testNotification(url.trim())
      toast.success('Test notification sent')
    } catch (e) {
      toast.error("The test notification didn't go", { description: e instanceof Error ? e.message : String(e) })
    } finally {
      testing = { ...testing, [key]: false }
    }
  }

  // --- actions: what runs after a job ends or the queue finishes; the whole list is saved on each change ---
  const blankAction = (): ActionSetting => ({
    name: '',
    kind: 'move',
    target: '',
    enabled: true,
    events: ['job_done'],
    overwrite: false,
  })
  let actionDraft = $state<ActionSetting>(blankAction())

  const TARGET_HINT: Record<ActionKind, string> = {
    command: '"C:\\Tools\\scan.exe" --file "{output}"',
    move: 'D:\\Library\\{label}',
    copy: 'D:\\Library',
    webhook: 'https://example.com/hook',
  }
  const isFileKind = (k: ActionKind) => k === 'move' || k === 'copy'

  function setActions(list: ActionSetting[]): Promise<boolean> {
    return change({ actions: list })
  }

  // A move or copy runs after a job only: switching to one drops the queue's event.
  function withKind(a: ActionSetting, kind: ActionKind): ActionSetting {
    const events = isFileKind(kind) ? a.events.filter((e) => e !== 'queue_finished') : a.events
    return { ...a, kind, events: events.length ? events : ['job_done'] }
  }

  function editAction(i: number, changes: Partial<ActionSetting>) {
    if (!config) return
    setActions(config.actions.map((a, j) => (j === i ? { ...a, ...changes } : a)))
  }

  async function addAction() {
    if (!config || !actionDraft.target.trim()) return
    if (await setActions([...config.actions, { ...actionDraft, target: actionDraft.target.trim() }]))
      actionDraft = blankAction()
  }

  async function removeAction(i: number) {
    if (!config) return
    const before = config.actions
    if (await setActions(before.filter((_, j) => j !== i)))
      toast(`Removed ${before[i].name}`, { action: { label: 'Undo', onClick: () => setActions(before) } })
  }

  function moveActionUp(i: number) {
    if (!config || i === 0) return
    const list = [...config.actions]
    ;[list[i - 1], list[i]] = [list[i], list[i - 1]]
    setActions(list)
  }

  // --- shutting down from the page ---
  let confirmStop = $state(false)
  let stopping = $state(false)

  async function shutDown() {
    stopping = true
    try {
      await api.shutdown()
      app.stopped = true
      confirmStop = false
    } catch (e) {
      toast.error("Couldn't shut down", { description: e instanceof Error ? e.message : String(e) })
    } finally {
      stopping = false
    }
  }
</script>

<div class="@container/settings h-full overflow-auto p-6">
  <div class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-8 @min-[80rem]/settings:grid-cols-2">
    <header class="col-span-full flex flex-wrap items-center gap-3">
      <h1 class="text-xl font-semibold">Settings</h1>
      <span class="text-sm text-muted-foreground">Saved as you go; used by new jobs and runs.</span>
      {#if pending}<span class="text-sm text-muted-foreground">{saveError ? 'Unsaved changes' : 'Saving…'}</span>{/if}
    </header>

    {#if error}<div
        class="col-span-full rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
      >
        {error}
      </div>{/if}
    {#if saveError}
      <div role="alert" class="col-span-full space-y-2 text-sm text-destructive">
        <p>Changes are not saved: {saveError}</p>
        <Button onclick={() => recoverSaves()}>Retry saves</Button>
        <Button variant="outline" onclick={() => recoverSaves(true)}>Discard unsaved changes</Button>
      </div>
    {/if}
    {#each config?.restart ?? [] as note (note)}
      <div class="col-span-full rounded-md border border-warning/50 bg-warning/10 p-3 text-sm text-warning">{note}</div>
    {/each}

    <section class="col-span-full space-y-3">
      <h2 class="font-medium">Encoder presets</h2>
      <p class="text-sm text-muted-foreground">
        Create, edit, organize, import, and export presets without opening a job or template.
      </p>
      <div class="flex flex-wrap gap-2">
        {#if app.defaultProfile}
          <EncoderPresetMenu
            profile={app.defaultProfile.id}
            current={app.defaultProfile.defaults.encoder}
            apply={() => {}}
            manageOnly
          />
        {/if}
        <AudioPresetMenu
          current={{ action: 'copy', layout: null, bitrate_kbps: null, options: {} }}
          apply={() => {}}
          manageOnly
        />
      </div>
    </section>

    {#if !config}
      <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
    {:else}
      <ConfigurationTransfer
        disabled={pending > 0 || !!saveError}
        onimported={(value) => {
          config = value
          pluginRefresh++
          checks = {}
          checkAll()
        }}
      />
      <PresetPackTransfer disabled={pending > 0 || !!saveError} />
      <section class="col-span-full min-w-0 space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Tools</h2>
          <span class="text-xs text-muted-foreground">A bare name (e.g. ffmpeg) is looked up on PATH.</span>
          <Button variant="outline" class="ml-auto" onclick={checkAll} disabled={Object.values(checking).some(Boolean)}>
            <RefreshCwIcon />Check again
          </Button>
        </div>
        <div class="divide-y divide-border/60 rounded-xl border bg-card">
          {#each config.tools as t (t.name)}
            {@const c = checks[t.name]}
            {@const look = c ? LOOK[c.status] : null}
            <div class="grid grid-cols-[12rem_1fr] gap-x-4 gap-y-1.5 px-4 py-3">
              <div>
                <div class="text-sm font-medium">{t.label}</div>
                <div class="text-xs text-muted-foreground">{t.purpose}</div>
              </div>
              <div class="flex min-w-0 items-center gap-2">
                <Input
                  class="min-w-0 flex-1 font-mono text-xs {t.custom ? 'border-primary/60' : ''}"
                  value={t.custom ?? t.default}
                  placeholder={t.default || 'not set'}
                  aria-label="{t.label} path"
                  onchange={(e) => setTool(t, e.currentTarget.value)}
                />
                <Button variant="outline" onclick={() => (browse = { kind: 'tool', tool: t })}
                  ><FolderOpenIcon />Browse…</Button
                >
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!t.custom}
                  title="Back to the default: {t.default || '(none)'}"
                  onclick={() => setTool(t, '')}>Reset</Button
                >
              </div>
              <div></div>
              <div class="flex min-w-0 items-center gap-2 text-xs">
                {#if checking[t.name]}
                  <span class="text-muted-foreground">checking…</span>
                {:else if c && look}
                  <span class="flex shrink-0 items-center gap-1 {look.tone}"
                    ><look.icon class="size-3.5" />{look.text}</span
                  >
                  {#if c.version}<span class="truncate" title={c.version}>{c.version}</span>{/if}
                  {#if c.detail}<span class="truncate text-muted-foreground" title={c.detail}>{c.detail}</span>{/if}
                  {#if c.found && c.found !== t.path}<span class="truncate text-muted-foreground" title={c.found}
                      >· {c.found}</span
                    >{/if}
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <p class="text-xs text-muted-foreground">
          Dolby Encoding Engine and qaac's CoreAudioToolbox can't be shipped with VideoForge: install them and point at
          them here. DDP needs DeeZy + DEE (+ truehdd for Atmos); AAC needs ffmpeg + qaac.
        </p>
      </section>

      <section class="space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Folder browser</h2>
          <span class="text-xs text-muted-foreground">
            {config.roots_custom
              ? 'Only these folders (and what is under them) can be browsed.'
              : 'Every drive can be browsed.'}
          </span>
          <Button
            variant="ghost"
            size="sm"
            class="ml-auto"
            disabled={!config.roots_custom}
            onclick={() => setRoots(null)}
          >
            Reset to every drive
          </Button>
        </div>
        <div class="flex flex-wrap gap-2">
          {#each config.roots as r (r)}
            <span class="flex items-center gap-1 rounded-md bg-muted px-2 py-1 font-mono text-xs">
              {r}
              {#if config.roots_custom}
                <button
                  class="text-muted-foreground hover:text-destructive"
                  aria-label="Remove {r}"
                  onclick={() => setRoots(config!.roots.filter((x) => x !== r))}><XIcon class="size-3" /></button
                >
              {/if}
            </span>
          {/each}
        </div>
        <div class="flex gap-2">
          <Input
            class="w-96 font-mono text-xs"
            placeholder="D:\Media"
            bind:value={newRoot}
            onkeydown={(e) => e.key === 'Enter' && addRoot(newRoot)}
          />
          <Button variant="outline" onclick={() => addRoot(newRoot)} disabled={!newRoot.trim()}>Add folder</Button>
          <Button variant="outline" onclick={() => (browse = { kind: 'root' })}><FolderOpenIcon />Browse…</Button>
        </div>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Profile</h2>
        <label class="flex items-center gap-3 text-sm">
          <span class="text-muted-foreground">New jobs start with</span>
          <NativeSelect value={config.profile} onchange={(e) => setProfile(e.currentTarget.value)}>
            {#each config.profiles as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
          </NativeSelect>
          <span class="text-xs text-muted-foreground">Default: {config.profile_default}</span>
        </label>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Batch indexing</h2>
        <label class="flex items-start gap-3 text-sm">
          <Checkbox
            class="mt-0.5"
            checked={config.index_waits_for_disk}
            onCheckedChange={(v) => change({ index_waits_for_disk: v })}
          />
          <span>
            Wait while an encode reads the same disk
            <span class="block text-xs text-muted-foreground">
              A job in the index lane whose source is on the disk the running encode reads waits for it to finish; jobs
              on other disks go first. Index now on a job never waits.
            </span>
          </span>
        </label>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Audio encodes</h2>
        <label class="flex items-start gap-3 text-sm">
          <Input
            type="number"
            min="0"
            max="8"
            class="w-20"
            value={config.parallel_audio}
            onchange={(e) => setParallelAudio(e.currentTarget)}
          />
          <span>
            At once, beside the video encode
            <span class="block text-xs text-muted-foreground">
              A job's audio encodes start once its source is indexed and run while the video encodes; the mux waits for
              them. 0 encodes them one by one, before the video. Default: {config.parallel_audio_default}
            </span>
          </span>
        </label>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Process priority</h2>
        {#each [{ key: 'encoder_priority', label: 'Video encode', hint: 'the encoder (x264, x265, ffmpeg for VP8 / VP9, SvtAv1EncApp) and the vspipe feeding it' }, { key: 'tool_priority', label: 'Other tools', hint: 'audio encodes, the mux, indexing' }] as const as row (row.key)}
          <label class="flex items-center gap-3 text-sm">
            <span class="w-28 shrink-0 text-muted-foreground">{row.label}</span>
            <NativeSelect
              class="shrink-0"
              value={config[row.key]}
              onchange={(e) => {
                const v = e.currentTarget.value as Priority
                change({ [row.key]: v === config?.[`${row.key}_default`] ? null : v })
              }}
            >
              {#each config.priorities as p (p)}<option value={p}>{PRIORITY_LABEL[p]}</option>{/each}
            </NativeSelect>
            <span class="text-xs text-muted-foreground">
              {row.hint}. Default: {PRIORITY_LABEL[config[`${row.key}_default`]]}
            </span>
          </label>
        {/each}
        <p class="text-xs text-muted-foreground">
          For jobs started from now on; the Queue's toolbar changes the running one's. On Linux it's a nice value, and
          raising one back needs CAP_SYS_NICE.
        </p>
      </section>

      <section class="space-y-3">
        <h2 class="font-medium">Work folders</h2>
        <label class="flex items-start gap-3 text-sm">
          <Checkbox
            class="mt-0.5"
            checked={config.delete_work_dir}
            onCheckedChange={(v) => change({ delete_work_dir: v === config?.delete_work_dir_default ? null : v })}
          />
          <span>
            Delete a job's work folder once it's done
            <span class="block text-xs text-muted-foreground">
              The <code>&lt;source&gt;_tmp</code> folder next to the source (index, encodes, log) is deleted after the
              job succeeds; its job records and log are copied to {config.records_dir} first (the newest 100 kept). A job
              that fails or is cancelled keeps it, to resume from. Default:
              {config.delete_work_dir_default ? 'on' : 'off'}
            </span>
          </span>
        </label>
      </section>

      <section class="col-span-full min-w-0 space-y-3" aria-label="Default subtitles">
        <h2 class="font-medium">Default subtitles</h2>
        {#if !defaultProfile?.track_editor || defaultProfile.picks_tracks}
          <p class="text-xs text-muted-foreground">
            {defaultProfile?.name}'s rules choose its jobs' subtitles; these apply to other profiles' jobs.
          </p>
        {/if}
        <TemplateSubsEditor
          value={subsDefault}
          flags={subFlags}
          toggleLabel="Choose every new job's subtitles by rules"
          offNote="Off: new jobs keep every subtitle track, unless their template sets subtitle rules."
          appliedNote="New jobs get these rules unless their template sets its own; jobs already in the queue keep theirs."
          onchange={setSubsDefault}
        />
      </section>

      <!-- the events a notification or an action wants (skip: ones it can't have) -->
      {#snippet eventChoices(
        events: NotificationEvent[],
        onchange: (events: NotificationEvent[]) => void,
        skip: NotificationEvent[] = [],
      )}
        <div class="flex flex-wrap gap-x-4 gap-y-1.5">
          {#each config!.notification_events.filter((ev) => !skip.includes(ev.id)) as ev (ev.id)}
            <label class="flex items-center gap-1.5 text-xs">
              <Checkbox
                checked={events.includes(ev.id)}
                onCheckedChange={(v) => onchange(toggleEvent(events, ev.id, v))}
              />
              {ev.label}
            </label>
          {/each}
        </div>
      {/snippet}

      <section class="col-span-full min-w-0 space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Notifications</h2>
          <span class="text-xs text-muted-foreground">
            Tell Discord, Telegram, ntfy, Pushover, email or
            <a
              class="underline hover:text-foreground"
              href="https://github.com/caronc/apprise/wiki"
              target="_blank"
              rel="noreferrer">any service Apprise supports</a
            > when jobs end.
          </span>
        </div>
        <div class="divide-y divide-border/60 rounded-xl border bg-card">
          {#each config.notifications as d, i (i)}
            <div class="space-y-2 px-4 py-3 {d.enabled ? '' : 'opacity-60'}">
              <div class="flex min-w-0 items-center gap-2">
                <Checkbox
                  checked={d.enabled}
                  aria-label="Send to {d.name}"
                  title={d.enabled ? 'On' : 'Off: nothing is sent here'}
                  onCheckedChange={(v) => editNotification(i, { enabled: v })}
                />
                <Input
                  class="w-40 text-sm"
                  value={d.name}
                  aria-label="Name"
                  onchange={(e) => editNotification(i, { name: e.currentTarget.value })}
                />
                <Input
                  class="min-w-0 flex-1 font-mono text-xs"
                  value={d.url}
                  aria-label="{d.name} Apprise URL"
                  onchange={(e) => editNotification(i, { url: e.currentTarget.value })}
                />
                <Button variant="outline" disabled={testing[i]} onclick={() => testNotification(String(i), d.url)}>
                  <SendIcon />{testing[i] ? 'Sending…' : 'Test'}
                </Button>
                <Button variant="ghost" size="icon" aria-label="Remove {d.name}" onclick={() => removeNotification(i)}>
                  <XIcon />
                </Button>
              </div>
              {@render eventChoices(d.events, (events) => editNotification(i, { events }))}
            </div>
          {/each}
          <div class="space-y-2 px-4 py-3">
            <div class="flex min-w-0 items-center gap-2">
              <Input class="w-40 text-sm" placeholder="Name (optional)" bind:value={draft.name} />
              <Input
                class="min-w-0 flex-1 font-mono text-xs"
                placeholder="discord://webhook_id/webhook_token"
                bind:value={draft.url}
                onkeydown={(e) => e.key === 'Enter' && addNotification()}
              />
              <Button
                variant="outline"
                disabled={!draft.url.trim() || testing.draft}
                onclick={() => testNotification('draft', draft.url)}
              >
                <SendIcon />{testing.draft ? 'Sending…' : 'Test'}
              </Button>
              <Button onclick={addNotification} disabled={!draft.url.trim()}><PlusIcon />Add</Button>
            </div>
            {@render eventChoices(draft.events, (events) => (draft.events = events))}
          </div>
        </div>
      </section>

      <section class="col-span-full min-w-0 space-y-3">
        <div class="flex items-center gap-3">
          <h2 class="font-medium">Actions</h2>
          <span class="text-xs text-muted-foreground">
            After a job ends or the queue finishes: move or copy the output, run a command, or call a webhook. A job's
            actions run in this order; after a move, the ones below it see the new path.
          </span>
        </div>
        {#if !config.allow_commands}
          <p class="text-xs text-warning">
            Command actions are disabled by the current server configuration (the page has no login, so only if no one
            else can reach it).
          </p>
        {/if}
        {#snippet actionRow(a: ActionSetting, set: (changes: Partial<ActionSetting>) => void, index: number | 'draft')}
          <div class="flex min-w-0 items-center gap-2">
            {#if index !== 'draft'}
              <Checkbox
                checked={a.enabled}
                aria-label="Run {a.name}"
                title={a.enabled ? 'On' : 'Off: it never runs'}
                onCheckedChange={(v) => set({ enabled: v })}
              />
            {/if}
            <Input
              class="w-40 text-sm"
              value={a.name}
              placeholder="Name (optional)"
              aria-label="Name"
              onchange={(e) => set({ name: e.currentTarget.value })}
            />
            <NativeSelect
              value={a.kind}
              aria-label="Kind"
              onchange={(e) => set(withKind(a, e.currentTarget.value as ActionKind))}
            >
              {#each config!.action_kinds as k (k.id)}<option value={k.id}>{k.label}</option>{/each}
            </NativeSelect>
            <Input
              class="min-w-0 flex-1 font-mono text-xs"
              value={a.target}
              placeholder={TARGET_HINT[a.kind]}
              aria-label="{a.name || 'Action'} target"
              oninput={(e) => index === 'draft' && set({ target: e.currentTarget.value })}
              onchange={(e) => index !== 'draft' && set({ target: e.currentTarget.value })}
              onkeydown={(e) => index === 'draft' && e.key === 'Enter' && addAction()}
            />
            {#if isFileKind(a.kind)}
              <Button variant="outline" onclick={() => (browse = { kind: 'action', index })}
                ><FolderOpenIcon />Browse…</Button
              >
            {/if}
            {#if index === 'draft'}
              <Button onclick={addAction} disabled={!a.target.trim()}><PlusIcon />Add</Button>
            {:else}
              <Button
                variant="ghost"
                size="icon"
                aria-label="Move {a.name} up"
                disabled={index === 0}
                onclick={() => moveActionUp(index)}
              >
                <ArrowUpIcon />
              </Button>
              <Button variant="ghost" size="icon" aria-label="Remove {a.name}" onclick={() => removeAction(index)}
                ><XIcon /></Button
              >
            {/if}
          </div>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {@render eventChoices(a.events, (events) => set({ events }), isFileKind(a.kind) ? ['queue_finished'] : [])}
            {#if isFileKind(a.kind)}
              <label class="flex items-center gap-1.5 text-xs">
                <Checkbox checked={a.overwrite} onCheckedChange={(v) => set({ overwrite: v })} />
                Replace a file already there
              </label>
            {/if}
          </div>
        {/snippet}
        <div class="divide-y divide-border/60 rounded-xl border bg-card">
          {#each config.actions as a, i (i)}
            <div class="space-y-2 px-4 py-3 {a.enabled ? '' : 'opacity-60'}">
              {@render actionRow(a, (changes) => editAction(i, changes), i)}
            </div>
          {/each}
          <div class="space-y-2 px-4 py-3">
            {@render actionRow(actionDraft, (changes) => (actionDraft = { ...actionDraft, ...changes }), 'draft')}
          </div>
        </div>
        <details class="text-xs text-muted-foreground">
          <summary class="cursor-pointer select-none">Tokens for commands and folders</summary>
          <div class="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5">
            <div class="col-span-2 font-medium text-foreground">After a job</div>
            {#each Object.entries(config.action_tokens.job) as [token, what] (token)}
              <code>{`{${token}}`}</code><span>{what}</span>
            {/each}
            <div class="col-span-2 mt-2 font-medium text-foreground">When the queue finishes</div>
            {#each Object.entries(config.action_tokens.queue) as [token, what] (token)}
              <code>{`{${token}}`}</code><span>{what}</span>
            {/each}
            <p class="col-span-2 mt-2">
              A command's arguments are split before the tokens go in, so a path with spaces stays one argument and no
              shell reads it. For pipes or redirection, run the shell yourself (<code>cmd /c …</code>). Write
              <code>{'{{'}</code>
              and <code>{'}}'}</code> for a literal brace. A webhook POSTs the event as JSON.
            </p>
          </div>
        </details>
      </section>

      <PluginManager
        refreshKey={pluginRefresh}
        onupdated={(value) => {
          config = value
        }}
      />
    {/if}

    <section class="col-span-full min-w-0 space-y-3">
      <h2 class="font-medium">VideoForge</h2>
      <div class="flex flex-wrap items-center gap-3 text-sm">
        <Button variant="outline" class="text-destructive hover:text-destructive" onclick={() => (confirmStop = true)}>
          <PowerIcon />Shut down…
        </Button>
        <span class="text-muted-foreground">
          Stops the server{drops.desktop ? ' and closes this window' : ''}; start it again with
          <code class="text-xs">videoforge serve{drops.desktop ? ' --window' : ''}</code>.
        </span>
      </div>
    </section>
  </div>
</div>

<Dialog.Root bind:open={confirmStop}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Shut down VideoForge?</Dialog.Title>
      <Dialog.Description>
        {#if app.queue.running}
          A job is running: it is cancelled. Started again, it skips the steps it finished.
        {:else}
          No job is running.
        {/if}
        {#if app.queue.queued}{app.queue.queued} queued job(s) stay in the queue.{/if}
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => (confirmStop = false)}>Cancel</Button>
      <Button variant="destructive" disabled={stopping} onclick={shutDown}><PowerIcon />Shut down</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

{#if browse}
  <FileBrowser
    title={browse.kind === 'tool' ? browse.tool.label : browse.kind === 'action' ? 'The folder' : 'Add a folder'}
    mode={browse.kind !== 'tool' || browse.tool.folder ? 'folder' : 'files'}
    programs={browse.kind === 'tool' && !browse.tool.folder}
    start={browse.kind === 'tool' ? startFolder(browse.tool) : ''}
    onpick={(paths) => {
      const b = browse
      browse = null
      if (!paths[0] || !b) return
      if (b.kind === 'tool') setTool(b.tool, paths[0])
      else if (b.kind === 'action') {
        if (b.index === 'draft') actionDraft = { ...actionDraft, target: paths[0] }
        else editAction(b.index, { target: paths[0] })
      } else addRoot(paths[0])
    }}
    onclose={() => (browse = null)}
  />
{/if}
