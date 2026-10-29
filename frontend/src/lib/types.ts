// Shapes of the VideoForge API (src/videoforge/server/views.py and the core dataclasses).

export type Status =
  | 'probing'
  | 'error'
  | 'cropping'
  | 'indexing' // the index lane is on it
  | 'index-queued' // waiting in the index lane
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
  height: number // with keep_ar, fitted to the job's source and crop (the server fits it on every change)
  kernel: string
  keep_ar: boolean // the height follows the width, keeping the display aspect ratio
  mod: number // both sides a multiple of it
}

export type SourceFilter = 'bestsource' | 'lsmash' | 'ffms2'
// The source filter menu: FFMS2 (the default) first.
export const SOURCE_FILTERS: { id: SourceFilter; label: string; title: string }[] = [
  { id: 'ffms2', label: 'FFMS2', title: 'Quick to index; the default' },
  { id: 'bestsource', label: 'BestSource (exact seeking)', title: 'Frame-exact seeking; the first index decodes the whole video' },
  { id: 'lsmash', label: 'L-SMASH Works', title: 'Quick to index' },
]

// Where a filter goes in the chain, in chain order (core.video.settings.FilterCategory).
export const FILTER_CATEGORIES = [
  { id: 'field', label: 'Field', title: 'IVTC, deinterlacing (before the crop, so it keeps the fields)' },
  { id: 'crop', label: 'Crop', title: '' },
  { id: 'subtitle', label: 'Subtitle', title: 'Burning subtitles in (after the crop)' },
  { id: 'restoration', label: 'Restoration', title: 'Dirty lines, deblocking, dehaloing' },
  { id: 'noise', label: 'Noise', title: 'Denoising' },
  { id: 'line', label: 'Line', title: 'Anti-aliasing, sharpening' },
  { id: 'resize', label: 'Resize', title: '' },
  { id: 'deband', label: 'Deband', title: 'Smoothing banding' },
  { id: 'grain', label: 'Grain', title: 'Adding grain' },
  { id: 'custom', label: 'Custom', title: 'Your own lines' },
] as const
export type FilterCategory = (typeof FILTER_CATEGORIES)[number]['id']

export interface FilterStep {
  category: FilterCategory
  name: string
  script: string // lines on `clip`; empty for the crop and resize steps (made from crop and resize)
  enabled: boolean
}

// A built-in filter (core.video.filters): a family's presets are its variants (strengths, widths).
export interface FilterPreset {
  category: FilterCategory
  family: string // the menu's label
  variant: string // its button ('' for a filter with just the one)
  name: string // the step's name: family and variant
  fill_in: boolean // added with its lines open, to type values in (an Empty variant, Custom)
  script: string
  description: string
}

export interface VideoSettings {
  source_filter: SourceFilter
  crop: Crop
  resize: Resize | null
  filters: FilterStep[] // in order; always one crop and one resize step
  custom: string | null
}

export type EncoderName = 'x264' | 'x265' | 'vp8' | 'vp9' | 'svtav1'
export const ENCODERS: [EncoderName, string][] = [['x264', 'x264'], ['x265', 'x265'], ['vp8', 'VP8'], ['vp9', 'VP9'], ['svtav1', 'SVT-AV1']]
export type RateControl = 'crf' | 'abr' | '2pass'

export interface EncoderSettings {
  encoder: EncoderName
  rate_control: RateControl
  crf: number
  bitrate_kbps: number
  target_mb: number | null // 2-pass: the output's size in MB (decimal), which sets the bitrate instead
  preset: string // VP8 / VP9: ffmpeg's -cpu-used (0 slowest); SVT-AV1: --preset (-1 to 13, 13 fastest)
  tune: string // x264 / x265; SVT-AV1: --tune's number
  depth: number
  options: Record<string, string>
  extra: string
  source_color: boolean // tag the encode with the source's colour description (and HDR10 metadata on x265 / SVT-AV1)
  hdr10plus: boolean // carry a source's HDR10+ metadata into an x265 encode
  dolby_vision: boolean // carry a source's Dolby Vision (as profile 8.1) into an x265 encode
}

// The source's colour description in x264 / x265's names ('' / 0 / null: not given)
export interface VideoColor {
  primaries: string
  transfer: string
  matrix: string
  range: string
  chroma_loc: number | null
  master_display: string
  max_cll: number
  max_fall: number
}

// The source's dynamic HDR metadata beyond HDR10 (0 / '': none)
export interface VideoHdr {
  dv_profile: number // Dolby Vision profile: 5, 7, 8
  dv_compat: number | null // its base layer's compatibility id (7.6 -> 6)
  dv_level: number
  dv_layers: string // 'BL+EL+RPU', 'BL+RPU'
  dv_el: string // a profile 7 enhancement layer: 'FEL' or 'MEL' ('' = none, or not read)
  hdr10plus: boolean
}

