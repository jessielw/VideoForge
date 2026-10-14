// App-wide state, kept current by the server's event WebSocket (/api/events).
import { toast } from 'svelte-sonner'
import { api } from './api'
import { STATUS_LABEL } from './format'
import type { AudioEncodeInfo, EncoderSettings, JobSummary, Preset, PresetKind, Presets, Profile, QueueState, StepRun, VideoPresetData } from './types'

const MAX_LOG = 20000

export interface LogLine {
  seq: number // increasing; a view that fetched a snapshot takes the lines after it
  job: string | null // job id; null for app messages
  step: string | null // the step it came from (its header and job messages: null)
  line: string
}

export type PresetData<K extends PresetKind> = K extends 'video' ? VideoPresetData : EncoderSettings

class AppState {
  jobs = $state<JobSummary[]>([])
  queue = $state<QueueState>({ running: false, current: null, stop_after_current: false, queued: 0 })
  profiles = $state<Profile[]>([])
  log = $state<LogLine[]>([])
  connected = $state(false)
  // Bumped per job whenever the server says it changed; open editors refetch on it.
  versions = $state<Record<string, number>>({})
  // Each job's last run, step by step, kept current by `step` events.
  runs = $state<Record<string, StepRun[]>>({})
  runStarts = $state<Record<string, number>>({}) // logSeq when each job's latest run began
  logSeq = 0
  encodes = $state<AudioEncodeInfo[]>([])
  presets = $state<Presets>({ video: [], encoder: [] })

  #socket: WebSocket | null = null
  #refreshTimer: ReturnType<typeof setTimeout> | null = null
  #retry = 500

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

  // A kind's presets for a profile: its defaults first (built in), then the user's.
  presetChoices<K extends PresetKind>(kind: K, profileId: string): (Preset<PresetData<K>> & { builtin: boolean })[] {
    const p = this.profiles.find(x => x.id === profileId)
    const own = p ? [{ name: `${p.name} defaults`, data: p.defaults[kind] as PresetData<K>, builtin: true }] : []
    return [...own, ...(this.presets[kind] as Preset<PresetData<K>>[]).map(x => ({ ...x, builtin: false }))]
  }

  get defaultProfile(): Profile | undefined {
    return this.profiles.find(p => p.default) ?? this.profiles[0]
  }

  jobName(id: string | null): string {
    if (!id) return 'VideoForge'
    return this.jobs.find(j => j.id === id)?.name ?? id
  }

  async start(): Promise<void> {
    this.profiles = await api.profiles()
    this.loadEncoders()
    this.loadPresets()
    await this.refreshJobs()
    this.connect()
  }

  async refreshJobs(): Promise<void> {
    const before = new Map(this.jobs.map(j => [j.id, j.status]))
    this.jobs = await api.jobs()
    for (const j of this.jobs) if (before.get(j.id) === 'running' && j.status !== 'running') this.#finished(j)
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

  #bump(id: string): void {
    this.versions[id] = (this.versions[id] ?? 0) + 1
  }

  addLog(line: string, job: string | null = null, step: string | null = null): void {
    this.log.push({ seq: ++this.logSeq, job, step, line })
    if (this.log.length > MAX_LOG) this.log.splice(0, this.log.length - MAX_LOG)
  }

  connect(): void {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/events`)
    this.#socket = ws
    ws.onopen = () => {
      this.connected = true
      this.#retry = 500
      this.#scheduleRefresh()
    }
    ws.onclose = () => {
      this.connected = false
      this.#socket = null
      setTimeout(() => this.connect(), this.#retry)
      this.#retry = Math.min(this.#retry * 2, 8000)
    }
    ws.onmessage = msg => this.#handle(JSON.parse(msg.data))
  }

  #handle(event: { type: string; [k: string]: unknown }): void {
    switch (event.type) {
      case 'hello':
      case 'queue': {
        const { type: _t, ...q } = event
        this.queue = q as unknown as QueueState
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
          if (job.status !== 'running') job.status = 'running'
        }
        break
      }
      case 'log':
        this.addLog(event.line as string, event.id as string, (event.step as string | null) ?? null)
        break
      case 'step': {
        const id = event.id as string
        const index = event.index as number
        const step = event.step as StepRun
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
