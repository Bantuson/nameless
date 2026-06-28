/**
 * Pure card rendering a reference's vibe + NON-melodic sonic-target summary (UI-02).
 *
 * Shows genre, tempo range, LUFS, tonal balance, stereo width, the embedding dimension (a count,
 * never the vector), and the LLM vibe prose. When analysis is still pending it says so. It carries
 * the "context, never cloned" line at the top — the honest product boundary, always visible.
 */

import type { ReferenceView } from '../api/types';
import { lufs, stereoWidth, tempoRange } from '../lib/format';
import { TonalBalanceBars } from './TonalBalanceBars';
import { Banner, Stat } from './ui';

export function ReferenceSummaryCard({ reference }: { reference: ReferenceView }): JSX.Element {
  const title = reference.title ?? 'Untitled reference';
  const artist = reference.artist ?? 'Unknown artist';
  return (
    <article className="ref-card" aria-label={`Reference summary for ${title}`}>
      <header className="ref-card__head">
        <h3 className="ref-card__title">{title}</h3>
        <p className="ref-card__artist">{artist}</p>
      </header>

      <Banner tone="info" title="Context, never cloned">
        A reference steers atmosphere and measurable targets only. Its melody, chords, and structure
        are never extracted or reproduced — the goal is to translate your intent, not imitate the song.
      </Banner>

      {reference.analysis === null ? (
        <p className="ref-card__pending" role="status">
          Analysis pending — the reference has been uploaded but its vibe/targets are not ready yet.
        </p>
      ) : (
        <>
          <dl className="stat-grid">
            <Stat term="Genre" value={reference.analysis.genre ?? '—'} />
            <Stat
              term="Tempo range"
              value={tempoRange(reference.analysis.tempo_bpm_min, reference.analysis.tempo_bpm_max)}
            />
            <Stat term="Loudness" value={lufs(reference.analysis.lufs)} />
            <Stat term="Stereo width" value={stereoWidth(reference.analysis.stereo_width)} />
            <Stat
              term="Style embedding"
              value={`${reference.analysis.embedding_dim}-d (vector withheld)`}
            />
            <Stat term="Analyzer" value={reference.analysis.analyzer_version} />
          </dl>

          <section className="ref-card__section" aria-label="Tonal balance">
            <h4 className="ref-card__subtitle">Tonal balance</h4>
            <TonalBalanceBars bands={reference.analysis.tonal_balance} />
          </section>

          <section className="ref-card__section" aria-label="Vibe">
            <h4 className="ref-card__subtitle">Vibe</h4>
            <p className="ref-card__vibe">{reference.analysis.vibe}</p>
          </section>
        </>
      )}
    </article>
  );
}
