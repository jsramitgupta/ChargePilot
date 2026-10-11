import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backendTarget = process.env.CHARGEPILOT_BACKEND_URL ?? 'http://localhost:8000'
const backendProxy = { target: backendTarget, changeOrigin: true }

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: Object.fromEntries(
      [
        '/api',
        '/login',
        '/register',
        '/logout',
        '/devices',
        '/mappings',
        '/endpoints',
        '/connectors',
        '/events',
        '/users',
        '/tenants',
        '/tenant',
        '/agent',
        '/health',
        '/ready',
        '/profile',
        '/static',
      ].map((path) => [path, backendProxy]),
    ),
  },
})