export interface Progress {
  step: string
  index: number
  total: number
  fraction: number
  overall: number
  reused: boolean
  fps: number | null // the step's encoder (or vspipe), when it prints one
  eta: number | null // seconds left in the step, by the encoder's own count
  elapsed: number // seconds since the run started
  left: number | null // the job's seconds left, guessed from how fast it went so far
}

export interface JobSummary {
  id: string
  name: string
  label: string // tells jobs on one source apart (spec.label)
  source: string
  profile: string
  status: Status
  progress: Progress | null
  issue: string
  output: string | null
  encoder: string
  crop: Crop | null // null with a custom script body or a reused encode
  custom_script: boolean
  indexed: boolean // the source index is in the work folder: the video opens at once
  index_error: string // the last batch index failed: why
  index_held: boolean // waiting in the index lane while an encode reads its disk
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
  bitrate_range: [number, number] | null
  per_channel_max: number | null
  vbr_default: boolean // no bitrate = the encoder's quality VBR
  default_max: string | null
  missing: string[] // tools it lacks ([] = it can run)
  options: EncodeOptionInfo[]
}

// One setting of an encode: a pick list (choices), a number (range, by step), or free text.
export interface EncodeOptionInfo {
  key: string
  label: string
  default: string
  help: string
  choices: { value: string; label: string }[]
  range: [number, number] | null
  step: number
  when: { key: string; value: string } | null // used (and shown) only while that option has that value
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
  burn?: boolean | null // subtitles: burned into the video instead of muxed (one per job)
  sync_ms?: number | null // audio: + later, - earlier, on top of the track's own delay (applied at the mux)
}

// Reusable compression settings and an optional custom output title.
export type AudioPresetSettings = {
  title?: string | null
  action: AudioAction
  layout: string | null
  bitrate_kbps: number | null
  options: Record<string, string>
}

export interface Overrides {
  original_language: string | null
  audio_track_ids: number[] | null
  tracks: Record<string, TrackOverride>
  order: string[] | null // track keys in output order (profiles that let the user reorder)
  copies: string[] // more output tracks from an audio track: "<track key>+<n>"
}

// What a template set for one kind of track (src/videoforge/core/models.py TemplateChoice).
export interface TemplateChoice {
  tracks: Record<string, TrackOverride> // each track it decided; an empty one = as the profile has it
  copies: string[]
  order: string[] | null
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
  output_policy: 'stop' | 'skip' | 'rename' | 'replace'
  mux: MuxSettings
  autocrop: boolean // the crop is detected once the source can be read (a template's auto crop)
  audio_template: TemplateAudio | null // a template's audio, waiting for the source's tracks
  subs_template: TemplateSubs | null // ... and its subtitle rules
  audio_from_template: TemplateChoice | null // what the last template set for the audio
  subs_from_template: TemplateChoice | null // ... and for the subtitles
  output_name: string // the output's file name without its extension; '' = the profile's (the source's)
  label: string // tells runs of one source apart (e.g. "dubbed"): added to the output name, in the job record
  id: string
}

// The job's muxer: container ('' = the profile's), extra arguments and MKV PGS compression.
export interface MuxSettings {
  container: string
  extra: string
  pgs_zlib: boolean
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
  auto?: TrackAuto
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
  auto?: TrackAuto
}

// A track as the profile has it with no hand edit (track editor profiles): the editor starts from these
// values and saves only what differs. Not kept: the profile's own choice leaves it out.
export interface TrackAuto {
  kept: boolean
  title?: string
  language?: string
  action?: AudioAction // audio only, as are layout and bitrate
  layout?: string
  bitrate_kbps?: number | null
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
  sync_ms?: number // the override's sync correction
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
  burn: Omit<SubTrack, 'key' | 'detected'> | null // the subtitle track burned into the video, not muxed
  issues: Issue[]
  profile: string
}

export interface Tracks {
  video: {
    width: number
    height: number
    start_ms: number
    default_duration_ns: number | null
    sar_num: number // the pixel aspect ratio (not 1:1 on an anamorphic source)
    sar_den: number
    vfr?: boolean // a variable frame rate: an MKV keeps the source's timestamps
    scan_type?: string // MediaInfo's: Progressive, Interlaced, MBAFF, PAFF; absent or '' = not read
    scan_order?: string // TFF, BFF, 2:3 Pulldown, ...
    color: VideoColor
    hdr?: VideoHdr // absent on a job probed before it was read
  } | null
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
  output_name: string | null // the file the run will write (null until planned)
  color_args: string[] | null // the source's colour flags for this encoder (null until probed)
  target: SizeBudget | null // where a 2-pass target size goes (null without one, or until planned)
}

