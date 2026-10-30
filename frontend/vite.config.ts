/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((h) => h.trim())
  .filter(Boolean)

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages serves the site from /<repo>/; set VITE_BASE=/Linguistic-DNA/ for that build.
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  // The dev server and `vite preview` (a production build, used on a laptop) both forward
  // /api to the local API. VITE_ALLOWED_HOSTS lets a tunnel's hostname through, e.g.
  // VITE_ALLOWED_HOSTS=.trycloudflare.com for a Cloudflare quick tunnel.
  server: { proxy: { '/api': 'http://localhost:8000' }, allowedHosts },
  preview: { proxy: { '/api': 'http://localhost:8000' }, allowedHosts },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
