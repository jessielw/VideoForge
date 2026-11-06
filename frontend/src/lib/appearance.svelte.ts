// The chosen palette and corner roundness: remembered in this browser, applied to <html> at once
// (main.ts calls apply() before the app mounts, so there is no flash of the default look).
import {
  ACCENT_KEY,
  DEFAULT_DENSITY,
  DEFAULT_PALETTE,
  DENSITY_KEY,
  OLED_KEY,
  accentForeground,
  densityScale,
  normalizeAccent,
  normalizeDensity,
  type DensityId,
  DEFAULT_RADIUS,
  PALETTE_KEY,
  RADIUS_KEY,
  normalizePalette,
  normalizeRadius,
  radiusRem,
  type PaletteId,
  type RadiusId,
} from './appearance'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage blocked: the choice lasts until reload */
  }
}

class Appearance {
  #palette = $state<PaletteId>(normalizePalette(read(PALETTE_KEY)))
  #radius = $state<RadiusId>(normalizeRadius(read(RADIUS_KEY)))

  get palette(): PaletteId {
    return this.#palette
  }
  set palette(value: PaletteId) {
    this.#palette = normalizePalette(value)
    write(PALETTE_KEY, this.#palette)
    this.apply()
  }

  get radius(): RadiusId {
    return this.#radius
  }
  set radius(value: RadiusId) {
    this.#radius = normalizeRadius(value)
    write(RADIUS_KEY, this.#radius)
    this.apply()
  }

  #density = $state<DensityId>(normalizeDensity(read(DENSITY_KEY)))
  #accent = $state<string | null>(normalizeAccent(read(ACCENT_KEY)))
  #oled = $state(read(OLED_KEY) === '1')

  get density(): DensityId {
    return this.#density
  }
  set density(value: DensityId) {
    this.#density = normalizeDensity(value)
    write(DENSITY_KEY, this.#density)
    this.apply()
  }

  get accent(): string | null {
    return this.#accent
  }
  set accent(value: string | null) {
    this.#accent = normalizeAccent(value)
    write(ACCENT_KEY, this.#accent ?? '')
    this.apply()
  }

  get oled(): boolean {
    return this.#oled
  }
  set oled(value: boolean) {
    this.#oled = value
    write(OLED_KEY, value ? '1' : '0')
    this.apply()
  }

  get isDefault(): boolean {
    return (
      this.#palette === DEFAULT_PALETTE &&
      this.#radius === DEFAULT_RADIUS &&
      this.#density === DEFAULT_DENSITY &&
      this.#accent === null &&
      !this.#oled
    )
  }

  reset(): void {
    this.palette = DEFAULT_PALETTE
    this.radius = DEFAULT_RADIUS
    this.density = DEFAULT_DENSITY
    this.accent = null
    this.oled = false
  }

  apply(): void {
    if (typeof document === 'undefined') return
    const root = document.documentElement
    if (this.#palette === DEFAULT_PALETTE) root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', this.#palette)
    if (this.#radius === DEFAULT_RADIUS) root.style.removeProperty('--radius')
    else root.style.setProperty('--radius', `${radiusRem(this.#radius)}rem`)
    // Density scales the root font size, so every rem-based size and gap follows.
    if (this.#density === DEFAULT_DENSITY) root.style.removeProperty('font-size')
    else root.style.fontSize = `${densityScale(this.#density) * 100}%`
    if (this.#oled) root.setAttribute('data-oled', '')
    else root.removeAttribute('data-oled')
    // A custom accent beats the palette's, in light and dark alike.
    for (const name of ['--primary', '--ring', '--primary-foreground']) root.style.removeProperty(name)
    if (this.#accent) {
      root.style.setProperty('--primary', this.#accent)
      root.style.setProperty('--ring', this.#accent)
      root.style.setProperty('--primary-foreground', accentForeground(this.#accent))
    }
  }
}

export const appearance = new Appearance()
