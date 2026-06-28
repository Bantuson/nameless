import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TonalBalanceBars } from './TonalBalanceBars';

describe('TonalBalanceBars', () => {
  it('renders each band as a percentage of the total', () => {
    render(<TonalBalanceBars bands={[1, 1, 1, 1, 0]} />);
    // 1/4 of the total → 25% (the zero-energy band is 0%).
    expect(screen.getAllByText('25%')).toHaveLength(4);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('clamps out-of-range band values to [0,100] (IN-04)', () => {
    // A negative band and a band exceeding the rest must not produce a negative or >100% label.
    render(<TonalBalanceBars bands={[-50, 200, 0, 0, 0]} />);
    const labels = screen.getAllByText(/%$/).map((el) => el.textContent);
    for (const label of labels) {
      const pct = Number(label!.replace('%', ''));
      expect(pct).toBeGreaterThanOrEqual(0);
      expect(pct).toBeLessThanOrEqual(100);
    }
  });
});
