import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { ConfigState, ManagedPlugin, PluginInventory } from '../../src/lib/types.ts'

async function fixture(page: Page, options: { installed?: boolean; enabled?: boolean; id?: string } = {}) {
  const errors: string[] = []
  const calls: { path: string; body: unknown }[] = []
  page.on('pageerror', error => errors.push(error.message))
  const plugin: ManagedPlugin = {
    id: options.id ?? 'example', name: 'Library scan', version: '1.0', description: 'Scan after encoding.', source: 'plugins/example',
    settings: [
      { key: 'url', label: 'Server URL', type: 'text', help: 'Your library server.', required: true, default: 'http://localhost', choices: [] },
      { key: 'token', label: 'API key', type: 'password', help: '', required: true, default: null, choices: [] },
      { key: 'enabled', label: 'Scan enabled', type: 'checkbox', help: '', required: false, default: true, choices: [] },
      { key: 'count', label: 'Retry count', type: 'integer', help: '', required: false, default: 2, choices: [] },
      { key: 'when', label: 'Scan after', type: 'choice', help: '', required: false, default: 'queue', choices: ['job', 'queue'] },
    ],
    values: { url: 'http://localhost', enabled: true, count: 2, when: 'queue' }, configured_passwords: ['token'],
    removable: true, revision: 'current-revision', pending: null, enabled: true, running: true,
    running_version: '1.0', events: ['JobFinished', 'QueueFinished'], error: null,
  }
  const inventory: PluginInventory = { folder: 'plugins', items: options.installed ? [plugin] : [], failures: [], management_enabled: options.enabled ?? true, restart: [] }
  const config: ConfigState = {
    tools: [], roots: [], roots_custom: false, default_roots: [], profile: 'manual', profile_default: 'manual', profiles: [], restart: [],
    index_waits_for_disk: true, parallel_audio: 2, parallel_audio_default: 2, delete_work_dir: false, delete_work_dir_default: false,
    encoder_priority: 'normal', encoder_priority_default: 'normal', tool_priority: 'normal', tool_priority_default: 'normal', priorities: ['normal'],
    records_dir: 'records', notifications: [], notification_events: [], actions: [], action_kinds: [], action_tokens: { job: {}, queue: {} }, allow_commands: false,
    plugins: { folder: 'plugins', loaded: [], disabled: [], failures: [] },
  }
  await page.routeWebSocket('**/api/events', () => {})
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url()), path = url.pathname
    if (path === '/api/plugins/preview') {
      expect(request.headers()['content-type']).toBe('application/zip')
      await route.fulfill({ json: { plugin: { ...plugin, version: '2.0', api_version: 1 }, current: inventory.items.length ? { ...plugin } : null, revision: inventory.items.length ? plugin.revision : 'absent' } })
      return
    }
    if (path === '/api/plugins/import') {
      calls.push({ path, body: { revision: url.searchParams.get('revision'), replace: url.searchParams.get('replace') } })
      inventory.items = [{ ...plugin, version: '2.0', running: !!options.installed, pending: options.installed ? 'replace' : 'install' }]
      inventory.restart = config.restart = ['Plugin changes take effect when VideoForge starts again.']
      await route.fulfill({ json: inventory })
      return
    }
    if (['/api/plugins/enabled', '/api/plugins/settings', '/api/plugins/remove'].includes(path) && request.method() !== 'GET') {
      const body = request.postDataJSON()
      expect(body.id).toBe(plugin.id)
      calls.push({ path, body })
      if (path.endsWith('/remove')) inventory.items[0].pending = 'remove'
      else if (path.endsWith('/enabled')) inventory.items[0].enabled = body.enabled
      else inventory.items[0].values = { ...inventory.items[0].values, ...body.values }
      inventory.restart = config.restart = ['Plugin changes take effect when VideoForge starts again.']
      await route.fulfill({ json: inventory })
      return
    }
    const responses: Record<string, unknown> = {
      '/api/jobs': [], '/api/profiles': [], '/api/health': { ok: true, version: 'test' },
      '/api/presets': { video: [], encoder: [], audio: [], template: [], template_defaults: {}, encoder_starters: [] },
      '/api/filter-presets': [], '/api/config/encoders': [], '/api/config/video-options/x264': { dashes: '--', options: [] },
      '/api/config': config, '/api/config/tools': [], '/api/plugins': inventory,
    }
    if (!(path in responses)) throw new Error(`Unexpected plugin request: ${request.method()} ${path}`)
    await route.fulfill({ json: responses[path] })
  })
  await page.goto('/#/settings')
  await expect(page.getByRole('button', { name: 'Install ZIP' })).toBeVisible()
  return { plugin, inventory, config, calls, errors }
}

async function chooseZip(page: Page) {
  await page.getByRole('button', { name: 'Install ZIP' }).click()
  const dialog = page.getByRole('dialog', { name: 'Install plugin' })
  await dialog.locator('input[type=file]').setInputFiles({ name: 'example.zip', mimeType: 'application/zip', buffer: Buffer.from('zip-upload') })
  await expect(dialog.getByText('example · Plugin API 1')).toBeVisible()
  return dialog
}

