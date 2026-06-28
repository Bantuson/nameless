import { describe, expect, it } from 'vitest';
import type { CreditSample } from '../api/types';
import { renderCreditsSheet } from './credits';

const sample = (over: Partial<CreditSample>): CreditSample => ({
  fragment: 'frag-1',
  source_title: 'Midnight Reverie',
  source_artist: 'Esther Vale',
  stem_type: 'vocals',
  start_ms: 12_000,
  end_ms: 18_000,
  rights: 'copyrighted_uncleared',
  ...over,
});

describe('renderCreditsSheet (pure port of the Rust credits_sheet)', () => {
  it('leads with the attribution-is-not-permission notice', () => {
    const sheet = renderCreditsSheet('Late Night Tape', [sample({})]);
    expect(sheet.indexOf('Attribution is not permission')).toBeGreaterThanOrEqual(0);
    // It leads: the notice appears before the first sample line.
    expect(sheet.indexOf('Attribution is not permission')).toBeLessThan(sheet.indexOf('Midnight Reverie'));
  });

  it('lists each sample with stem, range, and rights, and a deterministic count line', () => {
    const sheet = renderCreditsSheet('Tape', [
      sample({ fragment: 'a', source_title: 'Wasting Time', stem_type: 'piano', rights: 'own_work' }),
      sample({ fragment: 'b' }),
    ]);
    expect(sheet).toContain('2 sampled fragments in this project');
    expect(sheet).toContain('`piano`');
    expect(sheet).toContain('12000–18000 ms');
    expect(sheet).toContain('copyrighted_uncleared');
  });

  it('handles an empty project', () => {
    const sheet = renderCreditsSheet('Empty', []);
    expect(sheet).toContain('Attribution is not permission');
    expect(sheet).toContain('No samples in this project');
  });
});
