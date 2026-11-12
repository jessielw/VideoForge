// A desktop notification from this browser when the queue finishes, while the page isn't in front (in front,
// each job's own toast says it). Chosen per browser, as the permission is the browser's: remembered here.
// Browsers allow it on https and on localhost only, so a server reached over plain http on the LAN can't.
import { duration, STATUS_LABEL } from './format'
import type { Status } from './types'

const KEY = 'videoforge.desktopNotify'

export type QueueFinished = { statuses: Status[]; seconds: number; left: number }

function readOn(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

class BrowserNotify {
  readonly supported = typeof Notification !== 'undefined' && window.isSecureContext
  on = $state(readOn())
  permission = $state<NotificationPermission>(typeof Notification === 'undefined' ? 'denied' : Notification.permission)

  /** Turning it on asks the browser for permission (it must follow a click); it stays off when refused. */
  async set(on: boolean): Promise<void> {
    if (on && this.supported && Notification.permission === 'default') {
      this.permission = await Notification.requestPermission()
    }
    this.on = on && this.permission === 'granted'
    try {
      localStorage.setItem(KEY, this.on ? '1' : '0')
    } catch {
      /* storage blocked: the choice lasts until reload */
    }
  }

  queueFinished(e: QueueFinished): void {
    if (!this.on || !this.supported || Notification.permission !== 'granted' || !document.hidden) return
    const { title, body } = queueMessage(e)
    const n = new Notification(title, { body, icon: '/favicon.png', tag: 'videoforge-queue' })
    n.onclick = () => {
      window.focus()
      n.close()
    }
  }
}

/** "Queue finished" / "Queue stopped", and "3 jobs: 2 done, 1 failed · took 1h 05m · 2 still queued". */
export function queueMessage({ statuses, seconds, left }: QueueFinished): { title: string; body: string } {
  const counts = new Map<Status, number>()
  for (const s of statuses) counts.set(s, (counts.get(s) ?? 0) + 1)
  const parts = [...counts].map(([s, n]) => `${n} ${STATUS_LABEL[s]?.toLowerCase() ?? s}`)
  const jobs = `${statuses.length} job${statuses.length === 1 ? '' : 's'}`
  const body = [`${jobs}: ${parts.join(', ')}`, `took ${duration(seconds)}`, left ? `${left} still queued` : '']
  return { title: left ? 'Queue stopped' : 'Queue finished', body: body.filter(Boolean).join(' · ') }
}

export const browserNotify = new BrowserNotify()
