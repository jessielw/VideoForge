<script lang="ts">
  // A job's frames from the server (VapourSynth): zoom (fit .. 800%, Ctrl+wheel, double-click),
  // drag to pan with a minimap, an edge-detect view for spotting borders, a crop overlay,
  // and frame stepping (←/→ 1, Shift 10, PgUp/PgDn 1 s, Home/End). From the video-forge app.
  // A new frame replaces the old one only once it has decoded, so zoom, scroll and the picture
  // stay put while it loads; a failed load keeps the last frame under an error banner.
  import { api } from '../lib/api'
  import type { Crop } from '../lib/types'
  import Icon from './Icon.svelte'

  let {
    jobId,
    stage,
    frames,
    fps = 24,
    width,
    height,
    version = 0,
    crop = null,
    frame = $bindable(0),
    notice = null,
  }: {
    jobId: string
    stage: 'source' | 'output'
    frames: number
    fps?: number
    width: number
    height: number
    version?: number
    crop?: Crop | null
    frame?: number
    notice?: { text: string; tone: 'muted' | 'bad' } | null
  } = $props()

  const ZOOMS = [0, 25, 50, 75, 100, 150, 200, 300, 400, 600, 800] // 0 = fit
  let zoom = $state(0)
  let src = $state<string | null>(null)
  let loading = $state(false)
  let error = $state('')
  let pictType = $state('')
  let edges = $state(false)
  let edgeSrc = $state<string | null>(null)
  let viewport = $state<HTMLDivElement>()
  let panning = $state(false)
  let showMap = $state(false)
  let mapPos = $state({ left: 0, top: 0, w: 100, h: 100 })
  let frameInput = $state('0')

  let controller: AbortController | null = null
  let mapTimer: ReturnType<typeof setTimeout> | undefined

  async function load(n: number, st: string, v: number) {
    controller?.abort()
    const c = new AbortController()
    controller = c
    loading = true
    try {
      const res = await fetch(api.frameUrl(jobId, n, st as 'source' | 'output', v), { signal: c.signal })
      if (!res.ok) {
        let msg = `${res.status}`
        try {
          msg = (await res.json()).detail ?? msg
        } catch {
          msg = await res.text()
        }
        throw new Error(msg)
      }
      const url = URL.createObjectURL(await res.blob())
      const img = new Image()
      img.src = url
      await img.decode().catch(() => {})
      if (controller !== c) {
        URL.revokeObjectURL(url)
        return
      }
      if (src) URL.revokeObjectURL(src)
      src = url
      pictType = res.headers.get('X-Frame-Type') ?? ''
      error = ''
      if (edges) makeEdges()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') error = (e as Error).message
    } finally {
      if (controller === c) loading = false
    }
  }

  $effect(() => {
    load(frame, stage, version)
  })

  $effect(() => {
    frameInput = String(frame)
  })

  function seek(n: number) {
    frame = Math.max(0, Math.min(frames - 1, Math.round(n)))
  }

  function onkey(e: KeyboardEvent) {
    const step = e.shiftKey ? 10 : 1
    const second = Math.max(1, Math.round(fps))
    const moves: Record<string, number> = {
      ArrowLeft: -step,
      ArrowRight: step,
      PageUp: -second,
      PageDown: second,
    }
    if (e.key in moves) seek(frame + moves[e.key])
    else if (e.key === 'Home') seek(0)
    else if (e.key === 'End') seek(frames - 1)
    else if (e.key === '+' || e.key === '=') zoomBy(1)
    else if (e.key === '-') zoomBy(-1)
    else return
    e.preventDefault()
  }

  function zoomBy(dir: number) {
    const i = ZOOMS.indexOf(zoom)
    zoom = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, (i < 0 ? 0 : i) + dir))]
  }

  function onwheel(e: WheelEvent) {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      zoomBy(e.deltaY > 0 ? -1 : 1)
    } else if (zoom) flashMap()
  }

  function ondblclick() {
    const i = ZOOMS.indexOf(zoom)
    zoom = i < 0 || i === ZOOMS.length - 1 ? 0 : zoom === 0 ? 100 : ZOOMS[i + 1]
  }

  // --- panning + minimap ---
  let drag = { x: 0, y: 0, left: 0, top: 0, id: -1 }

  function onpointerdown(e: PointerEvent) {
    if (!zoom || !viewport || e.button !== 0) return
    // Leave the scrollbars to the browser. Classic ones sit outside the client area and
    // their presses target the viewport itself; overlay ones (Firefox on Windows 11, macOS)
    // sit over the picture, so the strip along each scrolling edge is theirs too.
    if (e.target === viewport) return
    const r = viewport.getBoundingClientRect()
    const x = e.clientX - r.left - viewport.clientLeft
    const y = e.clientY - r.top - viewport.clientTop
    const BAR = 16
    if (x >= viewport.clientWidth - (viewport.scrollHeight > viewport.clientHeight ? BAR : 0)) return
    if (y >= viewport.clientHeight - (viewport.scrollWidth > viewport.clientWidth ? BAR : 0)) return
    viewport.setPointerCapture(e.pointerId)
    drag = { x: e.clientX, y: e.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, id: e.pointerId }
    panning = true
  }

  function onpointermove(e: PointerEvent) {
    if (!panning || !viewport || e.pointerId !== drag.id) return
    viewport.scrollLeft = drag.left + drag.x - e.clientX
    viewport.scrollTop = drag.top + drag.y - e.clientY
    updateMap()
  }

  function onpointerup(e: PointerEvent) {
    if (e.pointerId === drag.id) {
      panning = false
      viewport?.releasePointerCapture(e.pointerId)
    }
  }

  function updateMap() {
    if (!viewport) return
    const { scrollLeft, scrollTop, scrollWidth, scrollHeight, clientWidth, clientHeight } = viewport
    mapPos = {
      left: (scrollLeft / scrollWidth) * 100,
      top: (scrollTop / scrollHeight) * 100,
      w: Math.min(100, (clientWidth / scrollWidth) * 100),
      h: Math.min(100, (clientHeight / scrollHeight) * 100),
    }
  }

  function flashMap() {
    updateMap()
    showMap = true
    clearTimeout(mapTimer)
    mapTimer = setTimeout(() => (showMap = false), 900)
  }

  // --- edge detection (Sobel), to see where the picture really ends ---
  function makeEdges() {
    if (!src) return
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0)
      const { data } = ctx.getImageData(0, 0, img.width, img.height)
      const w = img.width
      const h = img.height
      const gray = new Float32Array(w * h)
      for (let i = 0; i < w * h; i++) gray[i] = data[i * 4] * 0.299 + data[i * 4 + 1] * 0.587 + data[i * 4 + 2] * 0.114
      const out = ctx.createImageData(w, h)
      for (let y = 1; y < h - 1; y++) {
        for (let x = 1; x < w - 1; x++) {
          const i = y * w + x
          const gx = -gray[i - w - 1] + gray[i - w + 1] - 2 * gray[i - 1] + 2 * gray[i + 1] - gray[i + w - 1] + gray[i + w + 1]
          const gy = -gray[i - w - 1] - 2 * gray[i - w] - gray[i - w + 1] + gray[i + w - 1] + 2 * gray[i + w] + gray[i + w + 1]
          const v = 255 - Math.min(255, Math.sqrt(gx * gx + gy * gy) * 2)
          out.data[i * 4] = out.data[i * 4 + 1] = out.data[i * 4 + 2] = v
          out.data[i * 4 + 3] = 255
        }
      }
      ctx.putImageData(out, 0, 0)
      canvas.toBlob(b => {
        if (!b) return
        if (edgeSrc) URL.revokeObjectURL(edgeSrc)
        edgeSrc = URL.createObjectURL(b)
      })
    }
    img.src = src
  }

  function toggleEdges() {
    edges = !edges
    if (edges) makeEdges()
  }

  const shown = $derived(edges && edgeSrc ? edgeSrc : src)
  const pct = (v: number, of: number) => `${(v / of) * 100}%`
  const outW = $derived(crop ? width - crop.left - crop.right : width)
  const outH = $derived(crop ? height - crop.top - crop.bottom : height)
