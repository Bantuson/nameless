/**
 * The composition root's client factory — chooses which {@link NamelessApi} adapter to inject.
 *
 * Default is the in-memory `MockNamelessApi` (no backend needed). Set `VITE_NAMELESS_CLIENT=http`
 * (and `VITE_API_BASE_URL`) to talk to the real axum control plane instead. This is the ONLY place
 * the app names a concrete adapter; everything else depends on the interface.
 */

import type { NamelessApi } from './NamelessApi';
import { HttpNamelessApi } from './HttpNamelessApi';
import { MockNamelessApi } from './MockNamelessApi';

export function createClient(): NamelessApi {
  const mode = import.meta.env.VITE_NAMELESS_CLIENT ?? 'mock';
  if (mode === 'http') {
    const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8080';
    return new HttpNamelessApi({ baseUrl });
  }
  return new MockNamelessApi();
}
