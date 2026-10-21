import type { StepRun } from './types'

export function mergeSteps(snapshot: StepRun[], live: StepRun[], revisions: Record<string, number>, cursor: number): StepRun[] {
  const byId = new Map(live.filter(Boolean).map(step => [step.id, step]))
  return snapshot.map(step => (revisions[step.id] ?? 0) > cursor ? byId.get(step.id) ?? step : step)
}
