// Hash routes: #/new, #/queue, #/queue/<job id>, #/log, #/settings.
export type Page = 'new' | 'queue' | 'log' | 'settings'

const PAGES: Page[] = ['new', 'queue', 'log', 'settings']

class Router {
  page = $state<Page>('new')
  jobId = $state<string | null>(null)

  constructor() {
    this.#read()
    window.addEventListener('hashchange', () => this.#read())
  }

  #read(): void {
    const [, page, id] = location.hash.replace(/^#/, '').split('/')
    this.page = PAGES.includes(page as Page) ? (page as Page) : 'new'
    this.jobId = this.page === 'queue' && id ? decodeURIComponent(id) : null
  }

  go(page: Page, jobId: string | null = null): void {
    location.hash = `#/${page}${jobId ? `/${encodeURIComponent(jobId)}` : ''}`
  }
}

export const router = new Router()
