/**
 * Pure formatting + labelling helpers. No I/O, no React — deterministic string in, string out, so
 * they are trivially unit-testable and reusable across presentational components.
 */

import type { FragmentKind, FragmentState, Provenance, ReferenceRole, StemType } from '../api/types';

/** Human label for a fragment kind. */
export function kindLabel(kind: FragmentKind): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

/** Human label for a fragment lifecycle state. */
export function stateLabel(state: FragmentState): string {
  return state.charAt(0).toUpperCase() + state.slice(1);
}

/** Human label for a provenance. */
export function provenanceLabel(p: Provenance): string {
  switch (p) {
    case 'human_recorded':
      return 'Human-recorded';
    case 'ai_generated':
      return 'AI-generated';
    case 'derived':
      return 'Derived';
    case 'sampled':
      return 'Sampled';
  }
}

/** Human label for a stem type. */
export function stemTypeLabel(s: StemType): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Human label for a reference role. */
export function roleLabel(r: ReferenceRole): string {
  return r === 'vibe' ? 'Vibe (atmosphere)' : 'Sonic target (measurable)';
}

/** The five tonal-balance band names, low → high (matches `TonalBalance` ordering). */
export const TONAL_BAND_NAMES: readonly string[] = ['Low', 'Low-mid', 'Mid', 'High-mid', 'High'];

/** Format a tempo range like "110–116 BPM". A zero-width range collapses to a single value. */
export function tempoRange(min: number, max: number): string {
  const lo = Math.round(min);
  const hi = Math.round(max);
  return lo === hi ? `${lo} BPM` : `${lo}–${hi} BPM`;
}

/** Format integrated loudness like "-9.5 LUFS". */
export function lufs(value: number): string {
  return `${value.toFixed(1)} LUFS`;
}

/** Format a stereo-width ratio in [0,1] as a percentage like "42% wide". */
export function stereoWidth(value: number): string {
  return `${Math.round(value * 100)}% wide`;
}

/** Format milliseconds as seconds with one decimal, e.g. 6000 → "6.0s". `null` → "—". */
export function msToSeconds(ms: number | null | undefined): string {
  if (ms == null) return '—';
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Format a `START–END ms` time range like "12000–18000 ms (6.0s)". */
export function timeRangeLabel(startMs: number, endMs: number): string {
  return `${startMs}–${endMs} ms (${msToSeconds(endMs - startMs)})`;
}

/** Truncate a note for compact one-line display, appending an ellipsis when cut. */
export function notePreview(note: string, max = 80): string {
  const flat = note.trim().replace(/[\r\n]+/g, ' ');
  if (flat.length <= max) return flat;
  return `${flat.slice(0, Math.max(0, max - 1))}…`;
}
