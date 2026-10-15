// Where the video editor was left, per job: what the preview and the side panel show, frame, zoom, scroll, edge view and the
// script editor's text (unsaved edits too). Switching tabs, jobs or pages comes back to it;
// it goes when the job leaves the queue (or the page reloads).
import type { ScriptCheck, ScriptParts } from './types'

export type VideoView = {
  stage: 'source' | 'output' // the preview: the source (crop drawn on it) or the script's output
  panel: 'settings' | 'script' // the side panel: crop, filter, resize, filters; or the script editor
  frame: number
  zoom: number // percent; 0 = fit
  edges: boolean
  scroll: { left: number; top: number }
  parts: ScriptParts | null
  body: string
  checked: ScriptCheck | null
}

const views = new Map<string, VideoView>()

export function videoView(jobId: string): VideoView {
  let v = views.get(jobId)
  if (!v) {
    const fresh = $state<VideoView>({
      stage: 'source',
      panel: 'settings',
      frame: 0,
      zoom: 0,
      edges: false,
      scroll: { left: 0, top: 0 },
      parts: null,
      body: '',
      checked: null,
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
