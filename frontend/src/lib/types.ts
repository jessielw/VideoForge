// Shapes of the VideoForge API (src/videoforge/server/views.py and the core dataclasses).

export type Status =
  | 'probing'
  | 'error'
  | 'ready'
  | 'warn'
  | 'blocked'
  | 'queued'
  | 'running'
  | 'done'
  | 'invalid'
  | 'failed'
  | 'skipped'
  | 'cancelled'

export interface Crop {
  left: number
  top: number
  right: number
  bottom: number
}

export interface Resize {
  width: number
  height: number
  kernel: string
}

export type SourceFilter = 'bestsource' | 'lsmash' | 'ffms2'

export interface VideoSettings {
  source_filter: SourceFilter
  crop: Crop
  resize: Resize | null
  filters: string
  custom: string | null
}

export type EncoderName = 'x264' | 'x265'
export type RateControl = 'crf' | 'abr' | '2pass'

export interface EncoderSettings {
  encoder: EncoderName
  rate_control: RateControl
  crf: number
  bitrate_kbps: number
  preset: string
  tune: string
  depth: number
  options: Record<string, string>
  extra: string
}

export interface Progress {
  step: string
  index: number
  total: number
  fraction: number
  overall: number
  reused: boolean
}

export interface JobSummary {
  id: string
  name: string
  source: string
  profile: string
  status: Status
  progress: Progress | null
  issue: string
  output: string | null
  encoder: string
  crop: Crop
  audio: string[]
  subs: number
}

export type Severity = 'info' | 'warn' | 'block'

export interface Issue {
  severity: Severity
  code: string
  message: string
}

export type AudioAction = 'copy' | 'ddp' | 'atmos' | 'aac'

export interface TrackOverride {
  exclude: boolean | null
  language: string | null
  title: string | null
  flags: Record<string, boolean>
  // Audio, for profiles with the track editor (null = the profile's choice / the default)
  action: AudioAction | null
  bitrate_kbps: number | null
  layout: string | null // "2.0", "5.1", ...
}

export interface Overrides {
  original_language: string | null
  audio_track_ids: number[] | null
  tracks: Record<string, TrackOverride>
  order: string[] | null // track keys in output order (profiles that let the user reorder)
}

export interface JobInputs {
  source: string
  encode: string | null
  subtitles: string[]
  chapters: string | null
  encode_state: string
}

export interface JobSpec {
  inputs: JobInputs
  profile: string
  overrides: Overrides
  video: VideoSettings
  encoder: EncoderSettings
  qpf: boolean
  output_dir: string | null
  id: string
}

export interface AudioTrack {
  key: string
  id: number
  index: number
  codec: string
  layout: string
  language: string
  title: string
  default: boolean
  forced: boolean
  hearing_impaired: boolean
  commentary: boolean
  original: boolean
  atmos: boolean
  dtsx: boolean
  bitrate_kbps: number | null
  delay_ms: number
  format_name: string
  detected: Record<string, boolean>
}

export interface SubTrack {
  key: string
  id: number
  index: number
  format: string
  language: string
  title: string
  default: boolean
  forced: boolean
  hearing_impaired: boolean
  commentary: boolean
  original: boolean
  element_count: number | null
  external_path: string | null
  detected: Record<string, boolean>
}

export interface PlannedAudio {
  source: Omit<AudioTrack, 'key' | 'detected'>
  action: string
  out_codec: string
  out_layout: string
  out_atmos: boolean
  bitrate_kbps: number | null
  upmix_50: boolean
  language: string
  title: string
  default: boolean
  forced: boolean
  hearing_impaired: boolean
  commentary: boolean
  original: boolean
}

export interface PlannedSub {
  source: Omit<SubTrack, 'key' | 'detected'>
  slot: string // the profile's category; '' when it has none
  language: string
  title: string
  default: boolean
  forced: boolean
  hearing_impaired: boolean
  commentary: boolean
  original: boolean
}

export interface Plan {
  encode_path: string | null
  resolution: string // a profile's size class ("1080p") or a plain size ("1920x1080")
  original_language: string
  chapters_path: string | null
  audio: PlannedAudio[]
  subs: PlannedSub[]
  issues: Issue[]
  profile: string
}

export interface Tracks {
  video: { width: number; height: number; start_ms: number; default_duration_ns: number | null } | null
  audio: AudioTrack[]
  subs: SubTrack[]
  has_chapters: boolean
  count: number
}

export interface StepRecord {
  id: string
  fingerprint: string
  outputs: string[]
  seconds: number
}

export interface JobDetail extends JobSummary {
  spec: JobSpec
  issues: Issue[]
  steps: Record<string, StepRecord>
  plan: Plan | null
  tracks: Tracks | null
}

export interface ClipInfo {
  frames: number
  width: number
  height: number
  fps_num: number
  fps_den: number
  format: string
  bits: number
  fps: number
}

// The job's script: head and tail are generated, body is the editable part (line numbers run head -> tail).
export interface ScriptParts {
  script: string
  head: string[]
  body: string[]
  tail: string[]
  custom: boolean
}

export type ScriptCheck = { ok: true; info: ClipInfo } | { ok: false; error: string; line: number | null }

export interface TrackProperty {
  key: string
  label: string
  kind: 'audio' | 'sub'
  help: string
}

export interface Profile {
  id: string
  name: string
  container: string
  external_subtitles: boolean
  track_properties: TrackProperty[]
  track_editor: boolean // follows the user's track order, titles and audio encodes
  defaults: { video: VideoSettings; encoder: EncoderSettings }
  default: boolean
}

export interface QueueState {
  running: boolean
  current: string | null
  stop_after_current: boolean
  queued: number
}

export interface MatchedJob {
  source: string
  encode: string | null
  subtitles: string[]
  chapters: string | null
  encode_state: string
}

export interface MatchResult {
  jobs: MatchedJob[]
  unmatched: string[]
}

export interface DirListing {
  path: string
  parent: string | null
  dirs: { name: string; path: string }[]
  files: { name: string; path: string; size: number; mtime: number }[]
}

export interface CommandStep {
  id: string
  label: string
  command: string
}

export type StepStatus = 'pending' | 'running' | 'done' | 'reused' | 'failed' | 'cancelled'

// One step of a job's last run (GET /jobs/<id>/steps adds its output lines).
export interface StepRun {
  id: string
  label: string
  command: string // '' = runs inside VideoForge
  status: StepStatus
  exit_code: number | null
  seconds: number
  error: string
}

export interface StepOutput extends StepRun {
  lines: string[]
  partial: boolean // only the saved tail is left (after a restart)
}
