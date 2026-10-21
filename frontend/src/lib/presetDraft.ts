import type { Preset } from './types'

export type PresetChoice<T> = Preset<T> & { builtin: boolean }
export type PresetDraft<T> = { name?: string; label: string; folder: string; data: T }

export const presetKey = <T,>(choice: PresetChoice<T>) => `${choice.builtin}:${choice.name}`
export const presetLabel = <T,>(choice: Preset<T>) => choice.label ?? choice.name
export const folderParts = (folder: string) => folder.trim() ? folder.split('/').map(part => part.trim()) : []

export function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, val) => val && typeof val === 'object' && !Array.isArray(val)
    ? Object.fromEntries(Object.entries(val).sort(([a], [b]) => a.localeCompare(b))) : val)
}

export function draftFromChoice<T>(choice: PresetChoice<T>): PresetDraft<T> {
  return { name: choice.builtin ? undefined : choice.name, label: presetLabel(choice),
    folder: (choice.group ?? []).join(' / '), data: structuredClone(choice.data) }
}

export function newPresetDraft<T>(data: T, folder = ''): PresetDraft<T> {
  return { label: '', folder, data: structuredClone(data) }
}

export function duplicatePresetDraft<T>(draft: PresetDraft<T>, choices: PresetChoice<T>[], parentOf: (data: T) => string): PresetDraft<T> {
  const group = folderParts(draft.folder)
  const names = new Set(choices.filter(c => !c.builtin && parentOf(c.data) === parentOf(draft.data)
    && canonical(c.group ?? []) === canonical(group)).map(presetLabel))
  const base = `${draft.label.trim().slice(0, 65) || 'New preset'} copy`
  let label = base
  for (let i = 2; names.has(label); i++) label = `${base} ${i}`
  return { ...newPresetDraft(draft.data, draft.folder), label }
}

export function matchingPreset<T>(choices: PresetChoice<T>[], data: T, selected?: string | null): PresetChoice<T> | undefined {
  const signature = canonical(data)
  const matches = choices.filter(choice => canonical(choice.data) === signature)
  return matches.find(choice => presetKey(choice) === selected) ?? matches[0]
}

export function saveDestination<T>(draft: PresetDraft<T>, choices: PresetChoice<T>[], parentOf: (data: T) => string) {
  const label = draft.label.trim()
  const group = folderParts(draft.folder)
  const replacement = choices.find(c => !c.builtin && presetLabel(c) === label
    && parentOf(c.data) === parentOf(draft.data) && canonical(c.group ?? []) === canonical(group))
  if (draft.name && replacement && replacement.name !== draft.name) {
    throw new Error('A preset with this name already exists in this folder. Choose another name or folder.')
  }
  return { name: draft.name ?? replacement?.name, label, group, data: structuredClone(draft.data) }
}
