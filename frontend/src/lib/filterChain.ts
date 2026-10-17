// The video filter chain (VideoSettings.filters): where a built-in filter goes when it's added.
import { FILTER_CATEGORIES, type FilterCategory, type FilterPreset, type FilterStep } from './types'

export const rank = (c: FilterCategory) => FILTER_CATEGORIES.findIndex(x => x.id === c)

// The chain with preset added: in place of the same filter at another strength, else after the last
// step whose category comes at or before its own (so a click puts it where it belongs). Also where it went.
export function addFilter(chain: FilterStep[], preset: FilterPreset, presets: FilterPreset[]): [FilterStep[], number] {
  const step: FilterStep = { category: preset.category, name: preset.name, script: preset.script, enabled: true }
  const family = (s: FilterStep) => presets.find(p => p.name === s.name)?.family
  const same = preset.category === 'custom' ? -1 : chain.findIndex(s => family(s) === preset.family)
  if (same >= 0) return [chain.map((s, i) => (i === same ? step : s)), same]
  const r = rank(preset.category)
  let at = 0
  for (let i = chain.length - 1; i >= 0; i--) {
    if (rank(chain[i].category) <= r) {
      at = i + 1
      break
    }
  }
  return [[...chain.slice(0, at), step, ...chain.slice(at)], at]
}

export function moveStep(chain: FilterStep[], index: number, by: -1 | 1): FilterStep[] {
  const to = index + by
  if (to < 0 || to >= chain.length) return chain
  const out = [...chain]
  ;[out[index], out[to]] = [out[to], out[index]]
  return out
}
