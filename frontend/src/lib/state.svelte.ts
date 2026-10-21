// App-wide state, kept current by the server's event WebSocket (/api/events).
import { toast } from 'svelte-sonner'
import { api } from './api'
import { STATUS_LABEL } from './format'
import type { AudioEncodeInfo, AudioPresetSettings, EncoderSettings, FilterPreset, JobSummary, Preset, PresetKind, Presets, Profile, QueueState, StepRun, Template, VideoPresetData } from './types'
import { keepVideoViews } from './videoView.svelte'

const MAX_LOG = 20000

export interface LogLine {
  remoteSeq?: number
  seq: number // increasing; a view that fetched a snapshot takes the lines after it
  job: string | null // job id; null for app messages
  step: string | null // the step it came from (its header and job messages: null)
  line: string
}

export type PresetData<K extends PresetKind> = K extends 'video' ? VideoPresetData : K extends 'template' ? Template : K extends 'audio' ? AudioPresetSettings : EncoderSettings

class AppState {
  jobs = $state<JobSummary[]>([])
  queue = $state<QueueState>({ running: false, current: null, stop_after_current: false, paused: false, priority: null, queued: 0, indexing: null, index_queued: 0 })
  profiles = $state<Profile[]>([])
  log = $state<LogLine[]>([])
  connected = $state(false)
  connectionVersion = $state(0)
  connection = $state<'connecting' | 'retrying' | 'offline' | 'connected'>('connecting')
  connectionError = $state('')
  /** Shut down from the page: no reconnecting, the app shows that it stopped. */
  stopped = $state(false)
  // Bumped per job whenever the server says it changed; open editors refetch on it.
  versions = $state<Record<string, number>>({})
  // Each job's last run, step by step, kept current by `step` events.
  runs = $state<Record<string, StepRun[]>>({})
  stepVersions: Record<string, Record<string, number>> = {}
  runStarts = $state<Record<string, number>>({}) // logSeq when each job's latest run began
  logSeq = 0
  encodes = $state<AudioEncodeInfo[]>([])
  presets = $state<Presets>({ video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] })
  filterPresets = $state<FilterPreset[]>([])
  version = $state('') // the server's, for bug reports

  #socket: WebSocket | null = null
  #refreshTimer: ReturnType<typeof setTimeout> | null = null
  #retry = 500
  #retryTimer: ReturnType<typeof setTimeout> | null = null
  #starting: Promise<void> | null = null

  // The audio encodes, with the tools each one lacks.
  async loadEncoders(): Promise<void> {
    try {
      this.encodes = await api.encoders()
    } catch {
      /* shown as available; the job's plan still blocks a missing tool */
    }
  }

  async loadPresets(): Promise<void> {
    try {
      this.presets = await api.presets()
    } catch {
      /* only the profiles' defaults are offered */
    }
  }

  async loadFilterPresets(): Promise<void> {
    try {
      this.filterPresets = await api.filterPresets()
    } catch {
      /* the chain is still editable; only adding a built-in filter is missing */
    }
  }

  // A kind's presets for a profile: its defaults first (built in), the encoder starters, then the user's.
  presetChoices<K extends PresetKind>(kind: K, profileId: string): (Preset<PresetData<K>> & { builtin: boolean; badge?: string })[] {
    const p = this.profiles.find(x => x.id === profileId)
    const own = p && kind !== 'audio' ? [{ name: `${p.name} defaults`, data: p.defaults[kind as keyof Profile['defaults']] as unknown as PresetData<K>, builtin: true }] : []
    const starters = kind === 'encoder' ? (this.presets.encoder_starters ?? []).map(x => ({ ...x, data: x.data as unknown as PresetData<K>, builtin: true, badge: 'starter' })) : []
    return [...own, ...starters, ...(this.presets[kind] as Preset<PresetData<K>>[]).map(x => ({ ...x, builtin: false }))]
  }

  // The name of the template New jobs starts on: the user's starred one, else the profile's own.
  defaultTemplate(profileId: string): string {
    const p = this.profiles.find(x => x.id === profileId)
    return this.presets.template_defaults[profileId] ?? (p ? `${p.name} defaults` : '')
  }

  get defaultProfile(): Profile | undefined {
    return this.profiles.find(p => p.default) ?? this.profiles[0]
  }

  jobName(id: string | null): string {
    if (!id) return 'VideoForge'
    return this.jobs.find(j => j.id === id)?.name ?? id
  }

  start(): Promise<void> {
    if (this.#starting || this.stopped) return this.#starting ?? Promise.resolve()
    if (this.#retryTimer) clearTimeout(this.#retryTimer)
    this.#retryTimer = null
    this.connection = this.connectionError ? 'retrying' : 'connecting'
    this.#starting = (async () => {
      try {
        const [profiles, presets, filters, encodes, health] = await Promise.all([
          api.profiles(), api.presets(), api.filterPresets(), api.encoders(), api.health(),
        ])
        await this.refreshJobs()
        this.profiles = profiles
        this.presets = presets
        this.filterPresets = filters
        this.encodes = encodes
        this.version = health.version
        this.connectionError = ''
        this.connect()
      } catch (e) {
        this.connectionError = e instanceof Error ? e.message : String(e)
        this.connection = 'offline'
        this.#scheduleRetry()
      }
    })().finally(() => { this.#starting = null })
    return this.#starting
  }

  #scheduleRetry(): void {
    if (this.stopped || this.#retryTimer) return
    this.#retryTimer = setTimeout(() => { this.#retryTimer = null; void this.start() }, this.#retry)
    this.#retry = Math.min(this.#retry * 2, 8000)
  }

  async refreshJobs(): Promise<void> {
    const before = new Map(this.jobs.map(j => [j.id, j.status]))
    this.jobs = await api.jobs()
    keepVideoViews(this.jobs.map(j => j.id))
    for (const j of this.jobs) {
      if (before.get(j.id) === 'running' && j.status !== 'running') this.#finished(j)
      if (before.get(j.id) === 'indexing' && j.status !== 'indexing' && j.index_error)
        toast.error(`${j.name}: indexing failed`, { description: j.index_error })
    }
  }

  // A toast when a run ends: done, or failed / invalid / cancelled with its first issue.
  #finished(job: JobSummary): void {
    const open = { label: 'Open', onClick: () => (location.hash = `#/queue/${encodeURIComponent(job.id)}`) }
    if (job.status === 'done') toast.success(`${job.name} is done`, { action: open })
    else if (job.status === 'cancelled') toast.warning(`${job.name} was cancelled`, { action: open })
    else toast.error(`${job.name}: ${STATUS_LABEL[job.status].toLowerCase()}`, { description: job.issue || undefined, action: open })
  }

  #scheduleRefresh(): void {
    if (this.#refreshTimer) return
    this.#refreshTimer = setTimeout(async () => {
      this.#refreshTimer = null
      try {
        await this.refreshJobs()
      } catch {
        /* the socket reconnect will retry */
      }
    }, 120)
  }

  #indexStopped = false

  /** Stop the index lane (the job being indexed is cancelled, the waiting ones dropped). */
  async stopIndexing(): Promise<void> {
    this.#indexStopped = true
    await api.stopIndex()
  }

  #bump(id: string): void {
    this.versions[id] = (this.versions[id] ?? 0) + 1
  }

  addLog(line: string, job: string | null = null, step: string | null = null, remoteSeq?: number): void {
    this.log.push({ seq: ++this.logSeq, job, step, line, remoteSeq })
    if (this.log.length > MAX_LOG) this.log.splice(0, this.log.length - MAX_LOG)
  }

  connect(): void {
    if (this.#socket || this.stopped) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/events`)
    this.#socket = ws
    ws.onopen = () => {
      this.log = this.log.filter(line => line.job === null)
      this.runs = {}
      this.runStarts = {}
      this.stepVersions = {}
      this.connectionVersion++
      for (const job of this.jobs) this.#bump(job.id)
      this.connected = true
      this.connection = 'connected'
      this.connectionError = ''
      this.#retry = 500
      this.#scheduleRefresh()
    }
    ws.onclose = () => {
      this.connected = false
      this.#socket = null
      if (this.stopped) return
      this.connection = 'offline'
      this.connectionError = 'Connection lost. Retrying automatically.'
      this.#scheduleRetry()
    }
    ws.onmessage = msg => this.#handle(JSON.parse(msg.data))
  }

  #handle(event: { type: string; [k: string]: unknown }): void {
    switch (event.type) {
      case 'hello':
      case 'queue': {
        const { type: _t, ...q } = event
        const was = this.queue
        this.queue = q as unknown as QueueState
        if (event.type === 'queue' && was.indexing && !this.queue.indexing && !this.queue.index_queued) {
          if (this.#indexStopped) toast.info('Indexing stopped')
          else toast.success('Indexing finished', { description: 'The indexed jobs open at once.' })
          this.#indexStopped = false
        }
        break
      }
      case 'job':
      case 'job.added':
      case 'job.removed':
        this.#bump(event.id as string)
        this.#scheduleRefresh()
        break
      case 'order':
        this.#scheduleRefresh()
        break
      case 'progress': {
        const job = this.jobs.find(j => j.id === event.id)
        if (job) {
          const { type: _t, id: _i, ...p } = event
          job.progress = p as unknown as JobSummary['progress']
          const status = event.id === this.queue.indexing ? 'indexing' : 'running'
          if (job.status !== status) job.status = status
        }
        break
      }
      case 'log':
        this.addLog(event.line as string, event.id as string, (event.step as string | null) ?? null, event.seq as number)
        break
      case 'step': {
        const id = event.id as string
        const index = event.index as number
        const step = event.step as StepRun
        this.stepVersions[id] ??= {}
        this.stepVersions[id][step.id] = event.seq as number
        if (index < 0) break
        // A new run announces its whole list, pending, from index 0.
        if (index === 0 && step.status === 'pending') {
          this.runs[id] = []
          this.runStarts[id] = this.logSeq
        }
        this.runs[id] ??= []
        const list = this.runs[id]
        list.length = Math.max(list.length, event.total as number)
        list[index] = step
        break
      }
    }
  }
}

export const app = new AppState()
