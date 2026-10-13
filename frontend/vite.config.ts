import { svelte } from '@sveltejs/vite-plugin-svelte'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// `npm run dev` serves the UI with hot reload and forwards the API (and its
// WebSocket) to `videoforge serve` on 8765. `npm run build` writes dist/, which
// the FastAPI server serves itself.
export default defineConfig({
  plugins: [tailwindcss(), svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', ws: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
