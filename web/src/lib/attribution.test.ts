import { describe, expect, it } from 'vitest';
import { isAttributionComplete, missingAttributionFields, type PartialAttribution } from './attribution';

const full: PartialAttribution = {
  sourceTrackId: 'track-1',
  stemId: 'stem-1',
  sourceTitle: 'Midnight Reverie',
  sourceArtist: 'Esther Vale',
  stemType: 'vocals',
  startMs: 12_000,
  endMs: 18_000,
  rights: 'copyrighted_uncleared',
};

describe('missingAttributionFields (pure port of the Rust completeness rule)', () => {
  it('returns no missing fields for a complete attribution', () => {
    expect(missingAttributionFields(full)).toEqual([]);
    expect(isAttributionComplete(full)).toBe(true);
  });

  it('reports every missing field of an empty attribution', () => {
    const missing = missingAttributionFields({});
    expect(missing).toEqual([
      'source_track',
      'stem',
      'source_title',
      'source_artist',
      'stem_type',
      'time_range',
      'rights',
    ]);
  });

  it('treats a whitespace-only title or artist as missing (an empty credit is not a credit)', () => {
    const missing = missingAttributionFields({ ...full, sourceTitle: '   ', sourceArtist: '\t' });
    expect(missing).toContain('source_title');
    expect(missing).toContain('source_artist');
  });

  it('requires a positive time span (end > start)', () => {
    expect(missingAttributionFields({ ...full, startMs: 5_000, endMs: 5_000 })).toEqual(['time_range']);
    expect(missingAttributionFields({ ...full, startMs: 20_000, endMs: 10_000 })).toEqual(['time_range']);
  });

  it('rejects a negative start offset (IN-02 client-side tightening)', () => {
    expect(missingAttributionFields({ ...full, startMs: -100, endMs: 100 })).toEqual(['time_range']);
    expect(missingAttributionFields({ ...full, startMs: 0, endMs: 100 })).toEqual([]);
  });

  it('flags a missing rights status', () => {
    expect(missingAttributionFields({ ...full, rights: null })).toEqual(['rights']);
  });
});
