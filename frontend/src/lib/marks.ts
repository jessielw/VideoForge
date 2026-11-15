// Frame bookmarks: frames of a job's script marked to come back to (a dark scene, the credits), in the
// script's output frame numbers, sorted. The crop view, the unfiltered output and a done run's encode share
// those numbers; a test encode has its own (its blocks back to back), so marks are mapped to and from it.
// Kept per job in this browser's storage; a job that leaves the queue takes its marks with it (pruneMarks).

const PREFIX = 'videoforge.marks.'

// A test encode's blocks: `length` frames from every `cycle` frames of the script, back to back.
export type Blocks = { length: number; cycle: number }

export function toggleMark(marks: readonly number[], n: number): number[] {
  return marks.includes(n) ? marks.filter((m) => m !== n) : [...marks, n].sort((a, b) => a - b)
}

// The nearest mark after n (or before it), or null at the last (first) one.
export function nextMark(marks: readonly number[], n: number): number | null {
  return marks.find((m) => m > n) ?? null
}

export function prevMark(marks: readonly number[], n: number): number | null {
  return marks.findLast((m) => m < n) ?? null
}

// A test encode's frame n as the script's frame.
export function scriptFrame(n: number, b: Blocks): number {
  return Math.floor(n / b.length) * b.cycle + (n % b.length)
}

// The script's marks a test encode of `frames` frames holds, as its frame numbers.
export function sampleMarks(marks: readonly number[], b: Blocks, frames: number): number[] {
  const out: number[] = []
  for (const m of marks) {
    const off = m % b.cycle
    const n = Math.floor(m / b.cycle) * b.length + off
    if (off < b.length && n < frames) out.push(n)
  }
  return out
}

export function readMarks(jobId: string): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(PREFIX + jobId) ?? '[]')
    return Array.isArray(v) ? v.filter((n) => Number.isInteger(n) && n >= 0).sort((a, b) => a - b) : []
  } catch {
    return [] // storage blocked, or not ours
  }
}

export function writeMarks(jobId: string, marks: readonly number[]): void {
  try {
    if (marks.length) localStorage.setItem(PREFIX + jobId, JSON.stringify(marks))
    else localStorage.removeItem(PREFIX + jobId)
  } catch {
    /* storage blocked: the marks last until the page reloads */
  }
}

// Forget the marks of jobs no longer in the queue.
export function pruneMarks(jobIds: Iterable<string>): void {
  try {
    const keep = new Set([...jobIds].map((id) => PREFIX + id))
    const gone: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k?.startsWith(PREFIX) && !keep.has(k)) gone.push(k)
    }
    for (const k of gone) localStorage.removeItem(k)
  } catch {
    /* storage blocked */
  }
}
