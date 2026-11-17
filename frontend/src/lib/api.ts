// Thin typed client for /api. Errors carry the server's `detail` message.
import type {
  TemplateSubs,
  ActionSetting,
  AudioEncodeInfo,
  AudioBundle,
  AudioPresetSettings,
  ClipInfo,
  CommandStep,
  ConfigState,
  ConfigurationBundle,
  ConfigurationPreview,
  PluginInventory,
  PluginPreview,
  Crop,
  DirListing,
  EncoderName,
  EncoderSettings,
  EncoderBundle,
  FilterPreset,
  NamePolicy,
  NameTokens,
  JobDetail,
  JobSpec,
  JobSummary,
  MatchResult,
  NotificationDestination,
  PathKind,
  PresetKind,
  Presets,
  PresetPack,
  ManagedPresets,
  PresetPackPreview,
  PreviewStage,
  ImportAction,
  ImportPlan,
  Priority,
  ProfileList,
  RuleSet,
  QueueState,
  ReuseJob,
  StepOutput,
  ToolCheck,
  ScriptCheck,
  ScriptParts,
  SearchMetric,
  Template,
  TemplateBundle,
  VideoSettings,
} from './types'

export type OutputFolder = { path: string; pinned: boolean }
export type Settings = {
  output_dir: string
  last_dir: string
  output_folders: OutputFolder[]
  output_default: string
}

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

async function pluginZip<T>(path: string, file: File): Promise<T> {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new ApiError(res.status, error?.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body: unknown = {}) => request<T>('POST', path, body)
// An import keeps a preset of the same name and adds a numbered copy (Keep both), or replaces it.
const keep = (keepBoth: boolean) => (keepBoth ? '?keep_both=true' : '')
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body)

export interface InputSlots {
  sources: string[]
  encodes: string[]
  subtitles: string[]
  chapters: string[]
  rule_set: string
}

// A job's files, each replaced when given (a folder adds its files of that kind).
export interface InputChanges {
  subtitles?: string[]
  audio?: string[]
  chapters?: string | null
  encode?: string | null
}

export type SpecChanges = Partial<
  Pick<
    JobSpec,
    | 'video'
    | 'encoder'
    | 'overrides'
    | 'output_dir'
    | 'output_policy'
    | 'qpf'
    | 'rule_set'
    | 'mux'
    | 'label'
    | 'output_name'
  >
> & {
  inputs?: InputChanges
  template?: Template // applied first: the whole run's settings
  container?: string // the container alone; the job keeps its extra muxer arguments
}

