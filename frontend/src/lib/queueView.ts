import type { JobSummary, Status } from './types'

export const QUEUE_PAGE_SIZE = 100

/** Preserve queue order; every search word must occur in the name, label or source path. */
export function matchingJobs(jobs: JobSummary[], query: string, status: Status | '' = ''): JobSummary[] {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return jobs.filter((job) => {
    if (status && job.status !== status) return false
    if (!words.length) return true
    const text = `${job.name}\n${job.label}\n${job.source}`.toLocaleLowerCase()
    return words.every((word) => text.includes(word))
  })
}

export function queueRange(ids: string[], from: string, to: string): string[] {
  const a = ids.indexOf(from)
  const b = ids.indexOf(to)
  // An anchor can disappear when the filter or a live status changes.
  if (b < 0) return []
  if (a < 0) return [to]
  return ids.slice(Math.min(a, b), Math.max(a, b) + 1)
}

export function queuePage(count: number, requested: number): number {
  return Math.max(0, Math.min(requested, Math.ceil(count / QUEUE_PAGE_SIZE) - 1))
}

// Whether a job can be queued: queued is locked (read-only), and the queue runs it. Not one still being
// probed, indexed or crop-detected, a blocked one, or one already queued or running.
export function queueable(status: Status): boolean {
  return !['probing', 'error', 'cropping', 'indexing', 'blocked', 'queued', 'running'].includes(status)
}
