import { svelte } from '@sveltejs/vite-plugin-svelte'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// `npm run dev` serves the UI with hot reload and forwards the API (and its
// WebSocket) to `videoforge serve` on 8765, or on VIDEOFORGE_PORT when set (the
// browser tests set a closed port). `npm run build` writes dist/, which the
// FastAPI server serves itself.
export default defineConfig({
  resolve: { alias: { $lib: fileURLToPath(new URL('./src/lib', import.meta.url)) } },
  plugins: [tailwindcss(), svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: `http://127.0.0.1:${process.env.VIDEOFORGE_PORT || 8765}`, ws: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
