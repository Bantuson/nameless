/**
 * A small async-load primitive the data hooks build on.
 *
 * Returns `{ data, loading, error, refresh }`. Re-runs when `deps` change or `refresh()` is called.
 * Cancels stale resolutions (so a fast project switch can't render the previous project's data).
 * This is the only place the load/loading/error lifecycle is implemented — every hook reuses it
 * (separation of concerns: lifecycle here, the actual call in each hook).
 */

import { useCallback, useEffect, useState } from 'react';

export interface AsyncData<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
}

export function useAsyncData<T>(loader: () => Promise<T>, deps: unknown[]): AsyncData<T> {
  const [data, setData] = useState<T>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error>();
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(undefined);
    loader()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `loader` is intentionally excluded — `deps` + `tick` drive re-runs (the closure is fresh each render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, loading, error, refresh };
}
