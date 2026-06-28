/**
 * Pure rendering of a project's sample credits (UI-04). Leads with the non-negotiable
 * "attribution is not permission" notice, lists each sample, and offers the rendered markdown sheet
 * (the export artifact) in a collapsible block.
 */

import type { Credits } from '../api/types';
import { timeRangeLabel } from '../lib/format';
import { RightsTag } from './badges';
import { Banner, EmptyState } from './ui';

export function CreditsList({ credits }: { credits: Credits }): JSX.Element {
  return (
    <div className="credits">
      <Banner tone="warn" title="Attribution is not permission">
        Sampling a copyrighted recording is infringement regardless of personal or portfolio intent.
        Clear every uncleared or unknown sample before publishing output that contains it.
      </Banner>

      {credits.samples.length === 0 ? (
        <EmptyState>No samples in this project.</EmptyState>
      ) : (
        <>
          <p className="credits__summary">
            {credits.samples.length} sampled fragment{credits.samples.length === 1 ? '' : 's'}:
          </p>
          <ul className="credits__list" aria-label="Sample credits">
            {credits.samples.map((s) => (
              <li key={s.fragment} className="credits__item">
                <div className="credits__item-head">
                  <span className="credits__title">{s.source_title}</span>
                  <span className="credits__artist">— {s.source_artist}</span>
                  <RightsTag rights={s.rights} />
                </div>
                <p className="credits__meta">
                  stem <code>{s.stem_type}</code> · range {timeRangeLabel(s.start_ms, s.end_ms)}
                </p>
              </li>
            ))}
          </ul>

          <details className="credits__sheet">
            <summary>View the credits sheet (markdown export)</summary>
            <pre className="credits__markdown">{credits.markdown}</pre>
          </details>
        </>
      )}
    </div>
  );
}
