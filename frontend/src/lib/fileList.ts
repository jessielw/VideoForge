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
