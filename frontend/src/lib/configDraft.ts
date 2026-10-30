import type { api } from './api'
import type { ConfigState } from './types'

export type ConfigChanges = Parameters<typeof api.saveConfig>[0]

// Keep the next edit based on what the user just entered, including whole-list settings.
export function configDraft(config: ConfigState, changes: ConfigChanges): ConfigState {
  const next = { ...config }
  for (const key of ['notifications', 'actions', 'index_waits_for_disk', 'sample_quality'] as const) {
    if (changes[key] !== undefined) Object.assign(next, { [key]: changes[key] })
  }
  for (const key of ['profile', 'parallel_audio', 'delete_work_dir', 'encoder_priority', 'tool_priority'] as const) {
    if (changes[key] !== undefined) Object.assign(next, { [key]: changes[key] ?? config[`${key}_default`] })
  }
  if (changes.roots !== undefined) {
    next.roots = changes.roots ?? config.default_roots
    next.roots_custom = !!changes.roots?.length
  }
  if (changes.tools)
    next.tools = config.tools.map((tool) => {
      if (!(tool.name in changes.tools!)) return tool
      const custom = changes.tools![tool.name] || null
      return { ...tool, custom, path: custom ?? tool.default }
    })
  if (changes.disabled_plugins) {
    const enabled = <T extends { id: string; enabled: boolean }>(plugin: T): T => ({
      ...plugin,
      enabled: !changes.disabled_plugins!.includes(plugin.id),
    })
    next.plugins = {
      ...config.plugins,
      loaded: config.plugins.loaded.map(enabled),
      disabled: config.plugins.disabled.map(enabled),
    }
  }
  return next
}
