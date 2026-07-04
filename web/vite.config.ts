/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Vite + Vitest config. Tests run in jsdom and use the `MockNamelessApi`, so no backend (and no
// network) is required.
//
// Dev-server API proxy: set `VITE_API_PROXY_TARGET` (e.g. http://127.0.0.1:8080) to forward the
// control-plane routes to a running axum server. With the proxy, run the app with
// `VITE_NAMELESS_CLIENT=http VITE_API_BASE_URL=""` so `HttpNamelessApi` issues same-origin
// relative requests — this is what makes remote dev hosts (GitHub Codespaces forwarded URLs)
// work without CORS or a second public port. `VITE_API_BASE_URL` pointing straight at the server
// still works for plain localhost dev without the proxy.
const proxyTarget = process.env.VITE_API_PROXY_TARGET;
const apiRoutes = ['/projects', '/fragments', '/references', '/tracks'];

export default defineConfig({
  plugins: [react()],
  server: proxyTarget
    ? {
        proxy: Object.fromEntries(apiRoutes.map((r) => [r, { target: proxyTarget, changeOrigin: true }])),
      }
    : undefined,
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
