/**
 * Pure visualization of a reference's 5-band tonal balance. Each band is a horizontal bar whose
 * width is its share of the total. Coarse on purpose — "where the energy sits", never the notes.
 * Accessible: a `<dl>` of band → percentage, with the bars as decorative aria-hidden adornments.
 */

import { TONAL_BAND_NAMES } from '../lib/format';

export function TonalBalanceBars({ bands }: { bands: number[] }): JSX.Element {
  const total = bands.reduce((a, b) => a + b, 0) || 1;
  return (
    <dl className="tonal" aria-label="Tonal balance by frequency band">
      {bands.map((value, i) => {
        // Clamp to [0,100]: a real analyzer can emit a negative or >total band value, which would
        // otherwise render a negative/overflowing bar width and a misleading percentage label.
        const pct = Math.max(0, Math.min(100, Math.round((value / total) * 100)));
        const name = TONAL_BAND_NAMES[i] ?? `Band ${i + 1}`;
        return (
          <div className="tonal__row" key={name}>
            <dt className="tonal__band">{name}</dt>
            <dd className="tonal__value">
              <span className="tonal__bar" aria-hidden="true" style={{ width: `${pct}%` }} />
              <span className="tonal__pct">{pct}%</span>
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
