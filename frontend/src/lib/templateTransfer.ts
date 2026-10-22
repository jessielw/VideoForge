import type { Template, TemplateBundle } from './types'

export const MAX_TEMPLATE_BYTES = 5 * 1024 * 1024

export function templateBundle(templates: { name: string; data: Template }[]): TemplateBundle {
  // Copy only the portable fields, not UI metadata or default profile selections.
  return { format: 'videoforge.templates', version: 1, templates: templates.map(({ name, data }) => ({ name, data })) }
}

export function templateFilename(name: string): string {
  const safe = name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[. ]+$/g, '').slice(0, 80)
  return `${safe || 'templates'}.videoforge.json`
}

export function templateScripts(data: { video: Pick<Template['video'], 'filters' | 'custom'> }): { name: string; script: string }[] {
  const scripts = data.video.filters.filter(f => f.script.trim()).map(f => ({ name: f.name, script: f.script }))
  if (data.video.custom !== null) scripts.unshift({ name: 'Custom script body', script: data.video.custom })
  return scripts
}

export function downloadTemplates(bundle: TemplateBundle, filename: string) {
  const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' })
  if (blob.size > MAX_TEMPLATE_BYTES) throw new Error('The exported file exceeds 5 MiB. Select fewer templates or reduce included scripts.')
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // Give the browser time to begin reading the blob before releasing it.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
