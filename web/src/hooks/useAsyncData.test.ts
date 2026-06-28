/**
 * Tests for the async-load primitive — focused on WR-02: stale data must not survive a deps change
 * (a project switch), but must survive a manual refresh (no flash).
 */

import { describe, expect, it } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useAsyncData } from './useAsyncData';

function deferred<T>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('useAsyncData', () => {
  it('clears stale data on a deps change so a fast switch shows the spinner, not the previous entity', async () => {
    let current = deferred<string>();
    const { result, rerender } = renderHook(
      ({ dep }) => useAsyncData(() => current.promise, [dep]),
      { initialProps: { dep: 1 } },
    );

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeUndefined();

    const first = current;
    await act(async () => {
      first.resolve('A');
    });
    await waitFor(() => expect(result.current.data).toBe('A'));
    expect(result.current.loading).toBe(false);

    // Switch deps with a still-pending load → data must clear immediately (no leakage of 'A').
    current = deferred<string>();
    rerender({ dep: 2 });
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeUndefined();

    const second = current;
    await act(async () => {
      second.resolve('B');
    });
    await waitFor(() => expect(result.current.data).toBe('B'));
  });

  it('keeps the current data in place across a refresh() (reload without a flash)', async () => {
    let current = deferred<string>();
    const { result } = renderHook(() => useAsyncData(() => current.promise, [1]));

    const first = current;
    await act(async () => {
      first.resolve('A');
    });
    await waitFor(() => expect(result.current.data).toBe('A'));

    // A bare refresh re-runs the loader but must NOT clear the data (deps are identical).
    current = deferred<string>();
    act(() => {
      result.current.refresh();
    });
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBe('A');

    const second = current;
    await act(async () => {
      second.resolve('A2');
    });
    await waitFor(() => expect(result.current.data).toBe('A2'));
  });
});
