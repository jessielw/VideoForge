// Ticking paths in the file browser. `order` is the list as shown; ticked paths keep the order they
// were ticked in (that's the order they're added), and new ones go on the end in shown order.

// A click toggles one path. Shift+click sets every path from the last clicked one (the anchor) to this
// one the way this one goes, so it ticks a range or unticks one. Without an anchor in `order`, it's a click.
export function pickClick(
  picked: string[],
  order: string[],
  path: string,
  anchor: string | null,
  shift: boolean,
): string[] {
  const from = shift && anchor !== null ? order.indexOf(anchor) : -1
  const to = order.indexOf(path)
  const range = from >= 0 && to >= 0 ? order.slice(Math.min(from, to), Math.max(from, to) + 1) : [path]
  return set(picked, range, !picked.includes(path))
}

// Ctrl+A or the All box: tick every path in `all`, or untick them all when every one is ticked already.
export function pickAll(picked: string[], all: string[]): string[] {
  const has = new Set(picked)
  return set(picked, all, !all.every((p) => has.has(p)))
}

function set(picked: string[], paths: string[], on: boolean): string[] {
  const has = new Set(picked)
  if (on) return [...picked, ...paths.filter((p) => !has.has(p))]
  const drop = new Set(paths)
  return picked.filter((p) => !drop.has(p))
}
