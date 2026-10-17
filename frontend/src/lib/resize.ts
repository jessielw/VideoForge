// A keep-AR resize, fitted as core.video.settings fits it (the same integer rounding, so the size shown here
// is the size the server saves): the height follows the width, keeping the display aspect ratio of the
// picture going into the resize (the cropped source; an anamorphic source's pixel aspect included).
import type { Crop, Resize, VideoSettings } from './types'

// The picture going into the resize: its pixels, and a pixel's shape (width / height, sarNum / sarDen).
export interface Geometry {
  width: number
  height: number
  sarNum: number
  sarDen: number
}

export const MODS = [2, 4, 8, 16]
export const KERNELS = ['Spline36', 'Spline64', 'Lanczos', 'Bicubic', 'Bilinear', 'Point']
// StaxRip's width menu: the usual targets, by the height they make of 16:9.
export const WIDTHS = [
  { width: 3840, label: '2160p' },
  { width: 2560, label: '1440p' },
  { width: 1920, label: '1080p' },
  { width: 1280, label: '720p' },
  { width: 1024, label: '576p' },
  { width: 854, label: '480p' },
]

const floorDiv = (a: number, b: number) => (a - (a % b)) / b // exact for non-negative safe integers

// The nearest multiple of mod (halves up; at least mod), of the fraction num / den.
function roundMod(num: number, den: number, mod: number): number {
  return Math.max(mod, floorDiv(2 * num + den * mod, 2 * den * mod) * mod)
}

export const snap = (value: number, mod: number) => roundMod(Math.max(0, Math.round(value)), 1, mod)

export function fitHeight(width: number, g: Geometry, mod: number): number {
  return roundMod(width * g.height * g.sarDen, g.width * g.sarNum, mod)
}

export function fitWidth(height: number, g: Geometry, mod: number): number {
  return roundMod(height * g.width * g.sarNum, g.height * g.sarDen, mod)
}

// The display aspect ratio of the picture going in.
export const displayAspect = (g: Geometry) => (g.width * g.sarNum) / (g.height * g.sarDen)

// How far width x height is from it, in percent.
export const arError = (width: number, height: number, g: Geometry) => ((width / height) / displayAspect(g) - 1) * 100

// The shape of the encode's pixels (width / height), as VideoSettings.output_sar: the source's without a
// resize, square after a keep-AR one, the shape undoing a fixed size's stretch (square within 1%).
export function outputShape(r: Resize | null, g: Geometry): number {
  const sar = g.sarNum / g.sarDen
  if (!r) return sar
  if (r.keep_ar || r.width <= 0 || r.height <= 0) return 1
  const shape = (sar * g.width * r.height) / (g.height * r.width)
  return Math.abs(shape - 1) <= 0.01 ? 1 : shape
}

// The source's geometry less the crop when the crop step comes before the resize (VideoSettings.resize_input).
export function resizeInput(video: VideoSettings, source: Geometry): Geometry {
  let { width, height } = source
  for (const s of video.filters) {
    if (s.category === 'resize') break
    if (s.category === 'crop') {
      const c: Crop = video.crop
      width -= c.left + c.right
      height -= c.top + c.bottom
    }
  }
  return { ...source, width, height }
}

// A keep-AR resize fitted to g (VideoSettings.fit_resize); others as they are.
export function fitted(r: Resize, g: Geometry | null): Resize {
  if (!r.keep_ar || !g || g.width <= 0 || g.height <= 0) return r
  const width = snap(r.width, r.mod)
  return { ...r, width, height: fitHeight(width, g, r.mod) }
}
