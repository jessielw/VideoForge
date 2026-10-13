// App-wide state, kept current by the server's event WebSocket (/api/events).
import { api } from './api'
import type { JobSummary, Profile, QueueState } from './types'

const MAX_LOG = 20000

export interface LogLine {
  job: string | null // job id; null for app messages
  line: string
}

class AppState {
  jobs = $state<JobSummary[]>([])
  queue = $state<QueueState>({ running: false, current: null, stop_after_current: false, queued: 0 })
  profiles = $state<Profile[]>([])
  log = $state<LogLine[]>([])
  connected = $state(false)
  // Bumped per job whenever the server says it changed; open editors refetch on it.
  versions = $state<Record<string, number>>({})

  #socket: WebSocket | null = null
  #refreshTimer: ReturnType<typeof setTimeout> | null = null
  #retry = 500

  get defaultProfile(): Profile | undefined {
    return this.profiles.find(p => p.default) ?? this.profiles[0]
  }

  jobName(id: string | null): string {
    if (!id) return 'VideoForge'
    return this.jobs.find(j => j.id === id)?.name ?? id
  }

  async start(): Promise<void> {
    this.profiles = await api.profiles()
    await this.refreshJobs()
    this.connect()
  }

  async refreshJobs(): Promise<void> {
    this.jobs = await api.jobs()
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

  addLog(line: string, job: string | null = null): void {
    this.log.push({ job, line })
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
        this.addLog(event.line as string, event.id as string)
        break
    }
  }
}

export const app = new AppState()
