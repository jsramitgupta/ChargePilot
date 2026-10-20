import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { IncomingMessage } from 'node:http'
import { defineConfig } from 'vite'

const backendTarget = process.env.CHARGEPILOT_BACKEND_URL ?? 'http://localhost:8000'
const reactRoutes = new Set([
  '/',
  '/login',
  '/register',
  '/devices',
  '/mappings',
  '/endpoints',
  '/connectors',
  '/events',
  '/profile',
  '/users',
  '/tenants',
  '/agent',
  '/account',
])
const backendProxy = {
  target: backendTarget,
  changeOrigin: true,
  bypass(request: IncomingMessage) {
    const path = request.url?.split('?')[0]
    if (request.method === 'GET' && path && reactRoutes.has(path)) return request.url
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          minSize: 20_000,
          groups: [{ name: 'vendor', test: /node_modules/ }],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: Object.fromEntries(
      [
        '/api',
        '/devices',
        '/connectors',
        '/agent',
        '/health',
        '/ready',
      ].map((path) => [path, backendProxy]),
    ),
  },
})
