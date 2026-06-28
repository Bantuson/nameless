/** Pure table of a track's retained stems, each with a "Use as sample" action. */

import type { StemSummary } from '../api/types';
import { msToSeconds, stemTypeLabel } from '../lib/format';
import { Button, EmptyState } from './ui';

export function StemTable({
  stems,
  selectedStemId,
  onSelect,
}: {
  stems: StemSummary[];
  selectedStemId: string | null;
  onSelect: (stemId: string) => void;
}): JSX.Element {
  if (stems.length === 0) {
    return (
      <EmptyState>
        No stems yet. Separate the track to build its retained stem library (kept indefinitely).
      </EmptyState>
    );
  }
  return (
    <table className="stem-table">
      <caption className="stem-table__caption">Retained stems — promote any to an attributed sample</caption>
      <thead>
        <tr>
          <th scope="col">Stem</th>
          <th scope="col">Separator</th>
          <th scope="col">Length</th>
          <th scope="col">
            <span className="visually-hidden">Action</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {stems.map((s) => {
          const selected = s.id === selectedStemId;
          return (
            <tr key={s.id} className={selected ? 'stem-table__row stem-table__row--selected' : 'stem-table__row'}>
              <th scope="row" className="stem-table__type">
                {stemTypeLabel(s.stem_type)}
              </th>
              <td>
                <code>{s.separator}</code>
              </td>
              <td>{msToSeconds(s.duration_ms)}</td>
              <td className="stem-table__action">
                <Button
                  variant={selected ? 'primary' : 'secondary'}
                  onClick={() => onSelect(s.id)}
                  aria-pressed={selected}
                >
                  {selected ? 'Selected' : 'Use as sample'}
                </Button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
