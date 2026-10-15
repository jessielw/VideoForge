// Thin typed client for /api. Errors carry the server's `detail` message.
import type {
  AudioEncodeInfo,
  ClipInfo,
  CommandStep,
  ConfigState,
  Crop,
  DirListing,
  EncoderSettings,
  JobDetail,
  JobSpec,
  JobSummary,
  MatchResult,
  PathKind,
  PresetKind,
  Presets,
  Profile,
  QueueState,
  StepOutput,
  ToolCheck,
  ScriptCheck,
  ScriptParts,
  Template,
  VideoSettings,
} from './types'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (data?.detail) message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message)
  }
  return (await res.json()) as T
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body: unknown = {}) => request<T>('POST', path, body)
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body)

export interface InputSlots {
  sources: string[]
  encodes: string[]
  subtitles: string[]
  chapters: string[]
  profile: string
}

// A job's files, each replaced when given (a folder adds its files of that kind).
export interface InputChanges {
  subtitles?: string[]
  audio?: string[]
  chapters?: string | null
  encode?: string | null
}

export type SpecChanges = Partial<Pick<JobSpec, 'video' | 'encoder' | 'overrides' | 'output_dir' | 'qpf' | 'profile' | 'mux'>> & {
  inputs?: InputChanges
  template?: Template // applied first: the whole run's settings
  container?: string // the container alone; the job keeps its extra muxer arguments
}

export const api = {
  profiles: () => get<Profile[]>('/api/profiles'),
  presets: () => get<Presets>('/api/presets'),
  savePreset: (kind: PresetKind, name: string, data: unknown) =>
    request<Presets>('PUT', `/api/presets/${kind}/${encodeURIComponent(name)}`, data),
  deletePreset: (kind: PresetKind, name: string) => request<Presets>('DELETE', `/api/presets/${kind}/${encodeURIComponent(name)}`),
  renamePreset: (kind: PresetKind, name: string, to: string) =>
    post<Presets>(`/api/presets/${kind}/${encodeURIComponent(name)}/rename`, { to }),
  setTemplateDefault: (profile: string, name: string | null) =>
    request<Presets>('PUT', `/api/presets/template-default/${encodeURIComponent(profile)}`, { name }),
  config: () => get<ConfigState>('/api/config'),
  saveConfig: (changes: { tools?: Record<string, string | null>; roots?: string[] | null; profile?: string | null }) =>
    request<ConfigState>('PUT', '/api/config', changes),
  toolChecks: () => get<ToolCheck[]>('/api/config/tools'),
  encoders: () => get<AudioEncodeInfo[]>('/api/config/encoders'),
  checkTool: (name: string, path: string) => post<ToolCheck>('/api/config/tools/check', { name, path }),
  settings: () => get<{ output_dir: string; last_dir: string }>('/api/settings'),
  saveSettings: (s: { output_dir?: string; last_dir?: string }) => request('PUT', '/api/settings', s),

  shutdown: () => post<{ ok: boolean }>('/api/shutdown'),

  roots: () => get<string[]>('/api/fs/roots'),
  list: (path: string, extensions: string[] = []) =>
    get<DirListing>(`/api/fs/list?path=${encodeURIComponent(path)}&extensions=${encodeURIComponent(extensions.join(','))}`),
  pathKinds: (paths: string[]) => post<PathKind[]>('/api/fs/kinds', { paths }),

  match: (slots: InputSlots) => post<MatchResult>('/api/match', slots),
  addJobs: (
    body: InputSlots & {
      original_language: string | null
      output_dir: string | null
      video?: Partial<VideoSettings>
      encoder?: EncoderSettings
      template?: Template
    },
  ) =>
    post<{ added: string[]; skipped: string[]; unmatched: string[] }>('/api/jobs', body),

  jobs: () => get<JobSummary[]>('/api/jobs'),
  job: (id: string) => get<JobDetail>(`/api/jobs/${id}`),
  update: (id: string, changes: SpecChanges) => patch<JobDetail>(`/api/jobs/${id}`, changes),
  apply: (ids: string[], changes: SpecChanges) =>
    post<{ updated: string[]; skipped: string[] }>('/api/jobs/apply', { ids, ...changes }),
  remove: (ids: string[]) => post<{ removed: string[] }>('/api/jobs/remove', { ids }),
  reorder: (ids: string[]) => post<{ ids: string[] }>('/api/jobs/reorder', { ids }),
  reprobe: (ids: string[]) => post('/api/jobs/reprobe', { ids }),
  log: (id: string) => get<{ lines: string[] }>(`/api/jobs/${id}/log`),
  commands: (id: string) => get<CommandStep[]>(`/api/jobs/${id}/commands`),
  steps: (id: string) => get<StepOutput[]>(`/api/jobs/${id}/steps`),

  queue: () => get<QueueState>('/api/queue'),
  start: (ids?: string[]) => post<QueueState>('/api/queue/start', ids ? { ids } : {}),
  enqueue: (ids: string[]) => post<QueueState & { enqueued: string[] }>('/api/queue/enqueue', { ids }),
  dequeue: (ids: string[]) => post<QueueState>('/api/queue/dequeue', { ids }),
  stop: () => post<QueueState>('/api/queue/stop'),
  cancel: () => post<QueueState>('/api/queue/cancel'),
  index: (ids: string[], first = false) => post<QueueState & { taken: string[] }>('/api/queue/index', { ids, first }),
  stopIndex: (ids?: string[]) => post<QueueState>('/api/queue/index/stop', ids ? { ids } : {}),

  clipInfo: (id: string, stage: 'source' | 'output') => get<ClipInfo>(`/api/jobs/${id}/video/info?stage=${stage}`),
  frameUrl: (id: string, n: number, stage: 'source' | 'output', version: number, fmt: 'jpeg' | 'png' = 'jpeg') =>
    `/api/jobs/${id}/video/frame?n=${n}&stage=${stage}&fmt=${fmt}&v=${version}`,
  autocrop: (id: string, samples = 20) => post<Crop>(`/api/jobs/${id}/video/autocrop?samples=${samples}`),
  script: (id: string) => get<ScriptParts>(`/api/jobs/${id}/video/script`),
  checkScript: (id: string) => get<ScriptCheck>(`/api/jobs/${id}/video/check`),
}
