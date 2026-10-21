# VideoForge web UI

Svelte 5 + Vite + TypeScript + Tailwind 4. See ../ARCHITECTURE.md.

- `npm install && npm run build`: writes `dist/`, which `uv run videoforge serve` serves.
- `npm run dev`: hot-reload UI on http://localhost:5173; `/api` (and its WebSocket) goes to
  `videoforge serve` on 8765.
- `npm run check`: svelte-check + tsc.
- `npm test`: frontend unit and state regression tests.
- `npx playwright install chromium` once, then `npm run test:browser`: mounted queue tests with
  isolated API/WebSocket fixtures, a 10,000-job batch, keyboard focus, 320/800 CSS pixel layouts,
  and axe WCAG AA checks in light/dark mode. Page-layout checks cover wide Templates/Settings
  editors and New jobs scrolling in short windows. No real jobs or media tools are used.
  On Linux, `npx playwright install --with-deps chromium` also installs browser system libraries.
  `PLAYWRIGHT_CHROMIUM_EXECUTABLE` optionally points to an existing Chromium executable.
  Screenshots and failure traces go to `../build/queue-browser-results/`.

The layout tests exercise reflow at effective zoom viewport sizes. Native browser zoom controls
and screen-reader announcements still need a manual desktop pass.
