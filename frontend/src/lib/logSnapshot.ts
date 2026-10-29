import type { StepRun } from './types'

export function mergeSteps(
  snapshot: StepRun[],
  live: StepRun[],
  revisions: Record<string, number>,
  cursor: number,
): StepRun[] {
  const byId = new Map(live.filter(Boolean).map((step) => [step.id, step]))
  const merged = snapshot.map((step) => ((revisions[step.id] ?? 0) > cursor ? (byId.get(step.id) ?? step) : step))
  const seen = new Set(snapshot.map((step) => step.id))
  return [...merged, ...live.filter((step) => step && !seen.has(step.id) && (revisions[step.id] ?? 0) > cursor)]
}
