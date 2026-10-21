// Thin typed client for /api. Errors carry the server's `detail` message.
import type {
  ActionSetting,
  AudioEncodeInfo,
  AudioPresetSettings,
  ClipInfo,
  CommandStep,
  DirContents,
  ConfigState,
  Crop,
  DirListing,
  EncoderName,
  EncoderSettings,
  FilterPreset,
  JobDetail,
  JobSpec,
  JobSummary,
  MatchResult,
  NotificationDestination,
  PathKind,
  PresetKind,
  Presets,
  Priority,
  Profile,
  QueueState,
  ReuseJob,
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

export type SpecChanges = Partial<Pick<JobSpec, 'video' | 'encoder' | 'overrides' | 'output_dir' | 'output_policy' | 'qpf' | 'profile' | 'mux' | 'label' | 'output_name'>> & {
  inputs?: InputChanges
  template?: Template // applied first: the whole run's settings
  container?: string // the container alone; the job keeps its extra muxer arguments
}

export const api = {
  health: () => get<{ ok: boolean; version: string }>('/api/health'),
  profiles:() => get<Profile[]>('/api/profiles'),
  presets: () => get<Presets>('/api/presets'),
  filterPresets: () => get<FilterPreset[]>('/api/filter-presets'),
  savePreset: (kind: PresetKind, name: string, data: unknown) =>
    request<Presets>('PUT', `/api/presets/${kind}/${encodeURIComponent(name)}`, data),
  saveEncoderPreset: (preset: { name?: string; label: string; group: string[]; data: EncoderSettings }) =>
    post<Presets>('/api/presets/encoder', preset),
  saveAudioPreset: (preset: { name?: string; label: string; group: string[]; data: AudioPresetSettings }) =>
    post<Presets>('/api/presets/audio', preset),
  deletePreset: (kind: PresetKind, name: string) => request<Presets>('DELETE', `/api/presets/${kind}/${encodeURIComponent(name)}`),
  renamePreset: (kind: PresetKind, name: string, to: string) =>
    post<Presets>(`/api/presets/${kind}/${encodeURIComponent(name)}/rename`, { to }),
  setTemplateDefault: (profile: string, name: string | null) =>
    request<Presets>('PUT', `/api/presets/template-default/${encodeURIComponent(profile)}`, { name }),
  config: () => get<ConfigState>('/api/config'),
  saveConfig: (changes: {
    tools?: Record<string, string | null>
    roots?: string[] | null
    profile?: string | null
    index_waits_for_disk?: boolean
    parallel_audio?: number | null
    delete_work_dir?: boolean | null
    encoder_priority?: Priority | null
    tool_priority?: Priority | null
    notifications?: NotificationDestination[]
    actions?: ActionSetting[]
    disabled_plugins?: string[]
  }) =>
    request<ConfigState>('PUT', '/api/config', changes),
  testNotification: (url: string) => post<{ ok: boolean }>('/api/config/notifications/test', { url }),
  toolChecks: () => get<ToolCheck[]>('/api/config/tools'),
  // a video encoder's option names from its own help ([] when it isn't found)
  videoOptions: (encoder: EncoderName) =>
    get<{ dashes: string; options: { name: string; help: string }[] }>(`/api/config/video-options/${encoder}`),
  encoders: () => get<AudioEncodeInfo[]>('/api/config/encoders'),
  checkTool: (name: string, path: string) => post<ToolCheck>('/api/config/tools/check', { name, path }),
  settings: () => get<{ output_dir: string; last_dir: string }>('/api/settings'),
  saveSettings: (s: { output_dir?: string; last_dir?: string }) => request('PUT', '/api/settings', s),

  shutdown: () => post<{ ok: boolean }>('/api/shutdown'),

  roots: () => get<string[]>('/api/fs/roots'),
  list: (path: string, extensions: string[] = [], programs = false) =>
    get<DirListing>(
      `/api/fs/list?path=${encodeURIComponent(path)}&extensions=${encodeURIComponent(extensions.join(','))}${programs ? '&programs=true' : ''}`,
    ),
  pathKinds: (paths: string[]) => post<PathKind[]>('/api/fs/kinds', { paths }),
  makeDir: (path: string, name: string) => post<{ path: string }>('/api/fs/mkdir', { path, name }),
  dirContents: (path: string) => get<DirContents>(`/api/fs/contents?path=${encodeURIComponent(path)}`),
  removeDir: (path: string, recursive = false) => post<{ path: string }>('/api/fs/rmdir', { path, recursive }),

  match: (slots: InputSlots) => post<MatchResult>('/api/match', slots),
  addJobs: (
    body: InputSlots & {
      original_language: string | null
      replace_existing?: string[]
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
  remove: (ids: string[], workDirs = false) =>
    post<{ removed: string[]; deleted: string[]; kept: Record<string, string> }>('/api/jobs/remove', {
      ids,
      work_dirs: workDirs,
    }),
  removalPreview: (ids: string[]) => post<{ folders: { id: string; path: string; bytes: number | null; error: string }[] }>('/api/jobs/removal-preview', { ids }),
  restore: (ids: string[]) => post<{ restored: string[] }>('/api/jobs/restore', { ids }),
  reorder: (ids: string[]) => post<{ ids: string[] }>('/api/jobs/reorder', { ids }),
  reprobe: (ids: string[]) => post('/api/jobs/reprobe', { ids }),
  log: (id: string) => get<{ lines: string[] }>(`/api/jobs/${id}/log`),
  commands: (id: string) => get<CommandStep[]>(`/api/jobs/${id}/commands`),
  steps: (id: string) => get<StepOutput[]>(`/api/jobs/${id}/steps`),
  logSnapshot: (id: string) => get<{ seq: number; steps: StepOutput[]; lines: string[] }>(`/api/jobs/${id}/log-snapshot`),

  queue: () => get<QueueState>('/api/queue'),
  // reuse: per job, the offered sections to keep (the others are made again); jobs left out reuse as always
  start: (ids?: string[], reuse?: Record<string, string[]>) =>
    post<QueueState>('/api/queue/start', { ...(ids ? { ids } : {}), ...(reuse ? { reuse } : {}) }),
  reuse: (ids?: string[]) => post<{ jobs: ReuseJob[] }>('/api/queue/reuse', ids ? { ids } : {}),
  enqueue: (ids: string[]) => post<QueueState & { enqueued: string[] }>('/api/queue/enqueue', { ids }),
  dequeue: (ids: string[]) => post<QueueState>('/api/queue/dequeue', { ids }),
  stop: () => post<QueueState>('/api/queue/stop'),
  cancel: () => post<QueueState>('/api/queue/cancel'),
  pause: () => post<QueueState>('/api/queue/pause'),
  resume: () => post<QueueState>('/api/queue/resume'),
  // the running job's and the index lane's tools, for the rest of their run; null = the Settings'
  priority: (priority: Priority | null) => post<QueueState>('/api/queue/priority', { priority }),
  index: (ids: string[], first = false) => post<QueueState & { taken: string[] }>('/api/queue/index', { ids, first }),
  stopIndex: (ids?: string[]) => post<QueueState>('/api/queue/index/stop', ids ? { ids } : {}),

  clipInfo: (id: string, stage: 'crop' | 'output') => get<ClipInfo>(`/api/jobs/${id}/video/info?stage=${stage}`),
  frameUrl: (id: string, n: number, stage: 'crop' | 'output', version: number, fmt: 'jpeg' | 'png' = 'jpeg') =>
    `/api/jobs/${id}/video/frame?n=${n}&stage=${stage}&fmt=${fmt}&v=${version}`,
  autocrop: (id: string, samples = 20) => post<Crop>(`/api/jobs/${id}/video/autocrop?samples=${samples}`),
  script: (id: string) => get<ScriptParts>(`/api/jobs/${id}/video/script`),
  checkScript: (id: string) => get<ScriptCheck>(`/api/jobs/${id}/video/check`),
}