// A target size's bytes: the video gets what the rest leaves (core/video/target.py)
export interface SizeBudget {
  target: number
  seconds: number
  audio: number
  subs: number
  attachments: number
  metadata: number // HDR10+ / Dolby Vision
  overhead: number
  unknown: string[] // tracks whose size isn't known (counted as nothing)
  video: number
  kbps: number
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
  length_warning?: string // the output's length isn't the source's: its audio, subtitles and chapters would be out of step
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
  picks_tracks?: boolean // its own rules pick the tracks: Settings' default subtitle rules don't apply
  defaults: { video: VideoSettings; encoder: EncoderSettings; template: Template }
  default: boolean
}

export interface ContainerInfo {
  id: string
  label: string
  extension: string
  tool: string
}

// A user preset (the built-in ones are each profile's defaults and the encoder starters). Video presets have no crop.
export type VideoPresetData = Omit<VideoSettings, 'crop'>
export interface Preset<T> {
  name: string
  label?: string // encoder presets: display name, independent of storage identity
  group?: string[] // encoder presets: folders within the parent encoder
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
export interface TemplateBundle {
  format: 'videoforge.templates'
  version: 1
  templates: { name: string; data: Template }[]
}
export interface EncoderBundle {
  format: 'videoforge.encoders'
  version: 1
  encoders: { label: string; group: string[]; data: EncoderSettings }[]
}
export interface AudioBundle {
  format: 'videoforge.audio'
  version: 1
  audio: { label: string; group: string[]; data: AudioPresetSettings }[]
}
export interface ConfigurationBundle {
  format: 'videoforge.configuration'
  version: 1 | 2 | 3
  application: Record<string, unknown> & { allow_commands: boolean }
  settings: Record<string, unknown> & { notifications: NotificationDestination[]; actions: ActionSetting[]; disabled_plugins: string[]; plugin_settings?: Record<string, Record<string, unknown>> }
  folders: { output_dir: string; last_dir: string }
  presets: { template: Preset<Template>[]; video: Preset<VideoPresetData>[]; encoder: Preset<EncoderSettings>[]; audio: Preset<AudioPresetSettings>[] }
  template_defaults: Record<string, string>
  subs_default?: TemplateSubs | null // version 3
}
export interface ConfigurationPreview {
  bundle: ConfigurationBundle
  counts: Record<PresetKind, number>
  current_counts: Record<PresetKind, number>
  warnings: string[]
}
export interface PresetPack {
  format: 'videoforge.presets'
  version: 1
  presets: {
    template: { name: string; data: Template }[]
    video: { name: string; data: VideoPresetData }[]
    encoder: { label: string; group: string[]; data: EncoderSettings }[]
    audio: { label: string; group: string[]; data: AudioPresetSettings }[]
  }
}
export interface PresetPackPreview {
  bundle: PresetPack
  names: Record<PresetKind, string[]>
  actions?: Record<PresetKind, ImportAction[]> // absent from a server before replacing imports
}
// What an import does with each entry: adds it, adds a numbered copy (its name is taken and Keep both is on,
// or it's a built-in's name), replaces the saved preset of its name, or leaves that one as it is (the same settings).
export type ImportAction = 'new' | 'copy' | 'replaced' | 'unchanged'
export interface ImportPlan {
  names: string[]
  actions?: ImportAction[]
}
// A template's audio (source tracks only), by position or by rules. Position: slot n is for the
// source's nth audio track (extra slots are ignored). Rules: each track takes the first rule it
// matches (empty lists and null = any; commentary/AD by flag or title); a first_only rule goes to the
// first match only. `others`: tracks past the slots / no rule matches. `extra` = more outputs.
export interface AudioSlot {
  track: TrackOverride
  extra: TrackOverride[]
}
export type AudioCodec = 'aac' | 'ac3' | 'eac3' | 'truehd' | 'dts' | 'dts_hd_ma' | 'dts_hd_hra' | 'lpcm' | 'flac' | 'opus' | 'other'
export interface AudioRule {
  languages: string[]
  original: boolean | null // in the job's original language
  codecs: AudioCodec[]
  min_channels: number | null // channel count: 5.1 = 6
  max_channels: number | null
  commentary: boolean | null
  visual_impaired: boolean | null // audio description
  first_only: boolean
  track: TrackOverride // exclude = leave out
  extra: TrackOverride[]
}
export interface TemplateAudio {
  mode: 'position' | 'rules'
  slots: AudioSlot[]
  rules: AudioRule[]
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
  name_untitled?: boolean // a kept track left untitled is named from its language and flags ("English (SDH)")
}
export interface Presets {
  video: Preset<VideoPresetData>[]
  encoder: Preset<EncoderSettings>[]
  audio: Preset<AudioPresetSettings>[]
  template: Preset<Template>[]
  template_defaults: Record<string, string> // profile id -> its default template's name
  subs_default?: TemplateSubs | null // Settings: subtitle rules for new jobs whose template has none
  encoder_starters: Preset<EncoderSettings>[] // built in for every profile (core/video/starters.py)
}
export type PresetKind = 'video' | 'encoder' | 'audio' | 'template'

// A tool's process priority (a nice value on Linux).
export type Priority = 'idle' | 'below_normal' | 'normal' | 'above_normal' | 'high'

export interface QueueState {
  running: boolean
  current: string | null
  stop_after_current: boolean
  paused: boolean // the running job's tools and the index lane's are suspended
  priority: Priority | null // chosen on the toolbar for the running ones; null = the Settings'
  queued: number
  indexing: string | null // the job the index lane is on
  index_queued: number
}

// A finished file a start could reuse (POST /api/queue/reuse), by section of the job.
export interface ReuseOffer {
  id: string // "video", "audio.2"
  label: string
  file: string
  size: number
  seconds: number // how long it took to make (0 when unknown)
  finished: number | null // epoch seconds
  current: boolean // made with today's settings
  origin: string // another job's folder on the source it's linked from ("" = the job's own)
}

export interface ReuseJob {
  id: string
  name: string
  label: string
  offers: ReuseOffer[]
}

export interface MatchedJob {
  existing_id: string | null
  existing_status: string | null
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

// What deleting a folder takes with it: everything inside, all the way down.
export interface DirContents {
  files: number
  dirs: number
  bytes: number
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
  index_waits_for_disk: boolean // batch indexing holds a job back while an encode reads its disk
  parallel_audio: number // audio encodes at once beside a job's video; 0 = one by one
  parallel_audio_default: number // videoforge.toml's
  delete_work_dir: boolean // delete a done job's <source>_tmp/ (records and log copied to records_dir first)
  delete_work_dir_default: boolean // videoforge.toml's
  encoder_priority: Priority // the video encode's (the encoder and the vspipe feeding it)
  encoder_priority_default: Priority // videoforge.toml's
  tool_priority: Priority // every other tool's
  tool_priority_default: Priority // videoforge.toml's
  priorities: Priority[]
  records_dir: string
  notifications: NotificationDestination[]
  notification_events: { id: NotificationEvent; label: string; default: boolean }[]
  actions: ActionSetting[]
  action_kinds: { id: ActionKind; label: string }[]
  action_tokens: { job: Record<string, string>; queue: Record<string, string> } // {token}: what it stands for
  allow_commands: boolean // videoforge.toml [actions] commands
  plugins: PluginsState
}

export type ActionKind = 'command' | 'move' | 'copy' | 'webhook'

// What runs after a job ends or the queue finishes: target is the command line, the folder or the URL.
export interface ActionSetting {
  name: string
  kind: ActionKind
  target: string
  enabled: boolean
  events: NotificationEvent[]
  overwrite: boolean // move / copy: replace a file already there
}

export interface PluginInfo {
  id: string
  name: string
  version: string
  description: string
  source: string // its folder, or the entry point
  events: string[] // the event types it handles
  enabled: boolean
}

export interface PluginSetting {
  key: string
  label: string
  type: 'text' | 'password' | 'checkbox' | 'integer' | 'choice'
  help: string
  required: boolean
  default: string | boolean | number | null
  choices: string[]
}

export interface ManagedPlugin {
  id: string
  name: string
  version: string
  description: string
  source: string
  settings: PluginSetting[]
  values: Record<string, string | boolean | number>
  configured_passwords: string[]
  removable: boolean
  revision: string
  pending: 'install' | 'replace' | 'remove' | null
  enabled: boolean
  running: boolean
  running_version: string | null
  events: string[]
  error: string | null
}

export interface PluginInventory {
  folder: string
  items: ManagedPlugin[]
  failures: string[]
  management_enabled: boolean
  restart: string[]
}

export interface PluginPreview {
  plugin: { id: string; name: string; version: string; description: string; api_version: number; settings: PluginSetting[] }
  current: { id: string; name: string; version: string } | null
  revision: string
}

export interface PluginsState {
  folder: string
  loaded: PluginInfo[]
  disabled: { id: string; source: string; enabled: boolean }[] // switched off: found, not loaded
  failures: { id: string | null; source: string; reason: string }[]
}

export type NotificationEvent = 'job_done' | 'job_failed' | 'job_cancelled' | 'queue_finished'

// Where job and queue news goes: an Apprise URL and the events it wants.
export interface NotificationDestination {
  name: string
  url: string
  enabled: boolean
  events: NotificationEvent[]
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
