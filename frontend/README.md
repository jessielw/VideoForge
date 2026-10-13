# VideoForge web UI

Svelte 5 + Vite + TypeScript + Tailwind 4. See ../ARCHITECTURE.md.

- `npm install && npm run build`: writes `dist/`, which `uv run videoforge serve` serves.
- `npm run dev`: hot-reload UI on http://localhost:5173; `/api` (and its WebSocket) goes to
  `videoforge serve` on 8765.
- `npm run check`: svelte-check + tsc.
