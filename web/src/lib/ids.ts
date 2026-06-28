/**
 * ID + content-hash helpers for the in-memory mock.
 *
 * `newId` is injectable-by-default but falls back to `crypto.randomUUID()` (present in Node 18+ and
 * modern browsers). `pseudoContentHash` is a small deterministic FNV-1a over a string — NOT a real
 * SHA-256, just a stable stand-in so the mock can produce a content-address-shaped `audio_uri`
 * (`sha256:<hex>`) without reading real bytes. The real control plane content-hashes actual audio.
 */

export function newId(): string {
  return globalThis.crypto.randomUUID();
}

/** Deterministic FNV-1a 32-bit hash → 8 hex chars. Pure. */
export function pseudoContentHash(input: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    // 32-bit FNV prime multiply via shifts to stay in integer range.
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return `sha256:${h.toString(16).padStart(8, '0')}`;
}
