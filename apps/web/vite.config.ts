import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Absolute site address for social-preview tags in index.html (%VITE_SITE_URL%).
process.env.VITE_SITE_URL ??= 'http://localhost:8080'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // Same origin as in production (nginx): the browser only talks to the dev server.
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8001',
    },
  },
})
