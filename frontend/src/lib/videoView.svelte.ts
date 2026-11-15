// Where the video editor was left, per job: the side panel, the crop lines, frame, zoom, scroll, boost view, the
// script editor's text (unsaved edits too), the compare and the frame bookmarks. Switching tabs, jobs or pages
// comes back to it; it goes when the job leaves the queue (or the page reloads), but the bookmarks are kept in
// the browser's storage (lib/marks.ts) until the job leaves the queue.
import { pruneMarks, readMarks } from './marks'
import type { ScriptCheck, ScriptParts } from './types'

export type VideoView = {
  panel: 'settings' | 'script' // the side panel: crop, filter, resize, filters; or the script editor
  cropView: boolean // with Settings: the preview shows the crop lines (the output with its margins back on)
  frame: number
  zoom: number // percent; 0 = fit
  boost: boolean
  scroll: { left: number; top: number }
  parts: ScriptParts | null
  body: string
  checked: ScriptCheck | null
  // Compare two sides of the same frames: off, the encoder's input with a done run's encode or with the test
  // encode (numbered by its own frames: sampleFrame), or the output without its filters with the output.
  // shows: which side the preview has on (C flips it). split: both at once, either side of a line at splitAt
  // (0..1 of the frame's width), the shown side on the left.
  compare: 'off' | 'encode' | 'sample' | 'filters'
  shows: 'in' | 'out'
  sampleFrame: number
  split: boolean
  splitAt: number
  marks: number[] // bookmarked frames, in the script's numbers (lib/marks.ts)
}

const views = new Map<string, VideoView>()

export function videoView(jobId: string): VideoView {
  let v = views.get(jobId)
  if (!v) {
    const fresh = $state<VideoView>({
      panel: 'settings',
      cropView: true,
      frame: 0,
      zoom: 0,
      boost: false,
      scroll: { left: 0, top: 0 },
      parts: null,
      body: '',
      checked: null,
      compare: 'off',
      shows: 'out',
      sampleFrame: 0,
      split: false,
      splitAt: 0.5,
      marks: readMarks(jobId),
    })
    v = fresh
    views.set(jobId, v)
  }
  return v
}

// Drop the views (and the bookmarks) of jobs no longer in the queue.
export function keepVideoViews(jobIds: Iterable<string>): void {
  const keep = new Set(jobIds)
  for (const id of views.keys()) if (!keep.has(id)) views.delete(id)
  pruneMarks(keep)
}
