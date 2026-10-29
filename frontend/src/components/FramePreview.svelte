<script lang="ts">
  // A job's frames from the server (VapourSynth, lossless PNG): zoom (fit .. 800%, Ctrl+wheel and
  // double-click zoom at the pointer), drag to pan with a minimap, an edge-detect view for spotting
  // borders, the crop lines, and frame stepping (←/→ 1, Shift 10, PgUp/PgDn 1 s, Home/End).
  // The scrub bar is a native range (bits-ui's slider walks an array of every frame on each move): a
  // drag loads the frame where it rests a moment, and the one it's let go on.
  // Zoom counts screen (device) pixels: at 100% one frame pixel is one screen pixel, and from 100% up
  // the frame is drawn nearest-neighbour, so every pixel shows as it is.
  // The crop stage is the output with the cropped-off margins stacked back on (the server's crop view),
  // so the picture between the lines is the real output (a FillBorders after the crop shows) and each
  // line sits on a pixel boundary: a one-pixel line just outside the kept picture, the margins tinted.
  // With `oncrop` the crop is edited there: the wheel moves the crop line nearest the pointer 2 px a
  // notch (that side is marked), a drag on a line moves it (snapped to 2); then Shift+wheel scrolls a
  // zoomed view and a drag anywhere else still pans.
  // The frame sits on a matte (gray, black or white) with a margin all round, so every edge pixel
  // can be scrolled into view clear of the scrollbars and told apart from the background.
  // A new frame replaces the old one only once it has decoded, so zoom, scroll and the picture
  // stay put while it loads (a spinner shows over it when a load takes a moment); a failed load
  // keeps the last frame under an error banner. Zoom, edges and scroll are bindable so the caller
  // can bring a view back as it was left.
  // Save (S) downloads the shown frame's PNG as the server rendered it: full size, lossless, without the
  // edges view, the crop lines or the matte (the crop view's has its margins on).
  // `sar` is the frame's pixel shape (width / height): an anamorphic frame is shown widened (or narrowed)
  // to the shape it plays at, zoom counting the frame's rows; the crop lines and the pointer follow. The
  // AR toggle shows the stored pixels instead (one screen pixel per frame pixel both ways at 100%).
  import { tick, untrack, type Snippet } from 'svelte'
  import { api } from '../lib/api'
  import { frameFilename } from '../lib/format'
  import type { Crop } from '../lib/types'
  import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left'
  import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
  import ChevronsLeftIcon from '@lucide/svelte/icons/chevrons-left'
  import ChevronsRightIcon from '@lucide/svelte/icons/chevrons-right'
  import DownloadIcon from '@lucide/svelte/icons/download'
  import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
  import ZoomInIcon from '@lucide/svelte/icons/zoom-in'
  import ZoomOutIcon from '@lucide/svelte/icons/zoom-out'
  import { Button } from '$lib/components/ui/button'
  import { Input } from '$lib/components/ui/input'
  import { NativeSelect } from '$lib/components/ui/native-select'
  import { Toggle } from '$lib/components/ui/toggle'

  let {
    jobId,
    source = '',
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
    sar = 1,
    oncrop,
    tools,
  }: {
    jobId: string
    source?: string // the source's path, for a saved frame's name
    stage: 'crop' | 'output'
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
    sar?: number // the frame's pixel aspect ratio (width / height of one pixel)
    oncrop?: (crop: Crop) => void // set: the wheel and the crop lines edit the crop (crop stage only)
    tools?: Snippet // more toolbar controls, after Matte
  } = $props()

  const ZOOMS = [25, 50, 75, 100, 150, 200, 300, 400, 600, 800]
  const PAD = 24 // matte margin around the frame, px
  const MATTES = { gray: '#404040', black: '#000000', white: '#ffffff' } as const
  type Matte = keyof typeof MATTES
  let vw = $state(0) // the viewport's client size
  let vh = $state(0)
  let frameEl = $state<HTMLDivElement>()
  let matte = $state<Matte>(readMatte())
  let shaped = $state(readShaped()) // an anamorphic frame shown at its display shape
  let src = $state<string | null>(null)
  let shownAt = $state({ n: 0, stage: 'output' as 'crop' | 'output' }) // the frame and stage src holds
  let loading = $state(false)
  let slow = $state(false) // a load past a short delay: show the spinner (quick steps don't flash it)
  let error = $state('')
  let pictType = $state('')
  let cropView = $state(false) // the shown frame has its crop margins on (the lines can be drawn on it)
  let nat = $state({ w: 0, h: 0 }) // the shown frame's size: the overlay is laid on what is shown
  let dpr = $state(window.devicePixelRatio || 1)
  let edgeSrc = $state<string | null>(null)
  let viewport = $state<HTMLDivElement>()
  let panning = $state(false)
  let showMap = $state(false)
  let mapPos = $state({ left: 0, top: 0, w: 100, h: 100 })
  let frameInput = $state('0')
  let scrub = $state(0) // the scrub bar's position; while dragging, ahead of the frame
  const SCRUB_REST = 150 // ms a drag rests before its frame loads

  let controller: AbortController | null = null
  let mapTimer: ReturnType<typeof setTimeout> | undefined
  let scrubTimer: ReturnType<typeof setTimeout> | undefined

  async function load(n: number, st: string, v: number) {
    controller?.abort()
    const c = new AbortController()
    controller = c
    loading = true
    const spin = setTimeout(() => controller === c && (slow = true), 250)
    try {
      const res = await fetch(api.frameUrl(jobId, n, st as 'crop' | 'output', v, 'png'), { signal: c.signal })
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
      shownAt = { n, stage: st as 'crop' | 'output' }
      nat = { w: img.naturalWidth, h: img.naturalHeight }
      pictType = res.headers.get('X-Frame-Type') ?? ''
      cropView = res.headers.get('X-Crop-View') === '1'
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
    clearTimeout(scrubTimer)
    frame = Math.max(0, Math.min(frames - 1, Math.round(n)))
  }

  // A drag shows where it is at once; the frame follows once it rests (or on release, the range's change).
  function onscrub() {
    frameInput = String(scrub)
    clearTimeout(scrubTimer)
    scrubTimer = setTimeout(() => seek(scrub), SCRUB_REST)
  }

  $effect(() => () => clearTimeout(scrubTimer))

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
    else if ((e.key === 's' || e.key === 'S') && !e.ctrlKey && !e.metaKey && !e.altKey) saveFrame()
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

  // The device pixel ratio changes with browser zoom and with a move to a screen of another scale; a
  // move doesn't always resize the window, so watch the ratio itself (a query for the current one).
  $effect(() => {
    const mq = matchMedia(`(resolution: ${dpr}dppx)`)
    const update = () => (dpr = window.devicePixelRatio || 1)
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  })

  // --- zoom ---
  $effect(() => {
    const v = viewport
    if (!v) return
    // Rounded down from the real (fractional) size: clientWidth rounds to nearest, and a fitted frame a
    // fraction of a pixel too big would bring a scrollbar that shrinks the fit (and so on, round and round).
    const ro = new ResizeObserver(([e]) => {
      vw = Math.floor(e.contentRect.width)
      vh = Math.floor(e.contentRect.height)
    })
    ro.observe(v)
    return () => ro.disconnect()
  })

  // The frame's size: the shown image's, the clip's until one is shown.
  const W = $derived(nat.w || width)
  const H = $derived(nat.h || height)
  const anamorphic = $derived(Math.abs(sar - 1) > 1e-6)
  const ax = $derived(anamorphic && shaped ? sar : 1) // the frame drawn ax times as wide as its rows' scale
  // scale: screen (device) pixels per frame pixel (down, for an anamorphic frame); layout is in CSS px,
  // dpr of them to a device pixel.
  const fitScale = $derived(
    vw && vh ? Math.max(0.01, Math.min(((vw - 2 * PAD) * dpr) / (W * ax), ((vh - 2 * PAD) * dpr) / H)) : 1,
  )
  const scale = $derived(zoom ? zoom / 100 : fitScale)
  const css = $derived(scale / dpr) // CSS px per frame pixel, down
  const cssX = $derived(css * ax) // and across
  // A length in frame pixels as CSS px, rounded to whole device pixels (so edges land on screen pixels).
  const snap = (v: number) => Math.round(v * scale) / dpr
  const snapX = (v: number) => Math.round(v * scale * ax) / dpr
  const dispW = $derived(Math.floor(W * scale * ax) / dpr)
  const dispH = $derived(Math.floor(H * scale) / dpr)
  // The frame's place: centred, at least PAD in, on a whole device pixel. Centred on the viewport's
  // client size, which is rounded: the box round the frame is never sized from it (see the markup).
  const frameX = $derived(Math.round(Math.max(PAD, (vw - dispW) / 2) * dpr) / dpr)
  const frameY = $derived(Math.round(Math.max(PAD, (vh - dispH) / 2) * dpr) / dpr)
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
    const fx = (viewport.scrollLeft + x - frameEl.offsetLeft) / cssX
    const fy = (viewport.scrollTop + y - frameEl.offsetTop) / css
    zoom = z
    await tick()
    viewport.scrollLeft = fx * cssX + frameEl.offsetLeft - x
    viewport.scrollTop = fy * css + frameEl.offsetTop - y
    updateMap()
  }

  // One step in or out; zooming out past the fit size lands on Fit.
  function zoomBy(dir: number, cx?: number, cy?: number) {
    const cur = scale * 100
    if (dir > 0) {
      const next = ZOOMS.find((z) => z > cur + 0.5)
      if (next) setZoom(next, cx, cy)
    } else if (zoom) {
      const next = [...ZOOMS].reverse().find((z) => z < cur - 0.5)
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
    else setZoom(ZOOMS.find((z) => z >= 100 && z > fitScale * 100 + 1) ?? ZOOMS[ZOOMS.length - 1], e.clientX, e.clientY)
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

  function readShaped(): boolean {
    try {
      return localStorage.getItem('videoforge.anamorphic') !== 'stored'
    } catch {
      return true // storage blocked
    }
  }

  function toggleShaped() {
    shaped = !shaped
    try {
      localStorage.setItem('videoforge.anamorphic', shaped ? 'shaped' : 'stored')
    } catch {
      /* storage blocked */
    }
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
  const lined = $derived(!!crop && stage === 'crop' && cropView) // the lines go on the shown frame
  const cropping = $derived(!!oncrop && lined)
  let armed = $state<keyof Crop | null>(null) // the side the wheel moves: the line nearest the pointer
  let onLine = $state(false) // the pointer is on that line, so a press drags it
  let cropDrag = $state<{ side: keyof Crop; id: number } | null>(null)
  let wheelRest = 0 // touchpads scroll in small steps; they add up to a notch

  // The pointer in source pixels (off the frame on the matte too) and one screen px in source px, each way.
  function framePoint(e: MouseEvent) {
    const r = frameEl!.getBoundingClientRect()
    return {
      x: ((e.clientX - r.left) / r.width) * W,
      y: ((e.clientY - r.top) / r.height) * H,
      pxX: W / r.width,
      pxY: H / r.height,
    }
  }

  // The crop line nearest the pointer, measured in screen px (an anamorphic frame's differ across and down).
  function nearestLine(e: MouseEvent) {
    const { x, y, pxX, pxY } = framePoint(e)
    const c = crop!
    const d = {
      left: (x - c.left) / pxX,
      right: (W - c.right - x) / pxX,
      top: (y - c.top) / pxY,
      bottom: (H - c.bottom - y) / pxY,
    }
    const side = (Object.keys(d) as (keyof Crop)[]).reduce((a, b) => (Math.abs(d[b]) < Math.abs(d[a]) ? b : a))
    return { side, near: Math.abs(d[side]) <= HIT }
  }

  // Even, and never past the opposite side (MIN_OUT left between them).
  function setSide(side: keyof Crop, v: number) {
    const c = crop!
    const max = Math.floor(((side === 'left' || side === 'right' ? W : H) - c[OPPOSITE[side]] - MIN_OUT) / 2) * 2
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
      setSide(s, s === 'left' ? x : s === 'right' ? W - x : s === 'top' ? y : H - y)
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
          const gx =
            -gray[i - w - 1] + gray[i - w + 1] - 2 * gray[i - 1] + 2 * gray[i + 1] - gray[i + w - 1] + gray[i + w + 1]
          const gy =
            -gray[i - w - 1] - 2 * gray[i - w] - gray[i - w + 1] + gray[i + w - 1] + 2 * gray[i + w] + gray[i + w + 1]
          const v = 255 - Math.min(255, Math.sqrt(gx * gx + gy * gy) * 2)
          out.data[i * 4] = out.data[i * 4 + 1] = out.data[i * 4 + 2] = v
          out.data[i * 4 + 3] = 255
        }
      }
      ctx.putImageData(out, 0, 0)
      canvas.toBlob((b) => {
        if (!b) return
        if (edgeSrc) URL.revokeObjectURL(edgeSrc)
        edgeSrc = URL.createObjectURL(b)
      })
    }
    img.src = src
  }

  function saveFrame() {
    if (!src) return
    const link = document.createElement('a')
    link.href = src // the PNG blob as it came: revoked only when the next frame replaces it
    link.download = frameFilename(source, shownAt.n, frames, shownAt.stage)
    document.body.append(link)
    link.click()
    link.remove()
  }

  function toggleEdges() {
    edges = !edges
    if (edges) makeEdges()
  }

  const shown = $derived(edges && edgeSrc ? edgeSrc : src)
  const outW = $derived(crop ? W - crop.left - crop.right : W)
  const outH = $derived(crop ? H - crop.top - crop.bottom : H)
  // The crop stage's frame came back without its margins: a filter after the crop changes the frame.
  const unlined = $derived(!!src && !loading && stage === 'crop' && !cropView)
