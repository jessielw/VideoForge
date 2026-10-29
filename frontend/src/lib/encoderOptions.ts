// A video encoder's option names (from its own help, /api/config/video-options) for the Encoder tab: what an
// option does, and a hint when the encoder doesn't list it (the plan warns too: core/video/options.py).

export type OptionHelp = Map<string, string> // name (no dashes) -> its help line

// The option names the extra arguments set, in order: "--name" (x264 / x265 / SVT-AV1) or "-name" (ffmpeg, with
// any stream specifier dropped: -b:v -> b). Quoted values aren't flags; short flags (-p) aren't checked.
export function extraFlags(extra: string, dashes: string): string[] {
  const words = extra.match(/"[^"]*"|\S+/g) ?? []
  const names = words.flatMap((w) => {
    const flag = w.split('=')[0]
    if (dashes === '-') return /^-[A-Za-z]/.test(flag) ? [flag.slice(1).split(':')[0]] : []
    return flag.startsWith('--') && flag.length > 2 ? [flag.slice(2)] : []
  })
  return [...new Set(names)]
}

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]
    row[0] = i
    for (let j = 1; j <= b.length; j++) {
      const cur = row[j]
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1))
      prev = cur
    }
  }
  return row[b.length]
}

// '' when the encoder lists the name (or no list is loaded); else a warning, with the nearest listed name
export function unknownHint(name: string, known: OptionHelp | null, dashes: string, label: string): string {
  if (!name || !known?.size || known.has(name)) return ''
  let near = ''
  let best = Math.max(2, Math.floor(name.length / 4)) + 1
  for (const k of known.keys()) {
    const d = distance(name, k)
    if (d < best) [near, best] = [k, d]
  }
  return `${label}'s help doesn't list ${dashes}${name}${near ? `: did you mean ${dashes}${near}?` : ''}`
}

// Words as the encoder gets them: split on spaces outside double quotes, the quotes dropped
function words(text: string): string[] {
  const out: string[] = []
  let word = ''
  let quoted = false
  let active = false
  for (const ch of text) {
    if (ch === '"') [quoted, active] = [!quoted, true]
    else if (/\s/.test(ch) && !quoted) {
      if (active) out.push(word)
      word = ''
      active = false
    } else [word, active] = [word + ch, true]
  }
  if (active) out.push(word)
  return out
}

// Typed or pasted options ("--ref 4 --bframes 8 --no-sao", "--psy-rd=2", or a bare "level-idc") as [name, value]
// pairs, a flag's value "" (the options' rows). A first word without dashes is a name. skipped: what can't be a
// row: a value with no option before it, and short flags (-p 5) on an encoder whose options take "--" (for the
// extra arguments). ffmpeg's take one dash; a negative number there is a value.
export function parseOptions(text: string, dashes: string): { pairs: [string, string][]; skipped: string[] } {
  const ws = words(text.trim())
  const pairs: [string, string][] = []
  const skipped: string[] = []
  const isFlag = (w: string) => (dashes === '-' ? /^--?[A-Za-z]/.test(w) : /^-[A-Za-z]|^--[A-Za-z0-9]/.test(w))
  for (let i = 0; i < ws.length; i++) {
    const w = ws[i]
    const named = i === 0 && /^[A-Za-z]/.test(w)
    if (!named && !isFlag(w)) {
      skipped.push(w)
      continue
    }
    let [name, value] = [w.replace(/^-+/, ''), '']
    const eq = name.indexOf('=')
    if (eq > 0) [name, value] = [name.slice(0, eq), name.slice(eq + 1)]
    else if (i + 1 < ws.length && !isFlag(ws[i + 1])) value = ws[++i]
    if (dashes === '--' && /^-[A-Za-z]/.test(w)) skipped.push(value ? `${w} ${value}` : w)
    else if (name) pairs.push([name, value])
  }
  return { pairs, skipped }
}
