/**
 * Render a credits sheet from a project's sample rows — a PURE port of the Rust `credits_sheet`
 * (`crates/nameless-core/src/attribution.rs`). Text in, text out; deterministic.
 *
 * Used by the `MockNamelessApi` so its `getCredits` markdown matches the real backend's, and reused
 * by the UI as the single source of the rendered sheet. It ALWAYS leads with the
 * "attribution is not permission" notice (SAMP-04) and sorts deterministically by artist then title.
 */

import type { CreditSample } from '../api/types';
import { rightsNote } from './rights';

const PERMISSION_NOTICE =
  '> **Attribution is not permission.** Sampling a copyrighted recording is infringement ' +
  'regardless of personal or portfolio intent; crediting a source does not make using it legal. ' +
  'Clear every `copyrighted_uncleared` / `unknown` sample before publishing output that contains it.';

export function renderCreditsSheet(projectTitle: string, rows: readonly CreditSample[]): string {
  const sorted = [...rows].sort((a, b) => {
    const byArtist = a.source_artist.toLowerCase().localeCompare(b.source_artist.toLowerCase());
    if (byArtist !== 0) return byArtist;
    return a.source_title.toLowerCase().localeCompare(b.source_title.toLowerCase());
  });

  let out = `# Credits — ${projectTitle}\n\n${PERMISSION_NOTICE}\n\n`;

  if (sorted.length === 0) {
    out += '_No samples in this project._\n';
    return out;
  }

  out += `${sorted.length} sampled fragment${sorted.length === 1 ? '' : 's'} in this project:\n\n`;

  sorted.forEach((a, i) => {
    const durationMs = Math.max(0, a.end_ms - a.start_ms);
    out += `${i + 1}. **${a.source_title}** — ${a.source_artist}\n`;
    out += `   - stem: \`${a.stem_type}\`  ·  range: ${a.start_ms}–${a.end_ms} ms (${durationMs} ms)\n`;
    out += `   - rights: \`${a.rights}\` — ${rightsNote(a.rights)}\n`;
  });

  return out;
}
