import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Absolute site address for social-preview tags in index.html (%VITE_SITE_URL%).
process.env.VITE_SITE_URL ??= 'http://localhost:8080'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})
