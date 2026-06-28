/**
 * Rights-status labels + the honest "attribution is not permission" note.
 *
 * `rightsNote` mirrors the Rust `RightsStatus::note()` verbatim so the web surface tells exactly the
 * same legal truth as the CLI and the credits sheet: crediting a source does not make using it legal.
 */

import type { RightsStatus } from '../api/types';

/** Short human label for a rights status. */
export function rightsLabel(r: RightsStatus): string {
  switch (r) {
    case 'copyrighted_uncleared':
      return 'Copyrighted — uncleared';
    case 'royalty_free':
      return 'Royalty-free';
    case 'own_work':
      return 'Own work';
    case 'unknown':
      return 'Unknown';
  }
}

/** The plain note shown next to a status — mirrors `RightsStatus::note()` in Rust. */
export function rightsNote(r: RightsStatus): string {
  switch (r) {
    case 'copyrighted_uncleared':
      return 'copyrighted, NOT cleared — do not publish output containing this sample';
    case 'royalty_free':
      return 'royalty-free / cleared library material';
    case 'own_work':
      return "the producer's own recording";
    case 'unknown':
      return 'provenance unestablished — treat as uncleared until verified';
  }
}

/** True when a status should visually warn the producer (uncleared / unknown). */
export function rightsIsCautionary(r: RightsStatus): boolean {
  return r === 'copyrighted_uncleared' || r === 'unknown';
}
