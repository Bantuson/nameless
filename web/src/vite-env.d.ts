/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_NAMELESS_CLIENT?: 'mock' | 'http';
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
