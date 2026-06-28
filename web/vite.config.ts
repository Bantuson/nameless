/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Vite + Vitest config. The dev server proxies nothing by default; in a real environment the
// `VITE_API_BASE_URL` env var points the `HttpNamelessApi` at the running axum control plane.
// Tests run in jsdom and use the `MockNamelessApi`, so no backend (and no network) is required.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
