// Room for the editor: the nav and the queue list collapse to slim rails (remembered in this
// browser; a narrow window rails the queue list on its own), and the Video tab can fill the whole
// window for a while (Esc puts it back).

function read(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function write(key: string, on: boolean): void {
  try {
    localStorage.setItem(key, on ? '1' : '0')
  } catch {
    /* storage blocked: it lasts until reload */
  }
}

// Below this width an open job gets the room: the queue list shows as a rail and opens over the editor.
const NARROW = '(max-width: 1439px)'

class Layout {
  #nav = $state(read('videoforge.navCollapsed'))
  #queue = $state(read('videoforge.queueCollapsed'))
  videoExpanded = $state(false)
  narrow = $state(false)
  small = $state(false)

  constructor() {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia(NARROW)
    this.narrow = mq.matches
    mq.addEventListener('change', (e) => (this.narrow = e.matches))
    const small = window.matchMedia('(max-width: 639px)')
    this.small = small.matches
    small.addEventListener('change', (e) => (this.small = e.matches))
  }

  get navCollapsed(): boolean {
    return this.#nav
  }
  set navCollapsed(on: boolean) {
    this.#nav = on
    write('videoforge.navCollapsed', on)
  }

  get queueCollapsed(): boolean {
    return this.#queue
  }
  set queueCollapsed(on: boolean) {
    this.#queue = on
    write('videoforge.queueCollapsed', on)
  }
}

export const layout = new Layout()
