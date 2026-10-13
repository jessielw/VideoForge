<script lang="ts" module>
  // Stroke icons (24x24, Lucide-style shapes).
  const PATHS = {
    new: 'M12 5v14M5 12h14',
    queue: 'M3 6h13M3 12h13M3 18h9M19 15l3 3-3 3',
    fix: 'M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z',
    log: 'M4 17l6-5-6-5M12 19h8',
    play: 'M7 4l13 8-13 8z',
    stop: 'M6 6h12v12H6z',
    pause: 'M7 5h3v14H7zM14 5h3v14h-3z',
    x: 'M6 6l12 12M18 6L6 18',
    refresh: 'M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4',
    trash: 'M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3',
    folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
    file: 'M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8zM14 3v5h5',
    up: 'M12 19V5M5 12l7-7 7 7',
    down: 'M12 5v14M19 12l-7 7-7-7',
    left: 'M15 6l-6 6 6 6',
    right: 'M9 6l6 6-6 6',
    first: 'M11 6l-6 6 6 6M18 6l-6 6 6 6',
    last: 'M13 6l6 6-6 6M6 6l6 6-6 6',
    crop: 'M6 2v14a2 2 0 0 0 2 2h14M18 22V8a2 2 0 0 0-2-2H2',
    wand: 'M15 4V2M15 10V8M11 6H9M21 6h-2M3 21l12-12M17.8 3.8l-1.4 1.4M17.8 8.2l-1.4-1.4',
    zoomIn: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5M11 8v6M8 11h6',
    zoomOut: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5M8 11h6',
    check: 'M5 12l5 5 9-10',
    alert: 'M12 3l10 18H2zM12 10v4M12 17h.01',
    film: 'M3 4h18v16H3zM7 4v16M17 4v16M3 9h4M17 9h4M3 15h4M17 15h4',
    audio: 'M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13',
    sub: 'M3 5h18v14H3zM7 13h4M13 13h4M7 16h10',
    chapters: 'M6 3h12v18l-6-4-6 4z',
    copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
    home: 'M3 11l9-7 9 7M5 10v10h14V10',
    grip: 'M8.5 6h1M8.5 12h1M8.5 18h1M14.5 6h1M14.5 12h1M14.5 18h1',
  } as const
  export type IconName = keyof typeof PATHS
</script>

<script lang="ts">
  let { name, size = 16, class: cls = '' }: { name: IconName; size?: number; class?: string } = $props()
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.8"
  stroke-linecap="round"
  stroke-linejoin="round"
  class={cls}
  aria-hidden="true"
>
  <path d={PATHS[name]} />
</svg>
