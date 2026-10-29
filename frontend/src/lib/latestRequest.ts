export class LatestRequest {
  private revision = 0
  invalidate() {
    this.revision++
  }

  async run<T>(send: () => Promise<T>): Promise<{ value: T } | { error: string } | null> {
    const revision = ++this.revision
    try {
      const value = await send()
      return revision === this.revision ? { value } : null
    } catch (e) {
      return revision === this.revision ? { error: e instanceof Error ? e.message : String(e) } : null
    }
  }
}
