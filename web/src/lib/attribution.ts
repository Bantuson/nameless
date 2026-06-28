/**
 * The attribution-completeness predicate — a PURE port of the Rust `PartialAttribution::missing_fields`
 * (`crates/nameless-core/src/attribution.rs`).
 *
 * The server is the authoritative gate (it re-validates and refuses to create anything incomplete),
 * but mirroring the exact same rule on the client lets the "Add as sample" form disable its submit
 * button and name precisely which fields are still missing — before a request is ever sent. Same
 * integrity boundary, expressed twice, so the UX is honest and the network round-trip is not how a
 * producer discovers a blank credit.
 *
 * The rule matches Rust precisely, including:
 *   - a blank/whitespace-only title or artist counts as MISSING (an empty credit is not a credit);
 *   - a time range needs both ends AND a positive span (`end > start`), else `time_range` is missing.
 */

import type { AttributionField } from '../api/types';

/** The fields gathered for a sample's attribution; any may be absent during data entry. */
export interface PartialAttribution {
  sourceTrackId?: string | null;
  stemId?: string | null;
  sourceTitle?: string | null;
  sourceArtist?: string | null;
  stemType?: string | null;
  startMs?: number | null;
  endMs?: number | null;
  rights?: string | null;
}

function blank(s: string | null | undefined): boolean {
  return s == null || s.trim() === '';
}

/** The fields still missing for a complete attribution. Empty ⇒ complete. */
export function missingAttributionFields(p: PartialAttribution): AttributionField[] {
  const missing: AttributionField[] = [];
  if (!p.sourceTrackId) missing.push('source_track');
  if (!p.stemId) missing.push('stem');
  if (blank(p.sourceTitle)) missing.push('source_title');
  if (blank(p.sourceArtist)) missing.push('source_artist');
  if (!p.stemType) missing.push('stem_type');
  const { startMs, endMs } = p;
  const validRange = startMs != null && endMs != null && endMs > startMs;
  if (!validRange) missing.push('time_range');
  if (!p.rights) missing.push('rights');
  return missing;
}

/** True when nothing is missing. */
export function isAttributionComplete(p: PartialAttribution): boolean {
  return missingAttributionFields(p).length === 0;
}
