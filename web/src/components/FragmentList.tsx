/** Pure list of a project's fragments — id (short) + state + kind + note. */

import type { FragmentSummary } from '../api/types';
import { kindLabel, notePreview } from '../lib/format';
import { StatePill } from './badges';
import { EmptyState } from './ui';

function shortId(id: string): string {
  return id.slice(0, 8);
}

export function FragmentList({ fragments }: { fragments: FragmentSummary[] }): JSX.Element {
  if (fragments.length === 0) {
    return <EmptyState>No fragments captured yet. Capture a hum, a hook, or a beat to begin.</EmptyState>;
  }
  return (
    <ul className="frag-list" aria-label="Captured fragments">
      {fragments.map((f) => (
        <li key={f.id} className="frag-list__item">
          <div className="frag-list__head">
            <StatePill state={f.state} />
            <span className="frag-list__kind">{kindLabel(f.kind)}</span>
            <code className="frag-list__id" title={f.id}>
              {shortId(f.id)}
            </code>
          </div>
          <p className="frag-list__note">{notePreview(f.note, 120)}</p>
        </li>
      ))}
    </ul>
  );
}
