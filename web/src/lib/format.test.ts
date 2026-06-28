import { describe, expect, it } from 'vitest';
import {
  lufs,
  msToSeconds,
  notePreview,
  provenanceLabel,
  shortId,
  stereoWidth,
  tempoRange,
  timeRangeLabel,
} from './format';

describe('format helpers', () => {
  it('shortens an id to its first 8 chars', () => {
    expect(shortId('0123456789abcdef')).toBe('01234567');
    expect(shortId('abc')).toBe('abc');
  });

  it('formats a tempo range, collapsing a zero-width range', () => {
    expect(tempoRange(110, 114)).toBe('110–114 BPM');
    expect(tempoRange(112, 112)).toBe('112 BPM');
  });

  it('formats loudness and stereo width', () => {
    expect(lufs(-9.4)).toBe('-9.4 LUFS');
    expect(stereoWidth(0.46)).toBe('46% wide');
  });

  it('formats milliseconds as seconds, with an em dash for null', () => {
    expect(msToSeconds(6000)).toBe('6.0s');
    expect(msToSeconds(null)).toBe('—');
  });

  it('formats a time range label', () => {
    expect(timeRangeLabel(12_000, 18_000)).toBe('12000–18000 ms (6.0s)');
  });

  it('truncates long notes with an ellipsis and flattens newlines', () => {
    expect(notePreview('a\nb')).toBe('a b');
    const long = 'x'.repeat(200);
    const preview = notePreview(long, 50);
    expect(preview.length).toBe(50);
    expect(preview.endsWith('…')).toBe(true);
  });

  it('labels provenance for display', () => {
    expect(provenanceLabel('sampled')).toBe('Sampled');
    expect(provenanceLabel('ai_generated')).toBe('AI-generated');
  });
});
