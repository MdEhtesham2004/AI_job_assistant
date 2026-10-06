import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      // Vite answers only for localhost unless a host is listed here (DNS-rebinding guard).
      // ngrok tunnels for sharing the dev app; add more with VITE_ALLOWED_HOSTS=a.com,b.com
      allowedHosts: [
        '.ngrok-free.dev',
        '.ngrok-free.app',
        ...(env.VITE_ALLOWED_HOSTS ?? '')
          .split(',')
          .map((host) => host.trim())
          .filter(Boolean),
      ],
      proxy: {
        // Dev only: forward API calls to the local FastAPI backend.
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    test: {
      // Threads start faster than forked processes on Windows (avoids worker start-up timeouts).
      pool: 'threads',
      // Page tests chain several mocked requests; 5 s was too tight on a busy machine.
      testTimeout: 15_000,
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
      css: false,
    },
  }
})
