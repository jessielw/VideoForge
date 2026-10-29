// Writes survive editor unmounts. A failed write pauses later edits until retry or discard.
export class SaveQueue {
  private items: { send: () => Promise<unknown>; resolve: (value: any) => void; reject: (error: Error) => void }[] = []
  private running: Promise<void> | null = null
  private flushers = new Set<() => void>()
  private listeners = new Set<(error: string) => void>()
  error = ''

  subscribe(listener: (error: string) => void) {
    this.listeners.add(listener)
    listener(this.error)
    return () => {
      this.listeners.delete(listener)
    }
  }

  private report(error: string) {
    this.error = error
    for (const listener of this.listeners) listener(error)
  }

  register(flush: () => void) {
    this.flushers.add(flush)
    return () => {
      flush()
      this.flushers.delete(flush)
    }
  }

  add<T>(send: () => Promise<T>): Promise<T> {
    const result = new Promise<T>((resolve, reject) => this.items.push({ send, resolve, reject }))
    this.pump()
    return result
  }

  private pump() {
    if (this.running || this.error || !this.items.length) return
    this.running = (async () => {
      while (this.items.length) {
        const item = this.items[0]
        try {
          const result = await item.send()
          this.items.shift()
          item.resolve(result)
        } catch (e) {
          this.report(e instanceof Error ? e.message : String(e))
          break
        }
      }
    })().finally(() => {
      this.running = null
      this.pump()
    })
  }

  async flush() {
    for (const flush of this.flushers) flush()
    do {
      this.pump()
      if (this.running) await this.running
      if (this.error)
        throw new Error(`Changes are not saved: ${this.error}. Retry or discard unsaved changes before starting.`)
    } while (this.items.length)
  }

  async retry() {
    if (this.running) await this.running
    this.report('')
    await this.flush()
  }

  discard() {
    // Only offered after a failure, when no request is in flight.
    if (!this.error) return
    for (const item of this.items.splice(0)) item.reject(new Error('Unsaved changes discarded'))
    this.report('')
  }
}

export const saves = new SaveQueue()
