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
  const on = !picked.includes(path)
  return shift && anchor !== null ? pickRange(picked, order, anchor, path, on) : set(picked, [path], on)
}

// Ticks (on) or unticks every path from `from` to `to` in shown order; a dragged press does this from
// the row it started on, over the picks from before the press, so dragging back takes rows out again.
// With either end missing from `order`, it's `to` alone.
export function pickRange(picked: string[], order: string[], from: string, to: string, on: boolean): string[] {
  const a = order.indexOf(from)
  const b = order.indexOf(to)
  return set(picked, a >= 0 && b >= 0 ? order.slice(Math.min(a, b), Math.max(a, b) + 1) : [to], on)
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
