<script lang="ts">
  // Settings, in ten tabs: Jobs, Queue & indexing, Presets, Files & folders | Tools, Plugins, Automation |
  // Appearance, Profiles, Import & export. Each change saves at once and is used by new jobs and runs;
  // Reset (under Profiles) goes back to the server's configuration defaults.
  import { onMount, tick } from 'svelte'
  import AppearanceSettings from '../components/AppearanceSettings.svelte'
  import FileBrowser from '../components/FileBrowser.svelte'
  import ConfigurationTransfer from '../components/ConfigurationTransfer.svelte'
  import PresetPackTransfer from '../components/PresetPackTransfer.svelte'
  import ResetConfiguration from '../components/ResetConfiguration.svelte'
  import ProfileManager from '../components/ProfileManager.svelte'
  import SavedOutputFolders from '../components/SavedOutputFolders.svelte'
  import PluginManager from '../components/PluginManager.svelte'
  import ManagedPresets from '../components/ManagedPresets.svelte'
  import AudioPresetMenu from '../components/AudioPresetMenu.svelte'
  import EncoderPresetMenu from '../components/EncoderPresetMenu.svelte'
  import TemplateSubsEditor from '../components/TemplateSubsEditor.svelte'
  import Tip from '../components/Tip.svelte'
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
  import { SETTINGS_TAB_KEY, peekSettingsSection, takeSettingsSection } from '../lib/settingsLink'
  import { saves } from '../lib/saves'
  import { PRIORITY_LABEL } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import { router } from '../lib/router.svelte'
  import { browserNotify } from '../lib/browserNotify.svelte'
  import type {
    ActionKind,
    ActionSetting,
    ConfigState,
    NamePolicy,
    NameUse,
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
    // a narrow window's row of sections can start with the remembered one scrolled out of view
    document.getElementById(`settings-tab-${tab}`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    try {
      await saves.flush()
      config = await api.config()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      return
    }
    const section = peekSettingsSection() // a link elsewhere asked for it: shown and focused
    if (section) {
      await tick()
      const target = document.getElementById(section)
      if (target) {
        takeSettingsSection() // one not shown yet (it loads its own data) takes it itself
        target.scrollIntoView({ block: 'start' })
        target.focus({ preventScroll: true })
      }
    }
    draft.events = defaultEvents()
    checkAll()
    void app.loadProfiles()
  })

  // One rule set's naming policy; "as templates say" for both is stored as nothing. The rule sets carry the
  // policies too (the Templates page's note), so they're read again.
  async function setNaming(ruleSet: string, policy: NamePolicy) {
    if (!config) return
    const naming = { ...config.naming }
    if (policy.file_name === 'template' && policy.title === 'template') delete naming[ruleSet]
    else naming[ruleSet] = policy
    if (await change({ naming })) app.ruleSets = await api.ruleSets().catch(() => app.ruleSets)
  }

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

  function setJobLimit(input: HTMLInputElement, kind?: string) {
    if (!config?.concurrency) return
    const policy = config.concurrency
    if (!input.reportValidity()) {
      input.value = String(kind ? policy.encoders[kind].cap : policy.total)
      return
    }
    const cap = input.valueAsNumber
    change({
      concurrency: kind
        ? { ...policy, encoders: { ...policy.encoders, [kind]: { ...policy.encoders[kind], cap } } }
        : { ...policy, total: cap },
    })
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

  async function setRuleSet(id: string) {
    if (await change({ rule_set: id === config?.rule_set_default ? null : id })) app.ruleSets = await api.ruleSets()
  }

  // Subtitle rules for new jobs whose template sets none: shown as changed at once, saved in order.
  let subsEdit = $state<{ value: TemplateSubs | null } | null>(null)
  let subsSent = 0
  const subsDefault = $derived(subsEdit ? subsEdit.value : (app.presets.subs_default ?? null))
  const defaultRuleSet = $derived(app.ruleSets.find((p) => p.id === config?.rule_set) ?? app.defaultRuleSet)
  const subFlags = $derived(defaultRuleSet?.track_properties.filter((f) => f.kind === 'sub') ?? [])
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

  function removeRoot(i: number) {
    setRoots(config!.roots.filter((_, j) => j !== i))
    focusAfterRemove('roots', i)
  }

  async function addRoot(path: string) {
    const p = path.trim()
    if (!p || !config) return
    const current = config.roots_custom ? config.roots : []
    if (await change({ roots: [...current.filter((r) => r.toLowerCase() !== p.toLowerCase()), p] })) newRoot = ''
  }

  // If there's no recent folder, Browse can start at the tool's folder (or the plugin folder itself).
  function startFolder(t: ToolSetting): string {
    const found = checks[t.name]?.found ?? ''
    return t.folder ? found : found.replace(/[\\/][^\\/]*$/, '')
  }

  const LOOK: Record<ToolStatus, { icon: typeof CheckIcon; tone: string; text: string }> = {
    ok: { icon: CheckIcon, tone: 'text-success', text: 'found' },
    unknown: { icon: TriangleAlertIcon, tone: 'text-warning', text: 'found, no version' },
    unsupported: { icon: XIcon, tone: 'text-destructive', text: 'unsupported version' },
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

  // A remove button's row goes, so focus moves to the next row's remove button (now in its place), else the one
  // before it, else the list's heading.
  async function focusAfterRemove(list: 'roots' | 'notifications' | 'actions', i: number) {
    await tick()
    const buttons = document.querySelectorAll<HTMLElement>(`[data-remove="${list}"]`)
    ;(buttons[i] ?? buttons[i - 1] ?? document.getElementById(`${list}-heading`))?.focus()
  }

  async function removeNotification(i: number) {
    if (!config) return
    const before = config.notifications
    const saved = setNotifications(before.filter((_, j) => j !== i))
    focusAfterRemove('notifications', i)
    if (await saved)
      toast(`Removed ${before[i].name}`, { action: { label: 'Undo', onClick: () => setNotifications(before) } })
  }

  async function testNotification(key: string, url: string) {
    testing = { ...testing, [key]: true }
    try {
      await api.testNotification(url.trim())
      toast.success('Test notification sent')
    } catch (e) {
      toast.error("Couldn't send the test notification", { description: e instanceof Error ? e.message : String(e) })
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
    shutdown: 'Seconds to wait first (60)',
    sleep: 'Seconds to wait first (60)',
  }
  const isFileKind = (k: ActionKind) => k === 'move' || k === 'copy'
  const isPowerKind = (k: ActionKind) => k === 'shutdown' || k === 'sleep'

  function setActions(list: ActionSetting[]): Promise<boolean> {
    return change({ actions: list })
  }

  // A move or copy runs after a job only: switching to one drops the queue's event.
  function withKind(a: ActionSetting, kind: ActionKind): ActionSetting {
    if (isPowerKind(kind)) return { ...a, kind, target: a.target || '60', events: ['queue_finished'] }
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
    const saved = setActions(before.filter((_, j) => j !== i))
    focusAfterRemove('actions', i)
    if (await saved)
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

  // The sections are tabs in three groups (your work, setup and add-ons, the app itself); the last one open is
  // remembered, and an old one that is gone (general, encoding, backup) opens Jobs.
  // `about` opens the tab and is its description for screen readers.
  const GROUPS = [
    [
      {
        id: 'jobs',
        label: 'Jobs',
        about:
          'The rule set, output names and subtitle rules new jobs start with, and whether test encodes measure their quality.',
      },
      {
        id: 'queue',
        label: 'Queue & indexing',
        about:
          'When jobs are indexed, how many audio encodes run beside the video, and how encodes share the CPU with other programs.',
      },
      {
        id: 'presets',
        label: 'Presets',
        about: 'Saved encoder and audio settings you can pick in any job or template. Templates have their own page.',
      },
      {
        id: 'files',
        label: 'Files & folders',
        about:
          "Saved output folders, work folder cleanup, what the folder browser can open, and VideoForge's data folder.",
      },
    ],
    [
      {
        id: 'tools',
        label: 'Tools',
        about: 'The programs VideoForge uses for each step, and where each one is installed.',
      },
      {
        id: 'plugins',
        label: 'Plugins',
        about: 'A plugin can add rule sets, templates and presets, and can run its own code when jobs start or finish.',
      },
      {
        id: 'automation',
        label: 'Automation',
        about: 'Send notifications and run actions when a job ends or the queue finishes.',
      },
    ],
    [
      { id: 'appearance', label: 'Appearance', about: 'How VideoForge looks in this browser.' },
      {
        id: 'profiles',
        label: 'Profiles',
        about: 'Switch between whole sets of settings, templates and presets, or reset the active one to its defaults.',
      },
      {
        id: 'transfer',
        label: 'Import & export',
        about:
          'Back up your settings, templates and presets, move them to another computer, or share presets with others.',
      },
    ],
  ] as const
  const TABS = GROUPS.flat()
  type TabId = (typeof TABS)[number]['id']
  const TAB_KEY = SETTINGS_TAB_KEY
  function readTab(): TabId {
    try {
      const saved = localStorage.getItem(TAB_KEY)
      return TABS.find((t) => t.id === saved)?.id ?? 'jobs'
    } catch {
      return 'jobs' // storage blocked
    }
  }
  let tab = $state<TabId>(readTab())
  function openTab(id: TabId) {
    tab = id
    try {
      localStorage.setItem(TAB_KEY, id)
    } catch {
      /* storage blocked */
    }
  }
</script>

<div class="@container/settings h-full overflow-auto p-4 sm:p-6">
  <div class="flex min-w-0 flex-col gap-6">
    <header class="col-span-full flex flex-wrap items-center gap-3">
      <h1 tabindex="-1" class="text-xl font-semibold outline-none">Settings</h1>
      <span class="text-sm text-muted-foreground">Changes are saved as you make them. New jobs and runs use them.</span>
      {#if pending}<span class="text-sm text-muted-foreground">{saveError ? 'Unsaved changes' : 'Saving…'}</span>{/if}
    </header>

    {#if error}<div
        class="col-span-full rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
      >
        {error}
      </div>{/if}
    {#if saveError}
      <div role="alert" class="col-span-full space-y-2 text-sm text-destructive">
        <p>Changes aren't saved: {saveError}</p>
        <Button onclick={() => recoverSaves()}>Retry saves</Button>
        <Button variant="outline" onclick={() => recoverSaves(true)}>Discard unsaved changes</Button>
      </div>
    {/if}
    {#each config?.restart ?? [] as note (note)}
      <div class="col-span-full rounded-md border border-warning/50 bg-warning/10 p-3 text-sm text-warning">{note}</div>
    {/each}

    <div class="flex min-w-0 flex-col gap-6 @min-[48rem]/settings:flex-row">
      <!-- a column beside the section in a wide window: it stays in view while a long section scrolls -->
      <nav
        class="flex gap-1 overflow-x-auto @min-[48rem]/settings:sticky @min-[48rem]/settings:top-0 @min-[48rem]/settings:max-h-[calc(100dvh-3rem)] @min-[48rem]/settings:w-44 @min-[48rem]/settings:shrink-0 @min-[48rem]/settings:flex-col @min-[48rem]/settings:self-start @min-[48rem]/settings:overflow-y-auto"
        aria-label="Settings sections"
      >
        {#snippet divider()}
          <div
            class="w-px shrink-0 self-stretch bg-border @min-[48rem]/settings:my-1 @min-[48rem]/settings:h-px @min-[48rem]/settings:w-auto"
            aria-hidden="true"
          ></div>
        {/snippet}
        {#each GROUPS as group, i (i)}
          {#if i}{@render divider()}{/if}
          {#each group as t (t.id)}
            <button
              type="button"
              id="settings-tab-{t.id}"
              class="shrink-0 rounded-md px-3 py-1.5 text-left text-sm whitespace-nowrap hover:bg-muted/60 {tab === t.id
                ? 'bg-muted font-medium'
                : 'text-muted-foreground'}"
              aria-current={tab === t.id ? 'page' : undefined}
              onclick={() => openTab(t.id)}>{t.label}</button
            >
          {/each}
        {/each}
        {@render divider()}
        <div class="flex shrink-0 items-center gap-2 @min-[48rem]/settings:flex-col @min-[48rem]/settings:items-start">
          {#if app.version}<span class="px-3 text-xs whitespace-nowrap text-muted-foreground tabular-nums"
              >VideoForge {app.version}</span
            >{/if}
          <Button
            variant="outline"
            class="text-destructive hover:text-destructive"
            onclick={() => (confirmStop = true)}
          >
            <PowerIcon />Shut down…
          </Button>
        </div>
      </nav>

      <!-- Help text (text-xs, muted) wraps at about 75 characters, wherever a section puts it. -->
      <div
        class="grid max-w-4xl min-w-0 flex-1 grid-cols-[minmax(0,1fr)] content-start gap-8 [&_.text-xs.text-muted-foreground]:max-w-[60ch]"
        role="group"
        aria-labelledby="settings-tab-{tab}"
        aria-describedby="settings-about"
      >
        <div class="col-span-full -mb-4 space-y-1">
          <p id="settings-about" class="text-sm text-muted-foreground">{TABS.find((t) => t.id === tab)?.about}</p>
          {#if tab === 'presets'}
            <button type="button" class="text-sm underline underline-offset-2" onclick={() => router.go('templates')}
              >Open Templates</button
            >
          {/if}
        </div>
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
        {#if tab === 'jobs'}
          {#if config}
            <section class="space-y-3">
              <h2 class="font-medium">Rule set</h2>
              <label class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span class="text-muted-foreground">New jobs start with</span>
                <NativeSelect value={config.rule_set} onchange={(e) => setRuleSet(e.currentTarget.value)}>
                  {#each config.rule_sets as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
                </NativeSelect>
                <span class="text-xs text-muted-foreground"
                  >Default: {config.rule_sets.find((p) => p.id === config!.rule_set_default)?.name ??
                    config.rule_set_default}</span
                >
              </label>
            </section>

            <section class="space-y-3">
              <h2 class="font-medium">Test encode</h2>
              <label class="flex items-start gap-3 text-sm">
                <Checkbox
                  class="mt-0.5"
                  checked={config.sample_quality}
                  aria-labelledby="sample-quality"
                  aria-describedby="sample-quality-help"
                  onCheckedChange={(v) => change({ sample_quality: v })}
                />
                <span>
                  <span id="sample-quality">Score its quality</span>
                  <span id="sample-quality-help" class="block text-xs text-muted-foreground">
                    After a test encode, VideoForge compares each of its frames with the encoder's input and shows the
                    SSIMULACRA2 and XPSNR scores (from vszip) beside its bitrate. Both are decoded again, so the test
                    encode takes longer.
                  </span>
                </span>
              </label>
            </section>

            <section class="col-span-full min-w-0 space-y-3" aria-labelledby="output-names">
              <h2 id="output-names" tabindex="-1" class="font-medium outline-none">Output names</h2>
              <p class="text-xs text-muted-foreground">
                For each rule set, whether its jobs name the file and set the MKV title with the name template. A job
                takes this when it's added or a template is applied to it, and its Output tab can still change it. A
                change here leaves jobs already added as they are.
              </p>
              <div class="space-y-3">
                {#each config.rule_sets as r (r.id)}
                  {@const policy = config.naming[r.id] ?? { file_name: 'template', title: 'template' }}
                  {@const own = app.ruleSets.find((x) => x.id === r.id)?.defaults.template.mux}
                  <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                    <span class="w-full font-medium sm:w-32 sm:shrink-0">{r.name}</span>
                    {#each [{ key: 'file_name', label: 'File name', own: own?.template_file_name }, { key: 'title', label: 'MKV title', own: own?.template_title }] as const as row (row.key)}
                      <label class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                        <span class="text-muted-foreground">{row.label}</span>
                        <NativeSelect
                          class="min-w-0"
                          aria-label="{r.name}: {row.label} from the name template"
                          aria-describedby={row.own === undefined ? undefined : `naming-${r.id}-${row.key}`}
                          value={policy[row.key]}
                          onchange={(e) => setNaming(r.id, { ...policy, [row.key]: e.currentTarget.value as NameUse })}
                        >
                          <option value="template">As each template says</option>
                          <option value="on">Always on</option>
                          <option value="off">Always off</option>
                        </NativeSelect>
                        <!-- beside the menu, not in its choice: a menu can't wrap, and this would cut it on a narrow window -->
                        {#if row.own !== undefined}
                          <span id="naming-{r.id}-{row.key}" class="text-xs text-muted-foreground"
                            >{r.name} defaults: {row.own ? 'on' : 'off'}</span
                          >
                        {/if}
                      </label>
                    {/each}
                  </div>
                {/each}
              </div>
            </section>

            <section class="col-span-full min-w-0 space-y-3" aria-label="Default subtitles">
              <h2 class="font-medium">Default subtitles</h2>
              {#if !defaultRuleSet?.track_editor || defaultRuleSet.picks_tracks}
                <p class="text-xs text-muted-foreground">
                  {defaultRuleSet?.name} picks its jobs' subtitles by its own rules, so these apply only to jobs with other
                  rule sets.
                </p>
              {/if}
              <TemplateSubsEditor
                value={subsDefault}
                flags={subFlags}
                toggleLabel="Choose every new job's subtitles by rules"
                offNote="When this is off, new jobs keep every subtitle track unless their template sets subtitle rules."
                appliedNote="New jobs get these rules unless their template sets its own. Jobs already in the queue keep theirs."
                onchange={setSubsDefault}
              />
            </section>
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {:else if tab === 'queue'}
          {#if config}
            <section class="space-y-3">
              {#if config.concurrency}
                {@const policy = config.concurrency}
                <h2 class="font-medium">Concurrent jobs</h2>
                <div class="flex items-center gap-2">
                  <input
                    id="concurrent-jobs"
                    type="checkbox"
                    checked={policy.enabled}
                    onchange={(e) => change({ concurrency: { ...policy, enabled: e.currentTarget.checked } })}
                  />
                  <label for="concurrent-jobs">Run multiple full jobs at once</label>
                </div>
                <p class="text-xs text-muted-foreground">
                  These limits apply to every profile on this installation. Jobs start in queue order. Changes apply to
                  future starts.
                </p>
                {#if policy.enabled}
                  <label class="block" for="total-job-cap">Total job slots</label>
                  <Input
                    id="total-job-cap"
                    type="number"
                    required
                    min="1"
                    step="1"
                    class="w-20"
                    value={policy.total}
                    onchange={(e) => setJobLimit(e.currentTarget)}
                  />
                  {#each Object.entries(policy.encoders) as [kind, limit] (kind)}
                    <fieldset class="flex items-center gap-3">
                      <legend class="font-medium">{kind === 'remux' ? 'Remux / reuse' : kind}</legend>
                      <label for={'cap-' + kind}>Job limit</label>
                      <Input
                        id={'cap-' + kind}
                        type="number"
                        required
                        min="1"
                        step="1"
                        class="w-20"
                        value={limit.cap}
                        onchange={(e) => setJobLimit(e.currentTarget, kind)}
                      />
                      <input
                        id={'alone-' + kind}
                        type="checkbox"
                        checked={limit.run_alone}
                        onchange={(e) =>
                          change({
                            concurrency: {
                              ...policy,
                              encoders: {
                                ...policy.encoders,
                                [kind]: { ...limit, run_alone: e.currentTarget.checked },
                              },
                            },
                          })}
                      />
                      <label for={'alone-' + kind}>Run alone</label>
                    </fieldset>
                  {/each}
                  <p class="text-xs text-muted-foreground">
                    Give each custom script or raw tool argument its own paths for any extra files it writes.
                  </p>
                {/if}
                <div class="flex items-center gap-2">
                  <input
                    id="limit-samples"
                    type="checkbox"
                    checked={policy.limit_samples}
                    onchange={(e) => change({ concurrency: { ...policy, limit_samples: e.currentTarget.checked } })}
                  />
                  <label for="limit-samples">Count samples and CRF searches toward job limits</label>
                </div>
              {/if}
            </section>

            <section class="space-y-3">
              <h2 class="font-medium">Batch indexing</h2>
              <label class="flex items-start gap-3 text-sm">
                <Checkbox
                  class="mt-0.5"
                  checked={config.auto_index}
                  aria-labelledby="auto-index"
                  aria-describedby="auto-index-help"
                  onCheckedChange={(v) => change({ auto_index: v })}
                />
                <span>
                  <span id="auto-index">Index new jobs</span>
                  <span id="auto-index-help" class="block text-xs text-muted-foreground">
                    Indexes each new job in the background, beside the queue, as soon as its tracks are read. Its
                    preview is then ready when you open it.
                  </span>
                </span>
              </label>
              <label class="flex items-start gap-3 text-sm">
                <Checkbox
                  class="mt-0.5"
                  checked={config.auto_crop}
                  aria-labelledby="auto-crop"
                  aria-describedby="auto-crop-help"
                  onCheckedChange={(v) => change({ auto_crop: v })}
                />
                <span>
                  <span id="auto-crop">Auto-crop new jobs</span>
                  <span id="auto-crop-help" class="block text-xs text-muted-foreground">
                    Detects each new job's crop once it's indexed, and indexes the job for this even with Index new jobs
                    off. A template with a fixed crop keeps its crop, and a crop you set by hand always wins.
                  </span>
                </span>
              </label>
              <label class="flex items-start gap-3 text-sm">
                <Checkbox
                  class="mt-0.5"
                  checked={config.index_waits_for_disk}
                  aria-labelledby="index-waits"
                  aria-describedby="index-waits-help"
                  onCheckedChange={(v) => change({ index_waits_for_disk: v })}
                />
                <span>
                  <span id="index-waits">Wait while an encode reads the same disk</span>
                  <span id="index-waits-help" class="block text-xs text-muted-foreground">
                    Indexing a job waits while the running job uses the disk its source is on, and jobs on other disks
                    go first. Index now on a job's Video tab skips this wait.
                  </span>
                </span>
              </label>
              <label class="ml-7 flex items-start gap-3 text-sm">
                <Checkbox
                  class="mt-0.5"
                  checked={config.index_during_video}
                  aria-labelledby="index-during-video"
                  aria-describedby="index-during-video-help"
                  disabled={!config.index_waits_for_disk}
                  onCheckedChange={(v) => change({ index_during_video: v })}
                />
                <span class={config.index_waits_for_disk ? '' : 'opacity-60'}>
                  <span id="index-during-video">Index anyway while it only encodes video</span>
                  <span id="index-during-video-help" class="block text-xs text-muted-foreground">
                    The video encode reads the source slowly, so an index beside it costs little. The wait still holds
                    while the job extracts tracks, encodes audio, indexes, or builds the output file.
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
                  aria-labelledby="parallel-audio"
                  aria-describedby="parallel-audio-help"
                  onchange={(e) => setParallelAudio(e.currentTarget)}
                />
                <span>
                  <span id="parallel-audio">At once per job, beside its video encode</span>
                  <span id="parallel-audio-help" class="block text-xs text-muted-foreground">
                    A job's audio encodes start once its source is indexed and run while the video encodes. The output
                    file is built when they're done. 0 encodes them one at a time, before the video. Default: {config.parallel_audio_default}
                  </span>
                </span>
              </label>
            </section>

            <section class="space-y-3">
              <h2 class="font-medium">Process priority</h2>
              {#each [{ key: 'encoder_priority', label: 'Video encode', hint: 'the encoder (x264, x265, ffmpeg for VP8 / VP9, SvtAv1EncApp) and the vspipe feeding it' }, { key: 'tool_priority', label: 'Other tools', hint: 'audio encodes, building the output file, indexing' }] as const as row (row.key)}
                <label class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
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
                  <span class="min-w-48 flex-1 text-xs text-muted-foreground">
                    {row.hint}. Default: {PRIORITY_LABEL[config[`${row.key}_default`]]}
                  </span>
                </label>
              {/each}
              <p class="text-xs text-muted-foreground">
                A change here applies to jobs, indexing and test encodes that start after you make it. To change the
                ones already running, use the priority menu on the Queue's toolbar. On Linux, Above normal and High need
                the CAP_SYS_NICE permission, and so does raising a running tool's priority again. Without it, the tool
                keeps its lower priority.
              </p>
            </section>
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {:else if tab === 'presets'}
          <section class="col-span-full space-y-3">
            <h2 class="font-medium">Encoder presets</h2>
            <div class="flex flex-wrap gap-2">
              {#if app.defaultRuleSet}
                <EncoderPresetMenu
                  ruleSet={app.defaultRuleSet.id}
                  current={app.defaultRuleSet.defaults.encoder}
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
          {#if config}
            <ManagedPresets disabled={pending > 0 || !!saveError} refreshKey={pluginRefresh} />
          {/if}
        {:else if tab === 'files'}
          {#if config}
            <SavedOutputFolders />

            <section class="space-y-3">
              <h2 class="font-medium">Work folders</h2>
              <label class="flex items-start gap-3 text-sm">
                <Checkbox
                  class="mt-0.5"
                  checked={config.delete_work_dir}
                  aria-labelledby="delete-work-dir"
                  aria-describedby="delete-work-dir-help"
                  onCheckedChange={(v) => change({ delete_work_dir: v === config?.delete_work_dir_default ? null : v })}
                />
                <span>
                  <span id="delete-work-dir">Delete a job's work folder once it's done</span>
                  <span id="delete-work-dir-help" class="block text-xs text-muted-foreground">
                    The <code>&lt;source&gt;_tmp</code> folder next to the source (index, encodes, log) is deleted after
                    the job succeeds; its job records and log are copied to {config.records_dir} first (the newest 100 kept).
                    A job that fails or is canceled keeps it, to resume from. Default:
                    {config.delete_work_dir_default ? 'on' : 'off'}
                  </span>
                </span>
              </label>
            </section>

            <section class="space-y-3">
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                <h2 id="roots-heading" tabindex="-1" class="font-medium outline-none">Folder browser</h2>
                <span class="min-w-48 flex-1 text-xs text-muted-foreground">
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
                {#each config.roots as r, i (r)}
                  <span class="flex items-center gap-1 rounded-md bg-muted px-2 py-1 font-mono text-xs">
                    {r}
                    {#if config.roots_custom}
                      <button
                        class="text-muted-foreground hover:text-destructive"
                        aria-label="Remove {r}"
                        data-remove="roots"
                        onclick={() => removeRoot(i)}><XIcon class="size-3" /></button
                      >
                    {/if}
                  </span>
                {/each}
              </div>
              <div class="flex flex-wrap gap-2">
                <Input
                  class="max-w-96 min-w-48 flex-1 font-mono text-xs"
                  placeholder="D:\Media"
                  bind:value={newRoot}
                  onkeydown={(e) => e.key === 'Enter' && addRoot(newRoot)}
                />
                <Button variant="outline" onclick={() => addRoot(newRoot)} disabled={!newRoot.trim()}>Add folder</Button
                >
                <Button variant="outline" onclick={() => (browse = { kind: 'root' })}><FolderOpenIcon />Browse…</Button>
              </div>
            </section>

            <section class="min-w-0 space-y-2">
              <h2 class="font-medium">Data folder</h2>
              <code class="block font-mono text-xs break-all">{config.data_dir}</code>
              <p class="text-xs text-muted-foreground">
                VideoForge stores its database, logs, job records and plugins here.
              </p>
            </section>
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {:else if tab === 'tools'}
          {#if config}
            <section class="col-span-full min-w-0 space-y-3">
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                <h2 class="font-medium">Tools</h2>
                <span class="min-w-48 flex-1 text-xs text-muted-foreground"
                  >A name without a folder, like ffmpeg, is looked up on PATH.</span
                >
                <Button
                  variant="outline"
                  class="ml-auto"
                  onclick={checkAll}
                  disabled={Object.values(checking).some(Boolean)}
                >
                  <RefreshCwIcon />Check again
                </Button>
              </div>
              <div class="divide-y divide-border/60 rounded-xl border bg-card">
                {#each config.tools as t (t.name)}
                  {@const c = checks[t.name]}
                  {@const look = c ? LOOK[c.status] : null}
                  <!-- the name goes above the path when the pane is too narrow for both side by side -->
                  <div
                    class="grid grid-cols-[minmax(0,1fr)] items-baseline gap-x-4 gap-y-1.5 px-4 py-3 @min-[40rem]/settings:grid-cols-[12rem_1fr]"
                  >
                    <div>
                      <div class="text-sm font-medium">{t.label}</div>
                      <div class="text-xs text-muted-foreground">{t.purpose}</div>
                    </div>
                    <div class="flex min-w-0 flex-wrap items-center gap-2">
                      <Input
                        class="min-w-24 flex-1 font-mono text-xs {t.custom ? 'border-primary/60' : ''}"
                        value={t.custom ?? t.default}
                        placeholder={t.default || 'not set'}
                        aria-label="{t.label} path"
                        onchange={(e) => setTool(t, e.currentTarget.value)}
                      />
                      <Button variant="outline" onclick={() => (browse = { kind: 'tool', tool: t })}
                        ><FolderOpenIcon />Browse…</Button
                      >
                      <Tip text="Back to the default: {t.default || '(none)'}">
                        <Button variant="ghost" size="sm" disabled={!t.custom} onclick={() => setTool(t, '')}
                          >Reset</Button
                        >
                      </Tip>
                    </div>
                    <div class="hidden @min-[40rem]/settings:block"></div>
                    <div class="flex min-w-0 items-center gap-2 text-xs">
                      {#if checking[t.name]}
                        <span class="text-muted-foreground">checking…</span>
                      {:else if c && look}
                        <span class="flex shrink-0 items-center gap-1 {look.tone}"
                          ><look.icon class="size-3.5" />{look.text}</span
                        >
                        {#if c.version}<Tip class="block truncate" text={c.version}>{c.version}</Tip>{/if}
                        {#if c.detail}<Tip class="block truncate text-muted-foreground" text={c.detail}>{c.detail}</Tip
                          >{/if}
                        {#if c.found && c.found !== t.path}<Tip
                            class="block truncate text-muted-foreground"
                            text={c.found}>· {c.found}</Tip
                          >{/if}
                      {/if}
                    </div>
                    {#if t.name === 'x265'}
                      <div class="mt-1 rounded-lg border bg-muted/30 px-3 py-2 @min-[40rem]/settings:col-start-2">
                        <label
                          class="flex cursor-pointer items-start justify-between gap-4 has-disabled:cursor-default"
                        >
                          <span class="min-w-0">
                            <span id="x265-avx512-label" class="block text-sm font-medium">Allow AVX-512</span>
                            <span id="x265-avx512-help" class="block text-xs text-muted-foreground">
                              Applies across profiles. CPU flags set by a job or preset take priority.
                            </span>
                          </span>
                          <span class="relative mt-0.5 flex shrink-0 items-center">
                            <input
                              type="checkbox"
                              {...{ switch: '' } as { switch: string }}
                              role="switch"
                              class="peer sr-only"
                              aria-labelledby="x265-avx512-label"
                              aria-describedby="x265-avx512-help x265-avx512-status"
                              checked={config.x265_avx512}
                              disabled={checking[t.name] || (c?.avx512 !== true && !config.x265_avx512)}
                              onchange={(event) => change({ x265_avx512: event.currentTarget.checked })}
                            />
                            <span
                              aria-hidden="true"
                              class="relative h-6 w-10 rounded-full border border-muted-foreground bg-muted before:absolute before:top-0.5 before:left-0.5 before:size-4 before:rounded-full before:bg-muted-foreground peer-checked:border-primary peer-checked:bg-primary peer-checked:before:translate-x-4 peer-checked:before:bg-primary-foreground peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring peer-disabled:opacity-60 forced-colors:peer-checked:before:bg-[Highlight]"
                            ></span>
                          </span>
                        </label>
                        <p id="x265-avx512-status" class="mt-1 text-xs text-muted-foreground" aria-live="polite">
                          {#if checking[t.name]}
                            Checking AVX-512 support…
                          {:else if c?.avx512 === false}
                            AVX-512 is unavailable with this CPU and x265 build.
                          {:else if c?.avx512 === true}
                            AVX-512 is available.
                          {:else}
                            AVX-512 support could not be verified.
                          {/if}
                        </p>
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
              <p class="text-xs text-muted-foreground">
                VideoForge can't include Dolby Encoding Engine or qaac's CoreAudioToolbox, so install them yourself and
                set them here. DDP encodes need DeeZy 2 and the DEE 6.7 tools folder, plus truehdd for Atmos; dee_shim
                adds DDP 7.1 and the 7.1 Atmos modes. AAC encodes need ffmpeg and qaac.
              </p>
            </section>
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {:else if tab === 'plugins'}
          {#if config}
            <PluginManager
              refreshKey={pluginRefresh}
              onupdated={(value) => {
                config = value
              }}
            />
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {:else if tab === 'automation'}
          {#if config}
            <section class="col-span-full min-w-0 space-y-3">
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                <h2 id="notifications-heading" tabindex="-1" class="font-medium outline-none">Notifications</h2>
                <span class="min-w-48 flex-1 text-xs text-muted-foreground">
                  Tell Discord, Telegram, ntfy, Pushover, email or
                  <a
                    class="underline hover:text-foreground"
                    href="https://github.com/caronc/apprise/wiki"
                    target="_blank"
                    rel="noreferrer">any service Apprise supports</a
                  > when jobs end.
                </span>
              </div>
              <div class="space-y-1 rounded-xl border bg-card px-4 py-3">
                <label class="flex items-center gap-2 text-sm has-disabled:opacity-60">
                  <Checkbox
                    checked={browserNotify.on}
                    disabled={!browserNotify.supported || browserNotify.permission === 'denied'}
                    onCheckedChange={(v) => browserNotify.set(v)}
                  />
                  Desktop notification from this browser when the queue finishes
                </label>
                <p class="pl-6 text-xs text-muted-foreground">
                  {#if !browserNotify.supported}
                    Browsers allow these only on https or localhost, and this page is on plain http.
                  {:else if browserNotify.permission === 'denied'}
                    This browser blocks notifications from VideoForge. Allow them in the browser's site settings.
                  {:else}
                    Shown only when VideoForge isn't the tab in front. When it is, each job's toast tells you instead.
                    This setting is for this browser only.
                  {/if}
                </p>
              </div>
              <div class="divide-y divide-border/60 rounded-xl border bg-card">
                {#each config.notifications as d, i (i)}
                  <div class="space-y-2 px-4 py-3 {d.enabled ? '' : 'opacity-60'}">
                    <div class="flex min-w-0 flex-wrap items-center gap-2">
                      <Tip text={d.enabled ? 'On' : 'Off, so nothing is sent here'}>
                        <Checkbox
                          checked={d.enabled}
                          aria-label="Send to {d.name}"
                          onCheckedChange={(v) => editNotification(i, { enabled: v })}
                        />
                      </Tip>
                      <Input
                        class="max-w-40 grow basis-32 text-sm"
                        value={d.name}
                        aria-label="Name"
                        onchange={(e) => editNotification(i, { name: e.currentTarget.value })}
                      />
                      <Input
                        class="min-w-24 flex-1 font-mono text-xs"
                        value={d.url}
                        aria-label="{d.name} Apprise URL"
                        onchange={(e) => editNotification(i, { url: e.currentTarget.value })}
                      />
                      <Button
                        variant="outline"
                        disabled={testing[i]}
                        onclick={() => testNotification(String(i), d.url)}
                      >
                        <SendIcon />{testing[i] ? 'Sending…' : 'Test'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Remove {d.name}"
                        data-remove="notifications"
                        onclick={() => removeNotification(i)}
                      >
                        <XIcon />
                      </Button>
                    </div>
                    {@render eventChoices(d.events, (events) => editNotification(i, { events }))}
                  </div>
                {/each}
                <div class="space-y-2 px-4 py-3">
                  <div class="flex min-w-0 flex-wrap items-center gap-2">
                    <Input
                      class="max-w-40 grow basis-32 text-sm"
                      placeholder="Name (optional)"
                      bind:value={draft.name}
                    />
                    <Input
                      class="min-w-24 flex-1 font-mono text-xs"
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
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                <h2 id="actions-heading" tabindex="-1" class="font-medium outline-none">Actions</h2>
                <span class="min-w-48 flex-1 text-xs text-muted-foreground">
                  After a job ends or the queue finishes, actions can move or copy the output, run a command, call a
                  webhook, or shut down or sleep the computer. A job's actions run in this order, and after a move, the
                  ones below it get the new path.
                </span>
              </div>
              {#if !config.allow_commands}
                <p class="text-xs text-warning">
                  Command actions are off in this server's configuration. To turn them on, set commands = true under
                  [actions] in videoforge.toml. Do this only if no one else can reach this page, because it has no
                  login.
                </p>
              {/if}
              {#snippet actionRow(
                a: ActionSetting,
                set: (changes: Partial<ActionSetting>) => void,
                index: number | 'draft',
              )}
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  {#if index !== 'draft'}
                    <Tip text={a.enabled ? 'On' : "Off, so it doesn't run"}>
                      <Checkbox
                        checked={a.enabled}
                        aria-label="Run {a.name}"
                        onCheckedChange={(v) => set({ enabled: v })}
                      />
                    </Tip>
                  {/if}
                  <Input
                    class="max-w-40 grow basis-32 text-sm"
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
                    class="min-w-24 flex-1 font-mono text-xs"
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
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Remove {a.name}"
                      data-remove="actions"
                      onclick={() => removeAction(index)}><XIcon /></Button
                    >
                  {/if}
                </div>
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                  {#if isPowerKind(a.kind)}
                    <label class="flex items-center gap-1.5 text-xs">
                      <Checkbox checked disabled />
                      Queue finished
                    </label>
                    <span class="text-xs text-muted-foreground">
                      Runs only when the queue runs out of jobs, not when it's stopped. Put it last.
                    </span>
                  {:else}
                    {@render eventChoices(
                      a.events,
                      (events) => set({ events }),
                      isFileKind(a.kind) ? ['queue_finished'] : [],
                    )}
                  {/if}
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
                <!-- wrap-anywhere: descriptions hold unbroken paths like (<source>_tmp) that would widen the list -->
                <div class="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 wrap-anywhere">
                  <div class="col-span-2 font-medium text-foreground">After a job</div>
                  {#each Object.entries(config.action_tokens.job) as [token, what] (token)}
                    <code>{`{${token}}`}</code><span>{what}</span>
                  {/each}
                  <div class="col-span-2 mt-2 font-medium text-foreground">When the queue finishes</div>
                  {#each Object.entries(config.action_tokens.queue) as [token, what] (token)}
                    <code>{`{${token}}`}</code><span>{what}</span>
                  {/each}
                  <p class="col-span-2 mt-2">
                    A command's arguments are split before the tokens go in, so a path with spaces stays one argument
                    and no shell reads it. For pipes or redirection, run the shell yourself (<code>cmd /c …</code>).
                    Write
                    <code>{'{{'}</code>
                    and <code>{'}}'}</code> for a literal brace. A webhook POSTs the event as JSON.
                  </p>
                </div>
              </details>
            </section>
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {:else if tab === 'appearance'}
          <AppearanceSettings />
        {:else if tab === 'profiles'}
          <ProfileManager
            disabled={pending > 0 || !!saveError}
            onswitched={(value) => {
              config = value
              pluginRefresh++
              checks = {}
              checkAll()
            }}
          />
          {#if config}
            <ResetConfiguration
              disabled={pending > 0 || !!saveError || app.queue.running}
              onreset={(value) => {
                config = value
                pluginRefresh++
                checks = {}
                checkAll()
              }}
            />
          {/if}
        {:else if tab === 'transfer'}
          {#if config}
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

            <section class="col-span-full space-y-3">
              <h2 class="font-medium">Templates and plugins</h2>
              <div class="flex flex-wrap items-center gap-3 text-sm">
                <span class="text-muted-foreground">Import and export templates on the Templates page.</span>
                <Button variant="outline" onclick={() => router.go('templates')}>Open Templates</Button>
              </div>
              <div class="flex flex-wrap items-center gap-3 text-sm">
                <span class="text-muted-foreground">Install a plugin from its ZIP file under Plugins.</span>
                <Button
                  variant="outline"
                  onclick={() => {
                    openTab('plugins')
                    document.getElementById('settings-tab-plugins')?.focus() // this button goes with its tab
                  }}>Open Plugins</Button
                >
              </div>
            </section>
          {:else}
            <p class="text-muted-foreground">{error ? '' : 'Loading…'}</p>
          {/if}
        {/if}
      </div>
    </div>
  </div>
</div>

<Dialog.Root bind:open={confirmStop}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Shut down VideoForge?</Dialog.Title>
      <Dialog.Description>
        {#if app.queue.running}
          The running job is canceled. When it runs again, it skips the steps it finished.
        {:else}
          No job is running.
        {/if}
        {#if app.queue.queued}{app.queue.queued} queued {app.queue.queued === 1 ? 'job stays' : 'jobs stay'} in the queue.{/if}
        Start VideoForge again with <code class="text-xs">videoforge serve</code> (or VideoForge.exe).
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
    title={browse.kind === 'tool'
      ? browse.tool.label
      : browse.kind === 'action'
        ? 'Destination folder'
        : 'Add a folder'}
    mode={browse.kind !== 'tool' || browse.tool.folder ? 'folder' : 'files'}
    programs={browse.kind === 'tool' && !browse.tool.folder}
    orFolder={browse.kind === 'tool' && browse.tool.name === 'dee'}
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
