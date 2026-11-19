// What the file browser shows of a folder: the rows the filter keeps, in the chosen order.

// Every word of the filter has to be somewhere in the name, ignoring case: "s01 mkv" keeps Show.S01E01.mkv.
export function filterEntries<T extends { name: string }>(entries: T[], query: string): T[] {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return entries
  return entries.filter((e) => {
    const name = e.name.toLocaleLowerCase()
    return words.every((w) => name.includes(w))
  })
}

export type SortKey = 'name' | 'mtime' | 'size'
export interface FileSort {
  key: SortKey
  desc: boolean
}

// Names compare the way Explorer does: E2 before E10, ignoring case.
const byName = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

// Sorts a copy. Folders have no size, so sorting by size keeps them by name; ties go by name too.
export function sortEntries<T extends { name: string; mtime?: number; size?: number }>(
  entries: T[],
  sort: FileSort,
): T[] {
  const sign = sort.desc ? -1 : 1
  return [...entries].sort((a, b) => {
    const x = sort.key === 'name' ? undefined : a[sort.key]
    const y = sort.key === 'name' ? undefined : b[sort.key]
    if (x !== undefined && y !== undefined && x !== y) return (x - y) * sign
    return byName.compare(a.name, b.name) * (sort.key === 'name' ? sign : 1)
  })
}
