// Hash routes: #/new, #/queue, #/queue/<job id>, #/templates, #/log, #/settings.
export type Page = 'new' | 'queue' | 'templates' | 'log' | 'settings'

const PAGES: Page[] = ['new', 'queue', 'templates', 'log', 'settings']

class Router {
  page = $state<Page>('new')
  jobId = $state<string | null>(null)
  guard: ((proceed: () => void) => void) | null = null

  constructor() {
    this.#read()
    window.addEventListener('hashchange', () => this.#read())
  }

  #read(): void {
    const [, page, id] = location.hash.replace(/^#/, '').split('/')
    const next = PAGES.includes(page as Page) ? (page as Page) : 'new'
    let jobId: string | null = null
    try {
      jobId = next === 'queue' && id ? decodeURIComponent(id) : null
    } catch {
      /* malformed route */
    }
    if (this.guard && (next !== this.page || jobId !== this.jobId)) {
      history.replaceState(null, '', `#/${this.page}${this.jobId ? `/${encodeURIComponent(this.jobId)}` : ''}`)
      this.go(next, jobId)
    } else {
      this.page = next
      this.jobId = jobId
    }
  }

  go(page: Page, jobId: string | null = null): void {
    if (page === this.page && jobId === this.jobId) return
    if (this.guard) this.guard(() => this.#commit(page, jobId))
    else this.#commit(page, jobId)
  }

  #commit(page: Page, jobId: string | null): void {
    // At once, not on hashchange: until then effects would see the old job (e.g. re-select it).
    this.page = page
    this.jobId = page === 'queue' ? jobId : null
    location.hash = `#/${page}${jobId ? `/${encodeURIComponent(jobId)}` : ''}`
  }
}

export const router = new Router()
