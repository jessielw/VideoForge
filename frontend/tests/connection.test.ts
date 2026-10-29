import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { test } from 'node:test'
import { compileModule } from 'svelte/compiler'
import { transpileModule, ScriptTarget } from 'typescript'

test('startup and reconnect recover catalogs with one bounded retry loop', async () => {
  let offline = true
  let filterCalls = 0
  let socketCount = 0
  const timers = new Map<number, { fn: () => void; delay: number }>()
  let timerId = 0
  class Socket {
    onopen = () => {}
    onclose = () => {}
    constructor() {
      socketCount++
      sockets.push(this)
    }
  }
  const sockets: Socket[] = []
  const read = async () => {
    if (offline) throw new Error('server offline')
    return []
  }
  Object.assign(globalThis, {
    __connectionDeps: {
      api: {
        profiles: read,
        jobs: read,
        presets: read,
        encoders: read,
        filterPresets: async () => {
          filterCalls++
          return read()
        },
        health: async () => ({ version: 'test' }),
      },
      toast: {},
      STATUS_LABEL: {},
      keepVideoViews: () => {},
    },
  })
  const raw = readFileSync(new URL('../src/lib/state.svelte.ts', import.meta.url), 'utf8')
  const source = raw.replace(/^import .* from .*$/gm, '')
  const js = transpileModule(source, { compilerOptions: { target: ScriptTarget.ESNext } }).outputText
  const compiled = compileModule(js, { filename: 'state.svelte.js', generate: 'client' }).js.code
  const runtime = pathToFileURL(createRequire(import.meta.url).resolve('svelte/internal/client')).href
  const code =
    'const { api, toast, STATUS_LABEL, keepVideoViews } = globalThis.__connectionDeps;\n' +
    compiled.replace(/(['"])svelte\/internal\/client\1/g, JSON.stringify(runtime))
  const { app } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
  const previous = { setTimeout, clearTimeout, WebSocket: globalThis.WebSocket }
  Object.assign(globalThis, {
    WebSocket: Socket,
    location: { protocol: 'http:', host: 'localhost' },
    setTimeout: (fn: () => void, delay: number) => {
      timers.set(++timerId, { fn, delay })
      return timerId
    },
    clearTimeout: (id: number) => timers.delete(id),
  })
  try {
    await Promise.all([app.start(), app.start()])
    assert.equal(app.connection, 'offline')
    assert.equal(socketCount, 0)
    assert.equal(timers.size, 1)
    for (let i = 0; i < 6; i++) {
      const timer = [...timers.values()][0]
      assert.ok(timer.delay <= 8000)
      timers.clear()
      timer.fn()
      await app.start()
      assert.equal(timers.size, 1)
    }
    offline = false
    await app.start()
    assert.equal(timers.size, 0)
    assert.equal(socketCount, 1)
    sockets[0].onopen()
    assert.equal(app.connection, 'connected')
    const before = filterCalls
    timers.clear()
    sockets[0].onclose()
    assert.equal(app.connection, 'offline')
    await app.start()
    assert.equal(socketCount, 2)
    assert.equal(filterCalls, before + 1)
    app.stopped = true
    sockets[1].onclose()
    assert.equal(timers.size, 0)
  } finally {
    Object.assign(globalThis, previous)
  }
})