</script>

<div class="flex h-full min-h-0 flex-col gap-2">
  <div class="flex flex-wrap items-center gap-2 text-sm">
    <div class="flex items-center gap-1">
      <Button variant="ghost" size="icon" onclick={() => zoomBy(-1)} title="Zoom out (-)" aria-label="Zoom out"
        ><ZoomOutIcon /></Button
      >
      <NativeSelect value={zoom} aria-label="Zoom" onchange={(e) => setZoom(+e.currentTarget.value)}>
        <option value={0}>Fit ({Math.round(fitScale * 100)}%)</option>
        {#each ZOOMS as z (z)}<option value={z}>{z}%</option>{/each}
      </NativeSelect>
      <Button variant="ghost" size="icon" onclick={() => zoomBy(1)} title="Zoom in (+)" aria-label="Zoom in"
        ><ZoomInIcon /></Button
      >
    </div>
    <Toggle
      pressed={edges}
      onPressedChange={toggleEdges}
      class="data-[state=on]:bg-primary/15 data-[state=on]:text-primary"
      title="Show edges, to judge borders"
    >
      Edges
    </Toggle>
    <Button variant="ghost" onclick={nextMatte} title="Background around the frame: {matte} (click to change)">
      <span class="inline-block size-3.5 border" style="background:{MATTES[matte]}"></span>Matte
    </Button>
    {#if anamorphic}
      <Toggle
        pressed={shaped}
        onPressedChange={toggleShaped}
        class="data-[state=on]:bg-primary/15 data-[state=on]:text-primary"
        title="Anamorphic frame (pixels {+sar.toFixed(
          4,
        )}:1). On: shown at the shape it plays at. Off: the stored pixels (exact at 100% and up)"
      >
        AR
      </Toggle>
    {/if}
    <Button
      variant="ghost"
      onclick={saveFrame}
      disabled={!src}
      title="Save frame {shownAt.n} as a PNG: full size, lossless (S)"
    >
      <DownloadIcon />Save
    </Button>
    {@render tools?.()}
    <span class="ml-auto text-xs whitespace-nowrap text-muted-foreground tabular-nums">
      {W}×{H}{lined ? ` → ${outW}×${outH}` : ''}{anamorphic ? ` · plays ${((W * sar) / H).toFixed(2)}:1` : ''} · {Math.round(
        scale * 100,
      )}%
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
      <!-- At least the viewport's size (100%, not its rounded client size: a fraction of a pixel over
           would bring a scrollbar, which shrinks the fit, which drops the scrollbar, round and round);
           bigger when the frame plus its margin is. The frame sits on a whole device pixel, its size in
           whole device pixels, so its pixels and the lines line up. -->
      <div class="relative min-h-full min-w-full" style="width:{dispW + 2 * PAD}px;height:{dispH + 2 * PAD}px">
        <div
          bind:this={frameEl}
          class="absolute"
          style="left:{frameX}px;top:{frameY}px;width:{dispW}px;height:{dispH}px"
        >
          {#if shown}
            <img
              src={shown}
              alt="Frame {frame}"
              draggable="false"
              class="block h-full w-full select-none"
              style="image-rendering: {scale >= 1 ? 'pixelated' : 'auto'}"
            />
            {#if lined && crop}
              {@const band = (side: keyof Crop) => (armed === side ? 'bg-destructive/55' : 'bg-destructive/35')}
              {@const line = (side: keyof Crop) => (armed === side ? 'var(--primary)' : 'var(--destructive)')}
              {@const t = snap(crop.top)}
              {@const b = snap(crop.bottom)}
              {@const px = 1 / dpr}
              <div class="pointer-events-none absolute inset-0">
                <!-- The cropped-off margins, tinted. -->
                <div class="absolute inset-x-0 top-0 {band('top')}" style="height:{t}px"></div>
                <div class="absolute inset-x-0 bottom-0 {band('bottom')}" style="height:{b}px"></div>
                <div
                  class="absolute left-0 {band('left')}"
                  style="top:{t}px;bottom:{b}px;width:{snapX(crop.left)}px"
                ></div>
                <div
                  class="absolute right-0 {band('right')}"
                  style="top:{t}px;bottom:{b}px;width:{snapX(crop.right)}px"
                ></div>
                <!-- The lines: one screen pixel just outside the kept picture, so none of its pixels is covered. -->
                <div
                  class="absolute box-border"
                  style="left:{snapX(crop.left) - px}px;top:{t - px}px;right:{snapX(crop.right) - px}px;bottom:{b -
                    px}px;border:{px}px solid;border-color:{line('top')} {line('right')} {line('bottom')} {line(
                    'left',
                  )}"
                ></div>
                <!-- The side the wheel moves is marked on the matte too, just outside the frame. -->
                {#if cropping && armed}
                  <div
                    class="absolute bg-primary {armed === 'top' || armed === 'bottom'
                      ? 'inset-x-0 h-1'
                      : 'inset-y-0 w-1'}"
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
      <div
        class="pointer-events-none absolute top-3 right-3 rounded-full bg-black/60 p-1.5 text-white"
        role="status"
        aria-label="Loading the frame"
      >
        <LoaderCircleIcon class="size-4 animate-spin" />
      </div>
    {/if}

    {#if !src}
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
        {#if error}
          <pre
            class="max-w-full overflow-auto border border-destructive/50 bg-destructive/10 p-3 text-xs whitespace-pre-wrap text-destructive">{error}</pre>
        {:else if loading}
          <span class="text-muted-foreground">Loading the frame…</span>
        {/if}
      </div>
    {:else if error || notice || unlined}
      <!-- Over the kept frame: why it isn't the newest (or has no crop lines). -->
      <div class="pointer-events-none absolute inset-x-2 top-2 flex flex-col items-start gap-1 text-xs">
        {#if error}
          <pre
            class="max-h-24 max-w-full overflow-hidden bg-destructive px-2 py-1 whitespace-pre-wrap text-white">{error}</pre>
        {/if}
        {#if notice}
          <span class="px-2 py-1 text-white {notice.tone === 'bad' ? 'bg-destructive' : 'bg-black/70'}"
            >{notice.text}</span
          >
        {/if}
        {#if unlined}
          <span class="bg-black/70 px-2 py-1 text-white"
            >No crop lines: a filter after the crop changes the size, length or colors, so this is the output as it is.</span
          >
        {/if}
      </div>
    {/if}

    {#if pannable && (panning || showMap) && shown}
      <div
        class="pointer-events-none absolute right-3 bottom-3 w-48 overflow-hidden rounded-md border bg-black/80 shadow-lg"
      >
        <div class="relative">
          <img src={shown} alt="" class="block w-full opacity-70" style="aspect-ratio:{W * ax} / {H}" />
          <div
            class="absolute border-2 border-primary"
            style="left:{mapPos.left}%;top:{mapPos.top}%;width:{mapPos.w}%;height:{mapPos.h}%"
          ></div>
        </div>
      </div>
    {/if}
  </div>

  <div class="@container flex items-center gap-1 @lg:gap-2">
    <Button
      variant="ghost"
      size="icon"
      class="hidden @md:inline-flex"
      onclick={() => seek(0)}
      title="First (Home)"
      aria-label="First frame"><ChevronsLeftIcon /></Button
    >
    <Button variant="ghost" size="icon" onclick={() => seek(frame - 1)} title="Previous (←)" aria-label="Previous frame"
      ><ChevronLeftIcon /></Button
    >
    <input
      type="range"
      class="scrub mx-2 min-w-10 flex-1"
      min={0}
      max={Math.max(0, frames - 1)}
      step={1}
      bind:value={scrub}
      style="--p:{frames > 1 ? scrub / (frames - 1) : 0}"
      oninput={onscrub}
      onchange={() => seek(scrub)}
      aria-label="Frame"
    />
    <Button variant="ghost" size="icon" onclick={() => seek(frame + 1)} title="Next (→)" aria-label="Next frame"
      ><ChevronRightIcon /></Button
    >
    <Button
      variant="ghost"
      size="icon"
      class="hidden @md:inline-flex"
      onclick={() => seek(frames - 1)}
      title="Last (End)"
      aria-label="Last frame"><ChevronsRightIcon /></Button
    >
    <Input
      class="w-20 shrink-0 text-right font-mono"
      aria-label="Frame number"
      bind:value={frameInput}
      onkeydown={(e) => e.key === 'Enter' && seek(+frameInput || 0)}
      onblur={() => seek(+frameInput || 0)}
    />
    <span class="shrink-0 text-xs whitespace-nowrap text-muted-foreground tabular-nums"
      >/ {frames - 1} · {(scrub / (fps || 24)).toFixed(2)} s</span
    >
  </div>
</div>

<style>
  /* The shadcn slider's look: a thin muted track filled in primary up to a small white thumb. */
  .scrub {
    appearance: none;
    height: 1rem;
    background: transparent;
    cursor: pointer;
  }
  .scrub:focus-visible {
    outline: none;
  }
  .scrub::-webkit-slider-runnable-track {
    height: 0.25rem;
    border-radius: 9999px;
    /* The fill ends at the thumb's centre, which travels half a thumb in from each end. */
    background: linear-gradient(to right, var(--primary) calc(0.375rem + (100% - 0.75rem) * var(--p)), var(--muted) 0);
  }
  .scrub::-moz-range-track {
    height: 0.25rem;
    border-radius: 9999px;
    background: var(--muted);
  }
  .scrub::-moz-range-progress {
    height: 0.25rem;
    border-radius: 9999px;
    background: var(--primary);
  }
  .scrub::-webkit-slider-thumb {
    appearance: none;
    box-sizing: border-box;
    width: 0.75rem;
    height: 0.75rem;
    margin-top: -0.25rem;
    border: 1px solid var(--ring);
    border-radius: 9999px;
    background: white;
    transition: box-shadow 0.15s;
  }
  .scrub::-moz-range-thumb {
    box-sizing: border-box;
    width: 0.75rem;
    height: 0.75rem;
    border: 1px solid var(--ring);
    border-radius: 9999px;
    background: white;
    transition: box-shadow 0.15s;
  }
  .scrub:hover::-webkit-slider-thumb,
  .scrub:active::-webkit-slider-thumb,
  .scrub:focus-visible::-webkit-slider-thumb {
    box-shadow: 0 0 0 3px color-mix(in oklab, var(--ring) 50%, transparent);
  }
  .scrub:hover::-moz-range-thumb,
  .scrub:active::-moz-range-thumb,
  .scrub:focus-visible::-moz-range-thumb {
    box-shadow: 0 0 0 3px color-mix(in oklab, var(--ring) 50%, transparent);
  }
</style>
