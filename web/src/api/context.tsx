/**
 * React injection of the {@link NamelessApi} port.
 *
 * The whole app reads its client from this context — never by importing a concrete adapter. At the
 * composition root (`main.tsx`) we inject `HttpNamelessApi` or `MockNamelessApi`; in tests we wrap
 * the tree in `<ApiProvider client={new MockNamelessApi()}>`. This is the loose-coupling seam: no
 * component or hook knows which implementation it is talking to.
 */

import { createContext, useContext, type ReactNode } from 'react';
import type { NamelessApi } from './NamelessApi';

const ApiContext = createContext<NamelessApi | null>(null);

export function ApiProvider({
  client,
  children,
}: {
  client: NamelessApi;
  children: ReactNode;
}): JSX.Element {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

/** The injected client. Throws if used outside an `<ApiProvider>` (a wiring mistake, surfaced loudly). */
export function useApi(): NamelessApi {
  const api = useContext(ApiContext);
  if (!api) throw new Error('useApi must be used within an <ApiProvider>');
  return api;
}
