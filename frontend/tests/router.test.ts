import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { test } from 'node:test'
import { compileModule } from 'svelte/compiler'
import { transpileModule, ScriptTarget } from 'typescript'

test('sidebar and browser-history navigation wait for the template guard; malformed hashes recover', async () => {
  let onHash = () => {}
  const location = { hash: '#/templates' }
  Object.assign(globalThis, {
    location,
    window: { addEventListener: (_: string, callback: () => void) => { onHash = callback } },
    history: { replaceState: (_: unknown, __: string, url: string) => { location.hash = url } },
  })
  const source = readFileSync(new URL('../src/lib/router.svelte.ts', import.meta.url), 'utf8')
  const js = transpileModule(source, { compilerOptions: { target: ScriptTarget.ESNext } }).outputText
  const compiled = compileModule(js, { filename: 'router.svelte.js', generate: 'client' }).js.code
  const runtime = pathToFileURL(createRequire(import.meta.url).resolve('svelte/internal/client')).href
  const code = compiled.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(runtime))
  const { router } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
  let proceed: (() => void) | null = null
  router.guard = (next: () => void) => { proceed = next }
  router.go('new')
  assert.equal(router.page, 'templates')
  assert.ok(proceed)
  ;(proceed as unknown as () => void)()
  assert.equal(router.page, 'new')
  location.hash = '#/queue/job'
  onHash()
  assert.equal(router.page, 'new')
  assert.equal(location.hash, '#/new')
  ;(proceed as unknown as () => void)()
  assert.equal(router.jobId, 'job')
  router.guard = null
  location.hash = '#/queue/%invalid'
  assert.doesNotThrow(onHash)
  assert.equal(router.jobId, null)
})
