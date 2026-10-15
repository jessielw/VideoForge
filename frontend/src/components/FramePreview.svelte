<script lang="ts">
  // A job's frames from the server (VapourSynth, lossless PNG): zoom (fit .. 800%, Ctrl+wheel and
  // double-click zoom at the pointer), drag to pan with a minimap, an edge-detect view for spotting
  // borders, a crop overlay, and frame stepping (←/→ 1, Shift 10, PgUp/PgDn 1 s, Home/End).
  // With `oncrop` the crop is edited on the Source frame: the wheel moves the crop line nearest the
  // pointer 2 px a notch (that side is marked), a drag on a line moves it (snapped to 2); then
  // Shift+wheel scrolls a zoomed view and a drag anywhere else still pans.
  // The frame sits on a matte (gray, black or white) with a margin all round, so every edge pixel
  // can be scrolled into view clear of the scrollbars and told apart from the background.
  // A new frame replaces the old one only once it has decoded, so zoom, scroll and the picture
  // stay put while it loads (a spinner shows over it when a load takes a moment); a failed load
  // keeps the last frame under an error banner. Zoom, edges and scroll are bindable so the caller
  // can bring a view back as it was left.
  import { tick, untrack } from 'svelte'
  import { api } from '../lib/api'
  import type { Crop } from '../lib/types'
  import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left'
  import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
  import ChevronsLeftIcon from '@lucide/svelte/icons/chevrons-left'
  import ChevronsRightIcon from '@lucide/svelte/icons/chevrons-right'
  import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
  import ZoomInIcon from '@lucide/svelte/icons/zoom-in'
  import ZoomOutIcon from '@lucide/svelte/icons/zoom-out'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { Slider } from '$lib/components/ui/slider'
  import { Toggle } from '$lib/components/ui/toggle'

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
    zoom = $bindable(0),
    edges = $bindable(false),
    scroll = $bindable({ left: 0, top: 0 }),
    notice = null,
    onstage,
    oncrop,
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
    zoom?: number // percent; 0 = fit
    edges?: boolean
    scroll?: { left: number; top: number }
    notice?: { text: string; tone: 'muted' | 'bad' } | null
    onstage?: (stage: 'source' | 'output') => void // keys 1 and 2, at the same frame
    oncrop?: (crop: Crop) => void // set: the wheel and the crop lines edit the crop (Source only)
  } = $props()

  const ZOOMS = [25, 50, 75, 100, 150, 200, 300, 400, 600, 800]
  const PAD = 24 // matte margin around the frame, px
  const MATTES = { gray: '#404040', black: '#000000', white: '#ffffff' } as const
  type Matte = keyof typeof MATTES
  let vw = $state(0) // the viewport's client size
  let vh = $state(0)
  let frameEl = $state<HTMLDivElement>()
  let matte = $state<Matte>(readMatte())
  let src = $state<string | null>(null)
  let loading = $state(false)
  let slow = $state(false) // a load past a short delay: show the spinner (quick steps don't flash it)
  let error = $state('')
  let pictType = $state('')
  let edgeSrc = $state<string | null>(null)
  let viewport = $state<HTMLDivElement>()
  let panning = $state(false)
  let showMap = $state(false)
  let mapPos = $state({ left: 0, top: 0, w: 100, h: 100 })
  let frameInput = $state('0')
  let scrub = $state(0) // the slider's position while dragging; the frame changes on release

  let controller: AbortController | null = null
  let mapTimer: ReturnType<typeof setTimeout> | undefined

  async function load(n: number, st: string, v: number) {
    controller?.abort()
    const c = new AbortController()
    controller = c
    loading = true
    const spin = setTimeout(() => controller === c && (slow = true), 250)
    try {
      const res = await fetch(api.frameUrl(jobId, n, st as 'source' | 'output', v, 'png'), { signal: c.signal })
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
      clearTimeout(spin)
      if (controller === c) loading = slow = false
    }
  }

  $effect(() => {
    load(frame, stage, version)
  })

  $effect(() => {
    frameInput = String(frame)
    scrub = frame
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
    else if (onstage && (e.key === '1' || e.key === '2')) onstage(e.key === '1' ? 'source' : 'output')
    else return
    e.preventDefault()
  }

  // Back to the scroll position the view was left at (zoom and edges come back through their props).
  let restored = false
  $effect(() => {
    const v = viewport
    if (v && !restored) {
      restored = true
      untrack(() => {
        v.scrollLeft = scroll.left
        v.scrollTop = scroll.top
      })
    }
  })

  function onscroll() {
    if (!viewport) return
    scroll = { left: viewport.scrollLeft, top: viewport.scrollTop }
    if (pannable) updateMap()
  }

  // --- zoom ---
  $effect(() => {
    const v = viewport
    if (!v) return
    const ro = new ResizeObserver(() => {
      vw = v.clientWidth
      vh = v.clientHeight
    })
    ro.observe(v)
    return () => ro.disconnect()
  })

  const fitScale = $derived(vw && vh ? Math.max(0.01, Math.min((vw - 2 * PAD) / width, (vh - 2 * PAD) / height)) : 1)
  const scale = $derived(zoom ? zoom / 100 : fitScale)
  const dispW = $derived(Math.floor(width * scale))
  const dispH = $derived(Math.floor(height * scale))
  const pannable = $derived(dispW + 2 * PAD > vw + 1 || dispH + 2 * PAD > vh + 1)

  // Change the zoom keeping the frame point under (cx, cy) (client coordinates; default the
  // viewport's centre) where it is.
  async function setZoom(z: number, cx?: number, cy?: number) {
    if (z === zoom) return
    if (!viewport || !frameEl) {
      zoom = z
      return
    }
    const r = viewport.getBoundingClientRect()
    const x = cx === undefined ? viewport.clientWidth / 2 : cx - r.left - viewport.clientLeft
    const y = cy === undefined ? viewport.clientHeight / 2 : cy - r.top - viewport.clientTop
    const before = scale
    const fx = (viewport.scrollLeft + x - frameEl.offsetLeft) / before
    const fy = (viewport.scrollTop + y - frameEl.offsetTop) / before
    zoom = z
    await tick()
    viewport.scrollLeft = fx * scale + frameEl.offsetLeft - x
    viewport.scrollTop = fy * scale + frameEl.offsetTop - y
    updateMap()
  }

  // One step in or out; zooming out past the fit size lands on Fit.
  function zoomBy(dir: number, cx?: number, cy?: number) {
    const cur = scale * 100
    if (dir > 0) {
      const next = ZOOMS.find(z => z > cur + 0.5)
      if (next) setZoom(next, cx, cy)
    } else if (zoom) {
      const next = [...ZOOMS].reverse().find(z => z < cur - 0.5)
      setZoom(next && next > fitScale * 100 + 0.5 ? next : 0, cx, cy)
    }
  }

  function onwheel(e: WheelEvent) {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      zoomBy(e.deltaY > 0 ? -1 : 1, e.clientX, e.clientY)
    } else if (cropping && e.shiftKey) {
      // Chromium turns Shift+wheel sideways; here it scrolls the way the wheel turns.
      e.preventDefault()
      if (viewport) viewport.scrollTop += (e.deltaY || e.deltaX) * (e.deltaMode === 1 ? 40 : 1)
      if (pannable) flashMap()
    } else if (cropping && e.deltaY) {
      e.preventDefault()
      wheelCrop(e)
    } else if (pannable) flashMap()
  }

  // Fit <-> a close look (100%, or more when the fit is already that big) at the pointer.
  function ondblclick(e: MouseEvent) {
    if (zoom) setZoom(0)
    else setZoom(ZOOMS.find(z => z >= 100 && z > fitScale * 100 + 1) ?? ZOOMS[ZOOMS.length - 1], e.clientX, e.clientY)
  }

  function readMatte(): Matte {
    try {
      const m = localStorage.getItem('videoforge.matte')
      if (m && m in MATTES) return m as Matte
    } catch {
      /* storage blocked */
    }
    return 'gray'
  }

  function nextMatte() {
    const keys = Object.keys(MATTES) as Matte[]
    matte = keys[(keys.indexOf(matte) + 1) % keys.length]
    try {
      localStorage.setItem('videoforge.matte', matte)
    } catch {
      /* storage blocked */
    }
  }

  // --- crop editing ---
  const MIN_OUT = 16 // the smallest picture a crop may leave, px
  const HIT = 6 // how close to a crop line (screen px) a press grabs it
  const OPPOSITE = { left: 'right', right: 'left', top: 'bottom', bottom: 'top' } as const
  const cropping = $derived(!!oncrop && !!crop && stage === 'source')
  let armed = $state<keyof Crop | null>(null) // the side the wheel moves: the line nearest the pointer
  let onLine = $state(false) // the pointer is on that line, so a press drags it
  let cropDrag = $state<{ side: keyof Crop; id: number } | null>(null)
  let wheelRest = 0 // touchpads scroll in small steps; they add up to a notch

  // The pointer in source pixels (off the frame on the matte too) and one screen px in source px.
  function framePoint(e: MouseEvent) {
    const r = frameEl!.getBoundingClientRect()
    return { x: ((e.clientX - r.left) / r.width) * width, y: ((e.clientY - r.top) / r.height) * height, px: width / r.width }
  }

  function nearestLine(e: MouseEvent) {
    const { x, y, px } = framePoint(e)
    const c = crop!
    const d = { left: x - c.left, right: width - c.right - x, top: y - c.top, bottom: height - c.bottom - y }
    const side = (Object.keys(d) as (keyof Crop)[]).reduce((a, b) => (Math.abs(d[b]) < Math.abs(d[a]) ? b : a))
    return { side, near: Math.abs(d[side]) / px <= HIT }
  }

  // Even, and never past the opposite side (MIN_OUT left between them).
  function setSide(side: keyof Crop, v: number) {
    const c = crop!
    const max = Math.floor(((side === 'left' || side === 'right' ? width : height) - c[OPPOSITE[side]] - MIN_OUT) / 2) * 2
    v = Math.max(0, Math.min(max, Math.round(v / 2) * 2))
    if (v !== c[side]) oncrop!({ ...c, [side]: v })
  }

  // The top and bottom lines follow the wheel (down moves them down); down crops the left and right in.
  function wheelCrop(e: WheelEvent) {
    const { side } = nearestLine(e)
    armed = side
    let d = e.deltaY * (e.deltaMode === 1 ? 40 : 1)
    if (Math.abs(d) < 50) {
      wheelRest += d
      if (Math.abs(wheelRest) < 50) return
      d = wheelRest
    }
    wheelRest = 0
    setSide(side, crop![side] + 2 * Math.sign(d) * (side === 'bottom' ? -1 : 1))
  }

  function trackLine(e: PointerEvent) {
    if (!cropping || !frameEl) return
    if (cropDrag) {
      const { x, y } = framePoint(e)
      const s = cropDrag.side
      setSide(s, s === 'left' ? x : s === 'right' ? width - x : s === 'top' ? y : height - y)
    } else if (!panning) {
      const n = nearestLine(e)
      armed = n.side
      onLine = n.near
    }
  }

  function onpointerleave() {
    if (!cropDrag) {
      armed = null
      onLine = false
    }
  }

  const cursor = $derived.by(() => {
    const side = cropDrag?.side ?? (cropping && onLine ? armed : null)
    if (side) return side === 'left' || side === 'right' ? 'cursor-ew-resize' : 'cursor-ns-resize'
    return pannable ? (panning ? 'cursor-grabbing' : 'cursor-grab') : ''
  })

  // --- panning + minimap ---
  let drag = { x: 0, y: 0, left: 0, top: 0, id: -1 }

  function onpointerdown(e: PointerEvent) {
    if (!viewport || e.button !== 0) return
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
    if (cropping && onLine && armed) {
      viewport.setPointerCapture(e.pointerId)
      cropDrag = { side: armed, id: e.pointerId }
      return
    }
    if (!pannable) return
    viewport.setPointerCapture(e.pointerId)
    drag = { x: e.clientX, y: e.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, id: e.pointerId }
    panning = true
  }

  function onpointermove(e: PointerEvent) {
    trackLine(e)
    if (!panning || !viewport || e.pointerId !== drag.id) return
    viewport.scrollLeft = drag.left + drag.x - e.clientX
    viewport.scrollTop = drag.top + drag.y - e.clientY
    updateMap()
  }

  function onpointerup(e: PointerEvent) {
    if (cropDrag && e.pointerId === cropDrag.id) {
      cropDrag = null
      viewport?.releasePointerCapture(e.pointerId)
    }
    if (e.pointerId === drag.id) {
      panning = false
      viewport?.releasePointerCapture(e.pointerId)
    }
  }

  // The visible part of the frame, in % of the frame (the matte margin left out).
  function updateMap() {
    if (!viewport || !frameEl || !dispW || !dispH) return
    const left = Math.max(0, viewport.scrollLeft - frameEl.offsetLeft)
    const top = Math.max(0, viewport.scrollTop - frameEl.offsetTop)
    const right = Math.min(dispW, viewport.scrollLeft + viewport.clientWidth - frameEl.offsetLeft)
    const bottom = Math.min(dispH, viewport.scrollTop + viewport.clientHeight - frameEl.offsetTop)
    mapPos = {
      left: (left / dispW) * 100,
      top: (top / dispH) * 100,
      w: (Math.max(0, right - left) / dispW) * 100,
      h: (Math.max(0, bottom - top) / dispH) * 100,
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
      <Button variant="ghost" size="icon" onclick={() => zoomBy(-1)} title="Zoom out (-)" aria-label="Zoom out"><ZoomOutIcon /></Button>
      <NativeSelect value={zoom} aria-label="Zoom" onchange={e => setZoom(+e.currentTarget.value)}>
        <option value={0}>Fit ({Math.round(fitScale * 100)}%)</option>
        {#each ZOOMS as z (z)}<option value={z}>{z}%</option>{/each}
      </NativeSelect>
      <Button variant="ghost" size="icon" onclick={() => zoomBy(1)} title="Zoom in (+)" aria-label="Zoom in"><ZoomInIcon /></Button>
    </div>
    <Toggle pressed={edges} onPressedChange={toggleEdges} class="data-[state=on]:bg-primary/15 data-[state=on]:text-primary" title="Show edges, to judge borders">
      Edges
    </Toggle>
    <Button variant="ghost" onclick={nextMatte} title="Background around the frame: {matte} (click to change)">
      <span class="inline-block size-3.5 border" style="background:{MATTES[matte]}"></span>Matte
    </Button>
    <span class="ml-auto text-xs whitespace-nowrap text-muted-foreground tabular-nums">
      {width}×{height}{crop && stage === 'source' ? ` → ${outW}×${outH}` : ''} · {Math.round(scale * 100)}%
      {#if pictType}· {pictType}-frame{/if}
    </span>
  </div>

  <div class="relative min-h-0 flex-1">
    <!-- A focusable viewport: arrow keys step frames, the wheel zooms, a drag pans. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div
      bind:this={viewport}
      class="absolute inset-0 overflow-auto border border-border outline-none focus:border-primary/60 {cursor}"
      style="background:{MATTES[matte]}"
      tabindex="0"
      role="application"
      aria-label="Frame {frame}: arrow keys step, Ctrl+wheel zooms, {cropping
        ? 'the wheel crops the nearest side, a drag on a crop line moves it, Shift+wheel scrolls'
        : 'drag pans'}"
      onkeydown={onkey}
      {onwheel}
      {ondblclick}
      {onpointerdown}
      {onpointermove}
      {onpointerup}
      onpointercancel={onpointerup}
      {onpointerleave}
      {onscroll}
    >
      <!-- At least the viewport's size, centring the frame; bigger when the frame (plus its margin) is. -->
      <div class="grid min-h-full min-w-full place-items-center" style="width:max-content;height:max-content;padding:{PAD}px">
        <div bind:this={frameEl} class="relative" style="width:{dispW}px;height:{dispH}px">
          {#if shown}
            <img
              src={shown}
              alt="Frame {frame}"
              draggable="false"
              class="block h-full w-full select-none"
              style="image-rendering: {scale >= 2 ? 'pixelated' : 'auto'}"
            />
            {#if crop && stage === 'source'}
              {@const band = (side: keyof Crop) => (armed === side ? 'bg-destructive/60' : 'bg-destructive/40')}
              <div class="pointer-events-none absolute inset-0">
                <div class="absolute inset-x-0 top-0 {band('top')}" style="height:{pct(crop.top, height)}"></div>
                <div class="absolute inset-x-0 bottom-0 {band('bottom')}" style="height:{pct(crop.bottom, height)}"></div>
                <div
                  class="absolute left-0 {band('left')}"
                  style="top:{pct(crop.top, height)};bottom:{pct(crop.bottom, height)};width:{pct(crop.left, width)}"
                ></div>
                <div
                  class="absolute right-0 {band('right')}"
                  style="top:{pct(crop.top, height)};bottom:{pct(crop.bottom, height)};width:{pct(crop.right, width)}"
                ></div>
                <!-- No outline round the kept picture: it would cover the edge rows a crop is judged by.
                     The side the wheel moves is marked on the matte, just outside the frame. -->
                {#if cropping && armed}
                  <div
                    class="absolute bg-primary {armed === 'top' || armed === 'bottom' ? 'inset-x-0 h-1' : 'inset-y-0 w-1'}"
                    style="{armed}:-8px"
                    data-armed={armed}
                  ></div>
                {/if}
              </div>
            {/if}
          {/if}
        </div>
      </div>
    </div>

    {#if src && slow}
      <div class="pointer-events-none absolute top-3 right-3 rounded-full bg-black/60 p-1.5 text-white" role="status" aria-label="Loading the frame">
        <LoaderCircleIcon class="size-4 animate-spin" />
      </div>
    {/if}

    {#if !src}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
        {#if error}
          <pre class="max-w-full overflow-auto border border-destructive/50 bg-destructive/10 p-3 text-xs whitespace-pre-wrap text-destructive">{error}</pre>
        {:else if loading}
          <span class="text-muted-foreground">Loading the frame (the first one indexes the source, which can take a while)…</span>
        {/if}
      </div>
    {:else if error || notice}
      <!-- Over the kept frame: why it isn't the newest. -->
      <div class="pointer-events-none absolute inset-x-2 top-2 flex flex-col items-start gap-1 text-xs">
        {#if error}
          <pre class="max-h-24 max-w-full overflow-hidden bg-destructive px-2 py-1 whitespace-pre-wrap text-white">{error}</pre>
        {/if}
        {#if notice}
          <span class="px-2 py-1 text-white {notice.tone === 'bad' ? 'bg-destructive' : 'bg-black/70'}"
            >{notice.text}</span
          >
        {/if}
      </div>
    {/if}

    {#if pannable && (panning || showMap) && shown}
      <div class="pointer-events-none absolute right-3 bottom-3 w-48 overflow-hidden rounded-md border bg-black/80 shadow-lg">
        <div class="relative">
          <img src={shown} alt="" class="block w-full opacity-70" />
          <div
            class="absolute border-2 border-primary"
            style="left:{mapPos.left}%;top:{mapPos.top}%;width:{mapPos.w}%;height:{mapPos.h}%"
          ></div>
        </div>
      </div>
    {/if}
  </div>

  <div class="@container flex items-center gap-1 @lg:gap-2">
    <Button variant="ghost" size="icon" class="hidden @md:inline-flex" onclick={() => seek(0)} title="First (Home)" aria-label="First frame"><ChevronsLeftIcon /></Button>
    <Button variant="ghost" size="icon" onclick={() => seek(frame - 1)} title="Previous (←)" aria-label="Previous frame"><ChevronLeftIcon /></Button>
    <Slider
      type="single"
      class="mx-2 min-w-10 flex-1"
      min={0}
      max={Math.max(0, frames - 1)}
      step={1}
      bind:value={scrub}
      onValueCommit={v => seek(v)}
      aria-label="Frame"
    />
    <Button variant="ghost" size="icon" onclick={() => seek(frame + 1)} title="Next (→)" aria-label="Next frame"><ChevronRightIcon /></Button>
    <Button variant="ghost" size="icon" class="hidden @md:inline-flex" onclick={() => seek(frames - 1)} title="Last (End)" aria-label="Last frame"><ChevronsRightIcon /></Button>
    <Input
      class="w-20 shrink-0 text-right font-mono"
      aria-label="Frame number"
      bind:value={frameInput}
      onkeydown={e => e.key === 'Enter' && seek(+frameInput || 0)}
      onblur={() => seek(+frameInput || 0)}
    />
    <span class="shrink-0 text-xs whitespace-nowrap text-muted-foreground tabular-nums">/ {frames - 1} · {(frame / (fps || 24)).toFixed(2)} s</span>
  </div>
</div>
