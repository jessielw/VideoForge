// The reuse question (ReuseDialog, mounted once by the Queue page): asked before jobs with finished files from an
// earlier run are started or queued. A running queue takes a job as soon as it's queued, so Queue asks too.
import { api } from './api'
import type { ReuseJob } from './types'

export type ReuseAnswer = Record<string, string[]>

class ReuseQuestion {
  open = $state(false)
  jobs = $state<ReuseJob[]>([])
  action = $state<'start' | 'queue'>('start')
  #resolve: ((answer: ReuseAnswer | null) => void) | undefined

  /** The answer for the given jobs (none given: the queued ones): {} when nothing could be reused, null when
   *  the user cancelled. */
  async ask(ids: string[] | undefined, action: 'start' | 'queue'): Promise<ReuseAnswer | null> {
    const { jobs } = await api.reuse(ids)
    if (!jobs.length) return {}
    this.#resolve?.(null)
    this.jobs = jobs
    this.action = action
    this.open = true
    return new Promise((resolve) => (this.#resolve = resolve))
  }

  answer(answer: ReuseAnswer | null): void {
    this.open = false
    const resolve = this.#resolve
    this.#resolve = undefined
    resolve?.(answer)
  }
}

export const reuseQuestion = new ReuseQuestion()
