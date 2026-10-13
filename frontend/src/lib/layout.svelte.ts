// Room for the editor: the nav and the queue list collapse to slim rails (remembered in this
// browser), and the Video tab can fill the whole window for a while (Esc puts it back).

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

class Layout {
  #nav = $state(read('videoforge.navCollapsed'))
  #queue = $state(read('videoforge.queueCollapsed'))
  videoExpanded = $state(false)

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
