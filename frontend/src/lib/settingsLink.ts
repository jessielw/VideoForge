// Opening Settings at one category and section from elsewhere (a link beside a setting it decides).
// Settings opens on the category kept under SETTINGS_TAB_KEY, and takes the section once its content is shown.
import { router } from './router.svelte'

export const SETTINGS_TAB_KEY = 'videoforge.settingsTab'

let pendingSection: string | null = null

export function openSettings(tab: string, section: string | null = null): void {
  try {
    localStorage.setItem(SETTINGS_TAB_KEY, tab)
  } catch {
    /* storage blocked: Settings opens on its first category */
  }
  pendingSection = section
  router.go('settings')
}

// The section a link asked for (an element id), once; null when none.
export function takeSettingsSection(): string | null {
  const section = pendingSection
  pendingSection = null
  return section
}
