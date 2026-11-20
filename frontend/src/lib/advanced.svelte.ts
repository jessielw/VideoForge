// Which Advanced sections are open: one switch per area, kept in this browser, closed until opened. The Encoder's
// is one switch for the job's Encoder tab, the preset manager, the template editor and the Queue's multi-job panel.
const KEY = 'videoforge.advanced'

function read(): Record<string, boolean> {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    return v && typeof v === 'object' ? (v as Record<string, boolean>) : {}
  } catch {
    return {} // storage blocked, or not ours
  }
}

export const advancedOpen: Record<string, boolean> = $state(read())

export function setAdvancedOpen(area: string, open: boolean) {
  if (!!advancedOpen[area] === open) return
  advancedOpen[area] = open
  try {
    localStorage.setItem(KEY, JSON.stringify(advancedOpen))
  } catch {
    /* storage blocked */
  }
}
