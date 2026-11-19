// The icon for each way a file matched its source. Shapes as well as colours: a hand for the user's match, a
// mortarboard for a pattern they taught before, two ticks for a name match, one for the episode, a hash for a
// numbered set, sparkles for the closest name, a folder for StaxRip's temp folder, a question for a guess and a
// warning for another episode.
import CheckIcon from '@lucide/svelte/icons/check'
import CheckCheckIcon from '@lucide/svelte/icons/check-check'
import CircleQuestionMarkIcon from '@lucide/svelte/icons/circle-question-mark'
import FolderCogIcon from '@lucide/svelte/icons/folder-cog'
import GraduationCapIcon from '@lucide/svelte/icons/graduation-cap'
import HandIcon from '@lucide/svelte/icons/hand'
import HashIcon from '@lucide/svelte/icons/hash'
import SparklesIcon from '@lucide/svelte/icons/sparkles'
import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
import type { SubtitleMatch } from './types'

export const MATCH_ICONS: Record<SubtitleMatch, typeof CheckIcon> = {
  manual: HandIcon,
  learned: GraduationCapIcon,
  name: CheckCheckIcon,
  episode: CheckIcon,
  number: HashIcon,
  similar: SparklesIcon,
  staxrip: FolderCogIcon,
  only_source: CircleQuestionMarkIcon,
  other_episode: TriangleAlertIcon,
}

/** The icon's colour class: red for another episode, green when sure, amber where a person should look. */
export function matchTone(match: SubtitleMatch, sure: boolean, off = false): string {
  if (off) return 'text-muted-foreground/60'
  return match === 'other_episode' ? 'text-destructive' : sure ? 'text-success' : 'text-warning'
}
