// Saved output folders (New jobs' Saved menu and Settings › Files & folders): one pinned folder can be the
// default, so unpinning or forgetting it clears the default.
import type { OutputFolder } from './api'

export type Saved = { folders: OutputFolder[]; fallback: string }

// Saves one at a time: each waits for the reply to the one before, so a quick second click builds on the first
// click's list (shown at once) instead of the last reply's. Hands back the reply once no newer save waits, else null.
export function savesInTurn(send: (s: Saved) => Promise<Saved>): (s: Saved) => Promise<Saved | null> {
  let chain: Promise<unknown> = Promise.resolve()
  let waiting = 0
  return (s) => {
    waiting++
    const done = chain.then(() => send(s)).finally(() => waiting--)
    chain = done.catch(() => {})
    return done.then((reply) => (waiting ? null : reply))
  }
}

export function togglePin(folders: OutputFolder[], f: OutputFolder, fallback: string): Saved {
  return {
    folders: folders.map((x) => (x === f ? { ...x, pinned: !x.pinned } : x)),
    fallback: f.pinned && f.path === fallback ? '' : fallback,
  }
}

export function forget(folders: OutputFolder[], f: OutputFolder, fallback: string): Saved {
  return { folders: folders.filter((x) => x !== f), fallback: f.path === fallback ? '' : fallback }
}
