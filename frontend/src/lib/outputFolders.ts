// Saved output folders (New jobs' Saved menu and Settings › Files & folders): one pinned folder can be the
// default, so unpinning or forgetting it clears the default.
import type { OutputFolder } from './api'

type Saved = { folders: OutputFolder[]; fallback: string }

export function togglePin(folders: OutputFolder[], f: OutputFolder, fallback: string): Saved {
  return {
    folders: folders.map((x) => (x === f ? { ...x, pinned: !x.pinned } : x)),
    fallback: f.pinned && f.path === fallback ? '' : fallback,
  }
}

export function forget(folders: OutputFolder[], f: OutputFolder, fallback: string): Saved {
  return { folders: folders.filter((x) => x !== f), fallback: f.path === fallback ? '' : fallback }
}
