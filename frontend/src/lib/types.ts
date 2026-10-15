// Shapes of the VideoForge API (src/videoforge/server/views.py and the core dataclasses).

export type Status =
  | 'probing'
  | 'error'
  | 'cropping'
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

export type AudioAction = 'copy' | 'ddp' | 'atmos' | 'aac' | 'flac' | 'opus' | 'opusenc' | 'aac_ffmpeg' | 'ac3' | 'eac3'

// One audio encode as the server describes it (core.execute.audio.ENCODES).
export interface AudioEncodeInfo {
  id: Exclude<AudioAction, 'copy'>
  label: string
  codec: string
  layouts: string[]
  bitrates: Record<string, number> | null // default kb/s by channels; null = lossless (no bitrate)
  bitrate_choices: number[] // only these, when not empty
  vbr_default: boolean // no bitrate = the encoder's quality VBR
  default_max: string | null
  missing: string[] // tools it lacks ([] = it can run)
  options: EncodeOptionInfo[]
}

// One setting of an encode: a pick list (choices), a whole number (range), or free text.
export interface EncodeOptionInfo {
  key: string
  label: string
  default: string
  help: string
  choices: { value: string; label: string }[]
  range: [number, number] | null
}

export interface TrackOverride {
  exclude: boolean | null
  language: string | null
  title: string | null
  flags: Record<string, boolean>
  // Audio, for profiles with the track editor (null = the profile's choice / the default)
  action: AudioAction | null
  bitrate_kbps: number | null
  layout: string | null // "2.0", "5.1", ...
  options: Record<string, string> // the encode's own settings (AudioEncodeInfo.options keys)
}

export interface Overrides {
  original_language: string | null
  audio_track_ids: number[] | null
  tracks: Record<string, TrackOverride>
  order: string[] | null // track keys in output order (profiles that let the user reorder)
  copies: string[] // more output tracks from an audio track: "<track key>+<n>"
}

export interface JobInputs {
  source: string
  encode: string | null
  subtitles: string[]
  chapters: string | null
  encode_state: string
  audio: string[]
}

export interface JobSpec {
  inputs: JobInputs
  profile: string
  overrides: Overrides
  video: VideoSettings
  encoder: EncoderSettings
  qpf: boolean
  output_dir: string | null
  mux: MuxSettings
  autocrop: boolean // the crop is detected once the source can be read (a template's auto crop)
  audio_template: TemplateAudio | null // a template's audio, waiting for the source's tracks
  subs_template: TemplateSubs | null // ... and its subtitle rules
  id: string
}

// The job's muxer: container ('' = the profile's) and extra arguments for its tool, as typed.
export interface MuxSettings {
  container: string
  extra: string
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
  visual_impaired: boolean // audio description
  commentary: boolean
  original: boolean
  atmos: boolean
  dtsx: boolean
  bitrate_kbps: number | null
  delay_ms: number
  format_name: string
  detected: Record<string, boolean>
  external_path?: string | null // an added audio file (id and index are that file's)
  sample_rate: number | null // Hz
  bit_depth: number | null // lossless only
  size_bytes: number | null
  duration_ms: number | null
  copy: number // 1, 2, ...: another output track from the same source track
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
  visual_impaired: boolean // audio description
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
  visual_impaired: boolean // audio description
  commentary: boolean
  original: boolean
  options: Record<string, string> // the encode's settings, defaults filled in
}

export interface PlannedSub {
  source: Omit<SubTrack, 'key' | 'detected'>
  slot: string // the profile's category; '' when it has none
  language: string
  title: string
  default: boolean
  forced: boolean
  hearing_impaired: boolean
  visual_impaired: boolean // audio description
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
  containers: ContainerInfo[] // the profile's own first; a job may pick any of them
  external_subtitles: boolean
  track_properties: TrackProperty[]
  track_editor: boolean // follows the user's track order, titles and audio encodes
  defaults: { video: VideoSettings; encoder: EncoderSettings; template: Template }
  default: boolean
}

export interface ContainerInfo {
  id: string
  label: string
  extension: string
  tool: string
}

// A user preset (the built-in ones are each profile's defaults). Video presets have no crop.
export type VideoPresetData = Omit<VideoSettings, 'crop'>
export interface Preset<T> {
  name: string
  data: T
}
// A job's whole run (src/videoforge/core/template.py). video.crop is used when crop_mode is 'fixed'.
export type CropMode = 'keep' | 'fixed' | 'auto'
export interface Template {
  video: VideoSettings
  encoder: EncoderSettings
  mux: MuxSettings
  qpf: boolean
  crop_mode: CropMode
  audio: TemplateAudio | null // null: the template leaves each job's audio alone
  subs?: TemplateSubs | null // null (or missing, from before subtitle rules): ... and its subtitles
}
// A template's audio: slot n is for the source's nth audio track (extra slots are ignored); tracks
// past the slots are kept as the profile decides or left out. `extra` = more outputs from the track.
export interface AudioSlot {
  track: TrackOverride
  extra: TrackOverride[]
}
export interface TemplateAudio {
  slots: AudioSlot[]
  others: 'keep' | 'exclude'
}
export type SubFormat = 'srt' | 'pgs' | 'ass' | 'vobsub' | 'tx3g' | 'other'
// A template's subtitles: each track (added files too) takes the first rule it matches (empty
// lists and null = any; forced/SDH/commentary by flag or title); kept tracks go in rule order.
export interface SubRule {
  languages: string[]
  formats: SubFormat[]
  forced: boolean | null
  hearing_impaired: boolean | null
  commentary: boolean | null
  track: TrackOverride // exclude = leave out; title and flags (a default goes to the first track only)
}
export interface TemplateSubs {
  rules: SubRule[]
  others: 'keep' | 'exclude' // tracks no rule matches
}
export interface Presets {
  video: Preset<VideoPresetData>[]
  encoder: Preset<EncoderSettings>[]
  template: Preset<Template>[]
  template_defaults: Record<string, string> // profile id -> its default template's name
}
export type PresetKind = 'video' | 'encoder' | 'template'

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

export interface PathKind {
  path: string
  kind: 'file' | 'folder' | 'missing' | 'outside'
}

export interface CommandStep {
  id: string
  label: string
  command: string
}

// The Settings page (GET/PUT /api/config)
export interface ToolSetting {
  name: string
  label: string
  purpose: string
  folder: boolean
  path: string // in use
  default: string // from videoforge.toml
  custom: string | null // set on the Settings page
}

export interface ConfigState {
  tools: ToolSetting[]
  roots: string[]
  roots_custom: boolean
  default_roots: string[]
  profile: string
  profile_default: string
  profiles: { id: string; name: string }[]
  restart: string[]
}

export type ToolStatus = 'ok' | 'unknown' | 'missing' | 'broken'

export interface ToolCheck {
  name: string
  label: string
  purpose: string
  path: string
  found: string
  status: ToolStatus
  version: string
  detail: string
}

export type StepStatus ='pending' | 'running' | 'done' | 'reused' | 'failed' | 'cancelled'

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