export const api = {
  health: () => get<{ ok: boolean; version: string }>('/api/health'),
  ruleSets: () => get<RuleSet[]>('/api/rule-sets'),
  presets: () => get<Presets>('/api/presets'),
  exportAudio: (bundle: AudioBundle) => post<AudioBundle>('/api/presets/audio/export', bundle),
  previewAudio: (bundle: unknown, keepBoth = false) =>
    post<{ bundle: AudioBundle } & ImportPlan>(`/api/presets/audio/preview${keep(keepBoth)}`, bundle),
  importAudio: (bundle: AudioBundle, keepBoth = false) =>
    post<{ presets: Presets } & ImportPlan>(`/api/presets/audio/import${keep(keepBoth)}`, bundle),
  exportEncoders: (bundle: EncoderBundle) => post<EncoderBundle>('/api/presets/encoders/export', bundle),
  previewEncoders: (bundle: unknown, keepBoth = false) =>
    post<{ bundle: EncoderBundle } & ImportPlan>(`/api/presets/encoders/preview${keep(keepBoth)}`, bundle),
  importEncoders: (bundle: EncoderBundle, keepBoth = false) =>
    post<{ presets: Presets } & ImportPlan>(`/api/presets/encoders/import${keep(keepBoth)}`, bundle),
  exportTemplates: (bundle: TemplateBundle) => post<TemplateBundle>('/api/presets/templates/export', bundle),
  previewTemplates: (bundle: unknown, keepBoth = false) =>
    post<{ bundle: TemplateBundle } & ImportPlan>(`/api/presets/templates/preview${keep(keepBoth)}`, bundle),
  importTemplates: (bundle: TemplateBundle, keepBoth = false) =>
    post<{ presets: Presets } & ImportPlan>(`/api/presets/templates/import${keep(keepBoth)}`, bundle),
  filterPresets: () => get<FilterPreset[]>('/api/filter-presets'),
  nameTokens: () => get<NameTokens>('/api/name-tokens'),
  savePreset: (kind: PresetKind, name: string, data: unknown) =>
    request<Presets>('PUT', `/api/presets/${kind}/${encodeURIComponent(name)}`, data),
  saveEncoderPreset: (preset: { name?: string; label: string; group: string[]; data: EncoderSettings }) =>
    post<Presets>('/api/presets/encoder', preset),
  saveAudioPreset: (preset: { name?: string; label: string; group: string[]; data: AudioPresetSettings }) =>
    post<Presets>('/api/presets/audio', preset),
  deletePreset: (kind: PresetKind, name: string) =>
    request<Presets>('DELETE', `/api/presets/${kind}/${encodeURIComponent(name)}`),
  deletePresets: (kind: PresetKind, names: string[]) => post<Presets>('/api/presets/delete', { kind, names }),
  renamePreset: (kind: PresetKind, name: string, to: string) =>
    post<Presets>(`/api/presets/${kind}/${encodeURIComponent(name)}/rename`, { to }),
  setTemplateDefault: (ruleSet: string, name: string | null) =>
    request<Presets>('PUT', `/api/presets/template-default/${encodeURIComponent(ruleSet)}`, { name }),
  setSubsDefault: (subs: TemplateSubs | null) => request<Presets>('PUT', '/api/presets/subs-default', subs),
  config: () => get<ConfigState>('/api/config'),
  plugins: () => get<PluginInventory>('/api/plugins'),
  previewPlugin: (file: File) => pluginZip<PluginPreview>('/api/plugins/preview', file),
  installPlugin: (file: File, revision: string, replace: boolean) =>
    pluginZip<PluginInventory>(
      `/api/plugins/import?${new URLSearchParams({ revision, replace: String(replace) })}`,
      file,
    ),
  removePlugin: (id: string, revision: string) => post<PluginInventory>('/api/plugins/remove', { id, revision }),
  enablePlugin: (id: string, enabled: boolean) =>
    request<PluginInventory>('PUT', '/api/plugins/enabled', { id, enabled }),
  pluginSettings: (id: string, values: Record<string, unknown>, reset: string[] = []) =>
    request<PluginInventory>('PUT', '/api/plugins/settings', { id, values, reset }),
  exportConfiguration: () => get<ConfigurationBundle>('/api/configuration/export'),
  exportPresetPack: (bundle: PresetPack) => post<PresetPack>('/api/preset-packs/export', bundle),
  managedPresets: () => get<ManagedPresets>('/api/preset-packs/managed'),
  resetManagedPreset: (preset: { plugin: string; kind: PresetKind; key: string }) =>
    post<{ name: string; presets: Presets }>('/api/preset-packs/managed/reset', preset),
  previewPresetPack: (bundle: unknown, keepBoth = false) =>
    post<PresetPackPreview>(`/api/preset-packs/preview${keep(keepBoth)}`, bundle),
  importPresetPack: (bundle: PresetPack, keepBoth = false) =>
    post<{ presets: Presets; names: Record<PresetKind, string[]>; actions: Record<PresetKind, ImportAction[]> }>(
      `/api/preset-packs/import${keep(keepBoth)}`,
      bundle,
    ),
  previewConfiguration: (bundle: unknown) => post<ConfigurationPreview>('/api/configuration/preview', bundle),
  // into: a new profile (its name), or a profile (its id); switch: make it the active one too
  importConfiguration: (bundle: ConfigurationBundle, into: { new: string } | { profile: string }, switchTo: boolean) =>
    post<ProfileList & { config: ConfigState; presets: Presets; warnings: string[]; profile: string }>(
      `/api/configuration/import?${new URLSearchParams({ ...into, switch: String(switchTo) })}`,
      bundle,
    ),
  profiles: () => get<ProfileList>('/api/profiles'),
  // copy: start from the active profile's configuration; else a fresh install's
  createProfile: (name: string, copy: boolean) => post<ProfileList>('/api/profiles', { name, copy }),
  renameProfile: (id: string, name: string) =>
    request<ProfileList>('PATCH', `/api/profiles/${encodeURIComponent(id)}`, { name }),
  deleteProfile: (id: string) => request<ProfileList>('DELETE', `/api/profiles/${encodeURIComponent(id)}`),
  activateProfile: (id: string) =>
    post<ProfileList & { config: ConfigState; presets: Presets }>(`/api/profiles/${encodeURIComponent(id)}/activate`),
  resetConfiguration: (scopes: { settings: boolean; presets: boolean; jobs: boolean }) =>
    post<{ config: ConfigState; presets: Presets; backup: string; removed: string[] }>(
      '/api/configuration/reset',
      scopes,
    ),
  saveConfig: (changes: {
    tools?: Record<string, string | null>
    roots?: string[] | null
    rule_set?: string | null
    index_waits_for_disk?: boolean
    index_during_video?: boolean
    sample_quality?: boolean
    auto_index?: boolean
    auto_crop?: boolean
    naming?: Record<string, NamePolicy>
    parallel_audio?: number | null
    delete_work_dir?: boolean | null
    encoder_priority?: Priority | null
    tool_priority?: Priority | null
    notifications?: NotificationDestination[]
    actions?: ActionSetting[]
    disabled_plugins?: string[]
  }) => request<ConfigState>('PUT', '/api/config', changes),
  testNotification: (url: string) => post<{ ok: boolean }>('/api/config/notifications/test', { url }),
  toolChecks: () => get<ToolCheck[]>('/api/config/tools'),
  // a video encoder's option names from its own help ([] when it isn't found)
  videoOptions: (encoder: EncoderName) =>
    get<{ dashes: string; options: { name: string; help: string }[] }>(`/api/config/video-options/${encoder}`),
  encoders: () => get<AudioEncodeInfo[]>('/api/config/encoders'),
  checkTool: (name: string, path: string) => post<ToolCheck>('/api/config/tools/check', { name, path }),
  settings: () => get<Settings>('/api/settings'),
  saveSettings: (s: Partial<Settings>) => request<Settings>('PUT', '/api/settings', s),

  shutdown: () => post<{ ok: boolean }>('/api/shutdown'),

  roots: () => get<string[]>('/api/fs/roots'),
  list: (path: string, extensions: string[] = [], programs = false) =>
    get<DirListing>(
      `/api/fs/list?path=${encodeURIComponent(path)}&extensions=${encodeURIComponent(extensions.join(','))}${programs ? '&programs=true' : ''}`,
    ),
  pathKinds: (paths: string[]) => post<PathKind[]>('/api/fs/kinds', { paths }),
  makeDir: (path: string, name: string) => post<{ path: string }>('/api/fs/mkdir', { path, name }),
  removeDir: (path: string) => post<{ path: string }>('/api/fs/rmdir', { path }), // empty folders only

  match: (slots: InputSlots) => post<MatchResult>('/api/match', slots),
  addJobs: (
    body: InputSlots & {
      original_language: string | null
      replace_existing?: string[]
      output_dir: string | null
      video?: Partial<VideoSettings>
      encoder?: EncoderSettings
      template?: Template
      /** this batch only; left out, Settings' value applies */
      auto_index?: boolean
      auto_crop?: boolean
    },
  ) =>
    post<{
      added: string[]
      skipped: string[]
      unmatched: string[]
      kept: { source: string; id: string | null; name: string; status: string | null; reason: string }[]
    }>('/api/jobs', body),

  jobs: () => get<JobSummary[]>('/api/jobs'),
  job: (id: string) => get<JobDetail>(`/api/jobs/${id}`),
  update: (id: string, changes: SpecChanges) => patch<JobDetail>(`/api/jobs/${id}`, changes),
  apply: (ids: string[], changes: SpecChanges) =>
    post<{ updated: string[]; skipped: string[] }>('/api/jobs/apply', { ids, ...changes }),
  applyCrop: (ids: string[], crop: Crop) =>
    post<{ updated: string[]; skipped: Record<string, string>; failed: Record<string, string> }>(
      '/api/jobs/apply-crop',
      { ids, crop },
    ),
  remove: (ids: string[], workDirs = false) =>
    post<{ removed: string[]; deleted: string[]; kept: Record<string, string> }>('/api/jobs/remove', {
      ids,
      work_dirs: workDirs,
    }),
  removalPreview: (ids: string[]) =>
    post<{ folders: { id: string; path: string; bytes: number | null; error: string }[] }>(
      '/api/jobs/removal-preview',
      { ids },
    ),
  restore: (ids: string[]) => post<{ restored: string[] }>('/api/jobs/restore', { ids }),
  duplicate: (ids: string[]) => post<{ added: string[] }>('/api/jobs/duplicate', { ids }),
  // a job's file in its folder in the source's work folder; a path is a job file, a job folder or a <source>_tmp folder
  saveJobFiles: (ids: string[]) => post<{ saved: Record<string, string> }>('/api/jobs/save-files', { ids }),
  importJobs: (paths: string[]) =>
    post<{ added: string[]; skipped: { path: string; reason: string }[] }>('/api/jobs/import', { paths }),
  reorder: (ids: string[]) => post<{ ids: string[] }>('/api/jobs/reorder', { ids }),
  reprobe: (ids: string[]) => post('/api/jobs/reprobe', { ids }),
  log: (id: string) => get<{ lines: string[] }>(`/api/jobs/${id}/log`),
  commands: (id: string) => get<CommandStep[]>(`/api/jobs/${id}/commands`),
  // MediaInfo's text report of one of the job's files (no path: the source); parsed on request
  mediainfo: (id: string, path?: string) =>
    get<{ path: string; text: string }>(`/api/jobs/${id}/mediainfo${path ? `?${new URLSearchParams({ path })}` : ''}`),
  steps: (id: string) => get<StepOutput[]>(`/api/jobs/${id}/steps`),
  logSnapshot: (id: string) =>
    get<{ seq: number; steps: StepOutput[]; lines: string[] }>(`/api/jobs/${id}/log-snapshot`),

  queue: () => get<QueueState>('/api/queue'),
  // reuse: per job, the offered sections to keep (the others are made again); jobs left out reuse as always
  start: (ids?: string[], reuse?: Record<string, string[]>) =>
    post<QueueState>('/api/queue/start', { ...(ids ? { ids } : {}), ...(reuse ? { reuse } : {}) }),
  reuse: (ids?: string[]) => post<{ jobs: ReuseJob[] }>('/api/queue/reuse', ids ? { ids } : {}),
  enqueue: (ids: string[], reuse?: Record<string, string[]>) =>
    post<QueueState & { enqueued: string[] }>('/api/queue/enqueue', { ids, ...(reuse ? { reuse } : {}) }),
  dequeue: (ids: string[]) => post<QueueState>('/api/queue/dequeue', { ids }),
  stop: () => post<QueueState>('/api/queue/stop'),
  cancel: () => post<QueueState>('/api/queue/cancel'),
  pause: () => post<QueueState>('/api/queue/pause'),
  // stop the jobs (default: the running one) once the video's pass 1 is done, or take that back; set: the ones it applied to
  pauseAfterPass1: (on: boolean, ids?: string[]) =>
    post<QueueState & { set: string[] }>('/api/queue/pause-after-pass1', { on, ...(ids ? { ids } : {}) }),
  resume: () => post<QueueState>('/api/queue/resume'),
  // the running job's and the index lane's tools, for the rest of their run; null = the Settings'
  priority: (priority: Priority | null) => post<QueueState>('/api/queue/priority', { priority }),
  index: (ids: string[], first = false) => post<QueueState & { taken: string[] }>('/api/queue/index', { ids, first }),
  stopIndex: (ids?: string[]) => post<QueueState>('/api/queue/index/stop', ids ? { ids } : {}),
  // A test encode of percent of the job's video, first in the index lane (stopIndex cancels it)
  sample: (id: string, percent: number) => post<QueueState & { taken: boolean }>('/api/queue/sample', { id, percent }),
  // A CRF search on that test encode: the highest CRF whose metric reaches target
  search: (id: string, percent: number, metric: SearchMetric, target: number) =>
    post<QueueState & { taken: boolean }>('/api/queue/search', { id, percent, metric, target }),

  clipInfo: (id: string, stage: PreviewStage) => get<ClipInfo>(`/api/jobs/${id}/video/info?stage=${stage}`),
  frameUrl: (id: string, n: number, stage: PreviewStage, version: number, fmt: 'jpeg' | 'png' = 'jpeg') =>
    `/api/jobs/${id}/video/frame?n=${n}&stage=${stage}&fmt=${fmt}&v=${version}`,
  // origin: where the crop came from (a Dolby Vision source's RPU L5, or the detected borders)
  autocrop: (id: string, samples = 20) =>
    post<Crop & { origin: string }>(`/api/jobs/${id}/video/autocrop?samples=${samples}`),
  script: (id: string) => get<ScriptParts>(`/api/jobs/${id}/video/script`),
  checkScript: (id: string) => get<ScriptCheck>(`/api/jobs/${id}/video/check`),
}