</script>

<div class="flex h-full min-h-0 flex-col gap-2">
  <div class="flex flex-wrap items-center gap-2 text-sm">
    <div class="flex items-center gap-1">
      <button class="btn-ghost px-2" onclick={() => zoomBy(-1)} title="Zoom out (-)"><Icon name="zoomOut" /></button>
      <select class="field" bind:value={zoom}>
        {#each ZOOMS as z (z)}<option value={z}>{z === 0 ? 'Fit' : `${z}%`}</option>{/each}
      </select>
      <button class="btn-ghost px-2" onclick={() => zoomBy(1)} title="Zoom in (+)"><Icon name="zoomIn" /></button>
    </div>
    <button class="btn-ghost {edges ? 'text-accent' : ''}" onclick={toggleEdges} title="Show edges, to judge borders">
      Edges
    </button>
    <span class="ml-auto text-xs text-muted">
      {width}×{height}{crop && stage === 'source' ? ` → ${outW}×${outH}` : ''}
      {#if pictType}· {pictType}-frame{/if}
      {#if loading}· loading…{/if}
    </span>
  </div>

  <div class="relative min-h-0 flex-1">
    <!-- A focusable viewport: arrow keys step frames, the wheel zooms, a drag pans. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div
      bind:this={viewport}
      class="absolute inset-0 overflow-auto border border-line bg-black outline-none focus:border-accent/60
        {zoom ? (panning ? 'cursor-grabbing' : 'cursor-grab') : ''}"
      tabindex="0"
      role="application"
      aria-label="Frame {frame}: arrow keys step, Ctrl+wheel zooms, drag pans"
      onkeydown={onkey}
      {onwheel}
      {ondblclick}
      {onpointerdown}
      {onpointermove}
      {onpointerup}
      onpointercancel={onpointerup}
      onscroll={() => zoom && updateMap()}
    >
      {#if shown}
        <div class={zoom ? 'inline-block align-top' : 'flex h-full w-full items-center justify-center'}>
          <div class="relative {zoom ? '' : 'max-h-full max-w-full'}" style={zoom ? `width:${(width * zoom) / 100}px;height:${(height * zoom) / 100}px` : ''}>
            <img
              src={shown}
              alt="Frame {frame}"
              draggable="false"
              class="block select-none {zoom ? 'h-full w-full' : 'max-h-[calc(100vh-22rem)] max-w-full object-contain'}
                {loading ? 'opacity-80' : ''}"
              style="image-rendering: {zoom >= 200 ? 'pixelated' : 'auto'}"
            />
            {#if crop && stage === 'source'}
              <div class="pointer-events-none absolute inset-0">
                <div class="absolute inset-x-0 top-0 bg-bad/40" style="height:{pct(crop.top, height)}"></div>
                <div class="absolute inset-x-0 bottom-0 bg-bad/40" style="height:{pct(crop.bottom, height)}"></div>
                <div
                  class="absolute left-0 bg-bad/40"
                  style="top:{pct(crop.top, height)};bottom:{pct(crop.bottom, height)};width:{pct(crop.left, width)}"
                ></div>
                <div
                  class="absolute right-0 bg-bad/40"
                  style="top:{pct(crop.top, height)};bottom:{pct(crop.bottom, height)};width:{pct(crop.right, width)}"
                ></div>
                <div
                  class="absolute border border-accent"
                  style="top:{pct(crop.top, height)};bottom:{pct(crop.bottom, height)};left:{pct(crop.left, width)};right:{pct(crop.right, width)}"
                ></div>
              </div>
            {/if}
          </div>
        </div>
      {/if}
    </div>

    {#if !src}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
        {#if error}
          <pre class="max-w-full overflow-auto border border-bad/50 bg-bad/10 p-3 text-xs whitespace-pre-wrap text-bad">{error}</pre>
        {:else if loading}
          <span class="text-muted">Loading the frame (the first one indexes the source, which can take a while)…</span>
        {/if}
      </div>
    {:else if error || notice}
      <!-- Over the kept frame: why it isn't the newest. -->
      <div class="pointer-events-none absolute inset-x-2 top-2 flex flex-col items-start gap-1 text-xs">
        {#if error}
          <pre class="max-h-24 max-w-full overflow-hidden bg-bad px-2 py-1 whitespace-pre-wrap text-white">{error}</pre>
        {/if}
        {#if notice}
          <span class="px-2 py-1 text-white {notice.tone === 'bad' ? 'bg-bad' : 'bg-black/70'}"
            >{notice.text}</span
          >
        {/if}
      </div>
    {/if}

    {#if zoom && (panning || showMap) && shown}
      <div class="pointer-events-none absolute right-3 bottom-3 w-48 overflow-hidden rounded border border-line bg-black/80 shadow-lg">
        <div class="relative">
          <img src={shown} alt="" class="block w-full opacity-70" />
          <div
            class="absolute border-2 border-accent"
            style="left:{mapPos.left}%;top:{mapPos.top}%;width:{mapPos.w}%;height:{mapPos.h}%"
          ></div>
        </div>
      </div>
    {/if}
  </div>

  <div class="flex flex-wrap items-center gap-2">
    <button class="btn-ghost px-2" onclick={() => seek(0)} title="First (Home)"><Icon name="first" /></button>
    <button class="btn-ghost px-2" onclick={() => seek(frame - 1)} title="Previous (←)"><Icon name="left" /></button>
    <input
      type="range"
      class="min-w-16 flex-1 accent-[var(--color-accent)]"
      min="0"
      max={Math.max(0, frames - 1)}
      value={frame}
      onchange={e => seek(+(e.target as HTMLInputElement).value)}
    />
    <button class="btn-ghost px-2" onclick={() => seek(frame + 1)} title="Next (→)"><Icon name="right" /></button>
    <button class="btn-ghost px-2" onclick={() => seek(frames - 1)} title="Last (End)"><Icon name="last" /></button>
    <input
      class="field w-24 text-right font-mono"
      bind:value={frameInput}
      onkeydown={e => e.key === 'Enter' && seek(+frameInput || 0)}
      onblur={() => seek(+frameInput || 0)}
    />
    <span class="w-28 text-xs text-muted">/ {frames - 1} · {(frame / (fps || 24)).toFixed(2)} s</span>
  </div>
</div>
