// Look-and-feel choices kept in this browser: a colour palette and how round the corners are.
// Light / dark / system is separate (mode-watcher). The palettes themselves live in app.css as
// `:root[data-theme='<id>']` overrides; the swatches here only draw the picker cards.

export type Swatches = readonly [background: string, surface: string, primary: string]

export interface Palette {
  id: string
  label: string
  description: string
  light: Swatches
  dark: Swatches
}

export const PALETTES = [
  {
    id: 'gold',
    label: 'Gold',
    description: 'Warm brass on neutral stone. The original look.',
    light: ['#f5f5f4', '#ffffff', '#8a6d3f'],
    dark: ['#121214', '#1a1a1d', '#c9a876'],
  },
  {
    id: 'indigo',
    label: 'Indigo',
    description: 'Balanced and familiar, with a soft blue-violet accent.',
    light: ['#eef1f8', '#ffffff', '#4f46e5'],
    dark: ['#0f1220', '#171b2e', '#818cf8'],
  },
  {
    id: 'ocean',
    label: 'Ocean',
    description: 'Cool blues on a calm, slightly deeper surface.',
    light: ['#edf5fa', '#ffffff', '#0369a1'],
    dark: ['#0a1520', '#112030', '#38bdf8'],
  },
  {
    id: 'forest',
    label: 'Forest',
    description: 'Muted greens that stay easy on the eyes.',
    light: ['#eff5ef', '#ffffff', '#15803d'],
    dark: ['#0d1510', '#142019', '#4ade80'],
  },
  {
    id: 'ember',
    label: 'Ember',
    description: 'Warm neutrals with an orange glow.',
    light: ['#fbf3ec', '#ffffff', '#c2410c'],
    dark: ['#1a110d', '#241812', '#fb923c'],
  },
  {
    id: 'rose',
    label: 'Rose',
    description: 'Soft pinks with a deeper crimson accent.',
    light: ['#fbf0f3', '#ffffff', '#be123c'],
    dark: ['#1a0f13', '#241519', '#fb7185'],
  },
  {
    id: 'slate',
    label: 'Slate',
    description: 'Neutral and restrained, cool grey-blue throughout.',
    light: ['#eef1f5', '#ffffff', '#334155'],
    dark: ['#0f1217', '#171b22', '#cbd5e1'],
  },
] as const satisfies readonly Palette[]

export type PaletteId = (typeof PALETTES)[number]['id']

export const RADII = [
  { id: 'sharp', label: 'Sharp', rem: 0.2 },
  { id: 'default', label: 'Default', rem: 0.5 },
  { id: 'round', label: 'Round', rem: 0.8 },
  { id: 'softest', label: 'Softest', rem: 1.1 },
] as const

export type RadiusId = (typeof RADII)[number]['id']

export const DEFAULT_PALETTE: PaletteId = 'gold'
export const DEFAULT_RADIUS: RadiusId = 'default'

export const PALETTE_KEY = 'videoforge.palette'
export const RADIUS_KEY = 'videoforge.radius'

export function normalizePalette(value: unknown): PaletteId {
  const hit = PALETTES.find((p) => p.id === value)
  return hit ? hit.id : DEFAULT_PALETTE
}

export function normalizeRadius(value: unknown): RadiusId {
  const hit = RADII.find((r) => r.id === value)
  return hit ? hit.id : DEFAULT_RADIUS
}

export function radiusRem(id: RadiusId): number {
  return (RADII.find((r) => r.id === id) ?? RADII[1]).rem
}

export const DENSITIES = [
  { id: 'compact', label: 'Compact', scale: 0.9 },
  { id: 'default', label: 'Default', scale: 1 },
  { id: 'comfortable', label: 'Comfortable', scale: 1.1 },
] as const

export type DensityId = (typeof DENSITIES)[number]['id']

export const DEFAULT_DENSITY: DensityId = 'default'

export const DENSITY_KEY = 'videoforge.density'
export const ACCENT_KEY = 'videoforge.accent'
export const OLED_KEY = 'videoforge.oled'

export function normalizeDensity(value: unknown): DensityId {
  const hit = DENSITIES.find((d) => d.id === value)
  return hit ? hit.id : DEFAULT_DENSITY
}

export function densityScale(id: DensityId): number {
  return (DENSITIES.find((d) => d.id === id) ?? DENSITIES[1]).scale
}

/** A custom accent as lower-case `#rrggbb`, or null (use the palette's own) for anything else. */
export function normalizeAccent(value: unknown): string | null {
  return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : null
}

/** Text colour that reads on `hex`: dark on light accents, white on dark ones. */
export function accentForeground(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? '#1c1917' : '#ffffff'
}
