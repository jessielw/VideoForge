// Where the video editor was left, per job: the side panel, the crop lines, frame, zoom, scroll, edge view, the
// script editor's text (unsaved edits too) and the compare. Switching tabs, jobs or pages comes back to it;
// it goes when the job leaves the queue (or the page reloads).
import type { ScriptCheck, ScriptParts } from './types'

export type VideoView = {
  panel: 'settings' | 'script' // the side panel: crop, filter, resize, filters; or the script editor
  cropView: boolean // with Settings: the preview shows the crop lines (the output with its margins back on)
  frame: number
  zoom: number // percent; 0 = fit
  edges: boolean
  scroll: { left: number; top: number }
  parts: ScriptParts | null
  body: string
  checked: ScriptCheck | null
  // Compare the encoder's input with its output: off, a done run's encode, or the test encode (numbered by its own
  // frames: sampleFrame). shows: which side the preview has on (C flips it).
  compare: 'off' | 'encode' | 'sample'
  shows: 'in' | 'out'
  sampleFrame: number
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
      edges: false,
      scroll: { left: 0, top: 0 },
      parts: null,
      body: '',
      checked: null,
      compare: 'off',
      shows: 'out',
      sampleFrame: 0,
    })
    v = fresh
    views.set(jobId, v)
  }
  return v
}

// Drop the views of jobs no longer in the queue.
export function keepVideoViews(jobIds: Iterable<string>): void {
  const keep = new Set(jobIds)
  for (const id of views.keys()) if (!keep.has(id)) views.delete(id)
}