test('preview requires trust, stages install, configures settings and displays running state after restart', async ({ page }, testInfo) => {
  const { inventory, calls, errors } = await fixture(page)
  const dialog = await chooseZip(page)
  await expect(dialog.getByRole('button', { name: 'Install on restart' })).toBeDisabled()
  expect(calls).toEqual([])
  await dialog.getByRole('checkbox', { name: 'I trust this plugin' }).check()
  await dialog.getByRole('button', { name: 'Install on restart' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText(/Install pending restart/)).toBeVisible()
  expect(calls[0]).toEqual({ path: '/api/plugins/import', body: { revision: 'absent', replace: 'false' } })
  await page.getByText('Details and settings', { exact: true }).click()
  await page.getByRole('button', { name: 'Configure Library scan' }).click()
  const settings = page.getByRole('dialog', { name: 'Configure Library scan' })
  await expect(settings.getByLabel('API key')).toHaveValue('')
  await expect(settings.getByLabel('API key')).toHaveAttribute('placeholder', 'Stored password (unchanged)')
  await settings.getByLabel('Server URL').fill('http://library')
  await settings.getByLabel('Retry count').fill('3')
  await settings.getByLabel('Scan after').selectOption('job')
  await settings.getByRole('button', { name: 'Save settings' }).click()
  expect(calls.at(-1)).toEqual({ path: '/api/plugins/settings', body: { id: 'example', values: { url: 'http://library', count: 3, when: 'job' }, reset: [] } })
  inventory.items[0] = { ...inventory.items[0], pending: null, running: true, running_version: '2.0' }
  await page.reload()
  await expect(page.getByText(/Running 2.0/)).toBeVisible()
  await page.getByRole('region', { name: 'Plugin manager' }).screenshot({ path: testInfo.outputPath('plugins.png') })
  expect(errors).toEqual([])
})

test('replacement shows both versions; disabling and removal remain pending until restart', async ({ page }) => {
  const { calls, errors } = await fixture(page, { installed: true })
  const manager = page.getByRole('region', { name: 'Plugin manager' })
  await manager.getByRole('checkbox', { name: 'Enabled', exact: true }).uncheck()
  await expect(manager.getByText(/Disabled on next start/)).toBeVisible()
  expect(calls[0]).toEqual({ path: '/api/plugins/enabled', body: { id: 'example', enabled: false } })
  const dialog = await chooseZip(page)
  await expect(dialog.getByText('Replace installed version 1.0 with 2.0.', { exact: false })).toBeVisible()
  await dialog.getByRole('checkbox', { name: 'I trust this plugin' }).check()
  await dialog.getByRole('button', { name: 'Replace on restart' }).click()
  await expect(manager.getByText(/Replacement pending restart/)).toBeVisible()
  expect(calls.at(-1)).toEqual({ path: '/api/plugins/import', body: { revision: 'current-revision', replace: 'true' } })
  expect(errors).toEqual([])
})

test('removal confirms preserved data and disabled management exposes no active controls', async ({ page }) => {
  const { calls, errors } = await fixture(page, { installed: true })
  await page.getByText('Details and settings', { exact: true }).click()
  await page.getByRole('button', { name: 'Remove Library scan' }).click()
  const dialog = page.getByRole('dialog', { name: 'Remove Library scan?' })
  await expect(dialog.getByText(/Saved settings and plugin data will be kept/)).toBeVisible()
  await dialog.getByRole('button', { name: 'Remove on restart' }).click()
  await expect(page.getByText(/Removal pending restart/)).toBeVisible()
  expect(calls.at(-1)?.path).toBe('/api/plugins/remove')
  expect(errors).toEqual([])
})

test('plugin section is accessible and remote management can be disabled', async ({ page }) => {
  const { errors } = await fixture(page, { installed: true, enabled: false })
  await expect(page.getByRole('button', { name: 'Install ZIP' })).toBeDisabled()
  const manager = page.getByRole('region', { name: 'Plugin manager' })
  await expect(manager.getByRole('checkbox', { name: 'Enabled' })).toBeDisabled()
  const report = await new AxeBuilder({ page }).include('[aria-label="Plugin manager"]').analyze()
  expect(report.violations).toEqual([])
  expect(errors).toEqual([])
})

test('event logger controls work when privacy filters block its name in request URLs', async ({ page }) => {
  const { calls, errors } = await fixture(page, { installed: true, id: 'event_logger' })
  const blocked: string[] = []
  // EasyPrivacy's /event_logger rule aborts the request before it reaches the local API.
  await page.route('**/*event_logger*', async route => {
    blocked.push(route.request().url())
    await route.abort('blockedbyclient')
  })
  const manager = page.getByRole('region', { name: 'Plugin manager' })
  const enabled = manager.getByRole('checkbox', { name: 'Enabled', exact: true })
  await enabled.uncheck()
  await expect(manager.getByText(/Disabled on next start/)).toBeVisible()
  await enabled.check()
  await expect(manager.getByText(/Enabled on next start/)).toBeVisible()
  expect(calls.slice(0, 2)).toEqual([
    { path: '/api/plugins/enabled', body: { id: 'event_logger', enabled: false } },
    { path: '/api/plugins/enabled', body: { id: 'event_logger', enabled: true } },
  ])
  await manager.getByText('Details and settings', { exact: true }).click()
  await manager.getByRole('button', { name: 'Configure Library scan' }).click()
  const settings = page.getByRole('dialog', { name: 'Configure Library scan' })
  await settings.getByLabel('Server URL').fill('http://library')
  await settings.getByRole('button', { name: 'Save settings' }).click()
  await expect(settings).not.toBeVisible()
  expect(calls.at(-1)?.body).toEqual({ id: 'event_logger', values: { url: 'http://library' }, reset: [] })
  await manager.getByRole('button', { name: 'Remove Library scan' }).click()
  await page.getByRole('dialog', { name: 'Remove Library scan?' }).getByRole('button', { name: 'Remove on restart' }).click()
  await expect(manager.getByText(/Removal pending restart/)).toBeVisible()
  expect(calls.at(-1)).toEqual({ path: '/api/plugins/remove', body: { id: 'event_logger', revision: 'current-revision' } })
  expect(blocked).toEqual([])
  await expect(manager.getByRole('alert')).toHaveCount(0)
  expect(errors).toEqual([])
})
