/**
 * Wire-contract parity tests for the REAL Http adapter (WR-01).
 *
 * The axum server is env-gated (not run here), so these tests pin the on-the-wire JSON body keys
 * against the Rust serde contract (`crates/nameless-core/src/attribution.rs` `PartialAttribution`,
 * `reference.rs`, and `crates/nameless-cli/src/output.rs`). The `MockNamelessApi` reads the TS input
 * object directly and never exercises wire naming, so this is the only guard that the JSON bodies the
 * client POSTs use the server's snake_case field names rather than the camelCase TS property names.
 */

import { describe, expect, it } from 'vitest';
import { HttpNamelessApi } from './HttpNamelessApi';

interface Captured {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
}

/** A `fetch` stub that records the request and replies with `responseBody` as 200 JSON. */
function capturingFetch(responseBody: unknown): { fetchFn: typeof fetch; calls: Captured[] } {
  const calls: Captured[] = [];
  const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawBody = init?.body;
    calls.push({
      url: String(input),
      method: init?.method ?? 'GET',
      body: typeof rawBody === 'string' ? JSON.parse(rawBody) : null,
    });
    return new Response(JSON.stringify(responseBody), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as unknown as typeof fetch;
  return { fetchFn, calls };
}

describe('HttpNamelessApi wire contract (WR-01)', () => {
  it('serializes addSample with snake_case keys matching the Rust attribution contract', async () => {
    const { fetchFn, calls } = capturingFetch({ fragment: 'f1' });
    const api = new HttpNamelessApi({ baseUrl: 'http://x', fetchFn });

    await api.addSample({
      projectId: 'p1',
      stemId: 's1',
      artist: 'Esther Vale',
      title: 'Late Night',
      startMs: 1000,
      endMs: 5000,
      rights: 'royalty_free',
    });

    expect(calls).toHaveLength(1);
    const body = calls[0].body!;
    // Exactly the server's field names — and crucially NONE of the camelCase TS names.
    expect(body).toMatchObject({
      stem_id: 's1',
      source_artist: 'Esther Vale',
      source_title: 'Late Night',
      start_ms: 1000,
      end_ms: 5000,
      rights: 'royalty_free',
    });
    for (const camel of ['stemId', 'artist', 'startMs', 'endMs', 'title']) {
      expect(body).not.toHaveProperty(camel);
    }
  });

  it('serializes attachReference with snake_case `reference_id`', async () => {
    const { fetchFn, calls } = capturingFetch({ reference: 'r1', project: 'p1', role: 'vibe' });
    const api = new HttpNamelessApi({ baseUrl: 'http://x', fetchFn });

    await api.attachReference({ projectId: 'p1', referenceId: 'r1', role: 'vibe' });

    const body = calls[0].body!;
    expect(body).toMatchObject({ reference_id: 'r1', role: 'vibe' });
    expect(body).not.toHaveProperty('referenceId');
  });
});
