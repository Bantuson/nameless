/**
 * The "Add as sample" attribution form (UI-03) — a controlled presentational component.
 *
 * It owns local form state and calls `onSubmit`; it never touches the client (the screen wires that).
 * It mirrors the server's completeness gate on the client using the SAME pure rule
 * (`missingAttributionFields`), so the submit button stays disabled — and the exact missing fields are
 * named — until the attribution is complete. The server re-validates authoritatively; this just makes
 * the gate visible before the round-trip. It always surfaces that **attribution is not permission**.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { RightsStatus, StemSummary } from '../api/types';
import { RIGHTS_STATUSES } from '../api/types';
import { missingAttributionFields } from '../lib/attribution';
import { stemTypeLabel } from '../lib/format';
import { rightsLabel, rightsNote } from '../lib/rights';
import { Banner, Button, Field } from './ui';

export interface AttributionFormValues {
  artist: string;
  startMs: number;
  endMs: number;
  rights: RightsStatus;
  title?: string;
}

const FIELD_LABELS: Record<string, string> = {
  source_track: 'source track',
  stem: 'stem',
  source_title: 'source title',
  source_artist: 'artist',
  stem_type: 'stem type',
  time_range: 'time range',
  rights: 'rights status',
};

export function AttributionForm({
  stem,
  trackId,
  fallbackTitle,
  busy,
  onSubmit,
}: {
  stem: StemSummary;
  trackId: string;
  fallbackTitle: string | null;
  busy: boolean;
  onSubmit: (values: AttributionFormValues) => void;
}): JSX.Element {
  const [artist, setArtist] = useState('');
  const [title, setTitle] = useState('');
  const [startMs, setStartMs] = useState('');
  const [endMs, setEndMs] = useState('');
  const [rights, setRights] = useState<RightsStatus | ''>('');

  // A11y (IN-03): when this form is revealed (it mounts on stem selection) move focus to it, so the
  // change of context is announced rather than leaving focus stranded on the stem table above.
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    formRef.current?.focus();
  }, []);

  const startNum = startMs === '' ? null : Number(startMs);
  const endNum = endMs === '' ? null : Number(endMs);
  const effectiveTitle = (title.trim() || fallbackTitle || '').trim();

  const missing = missingAttributionFields({
    sourceTrackId: trackId,
    stemId: stem.id,
    sourceTitle: effectiveTitle,
    sourceArtist: artist,
    stemType: stem.stem_type,
    startMs: startNum,
    endMs: endNum,
    rights: rights || null,
  });
  const complete = missing.length === 0;

  function handleSubmit(e: FormEvent): void {
    e.preventDefault();
    if (!complete || rights === '') return;
    onSubmit({
      artist: artist.trim(),
      startMs: startNum as number,
      endMs: endNum as number,
      rights,
      title: title.trim() ? title.trim() : undefined,
    });
  }

  return (
    <form
      ref={formRef}
      tabIndex={-1}
      className="attr-form"
      onSubmit={handleSubmit}
      aria-label={`Attribute the ${stemTypeLabel(stem.stem_type)} stem`}
    >
      <p className="attr-form__lead">
        Promoting the <strong>{stemTypeLabel(stem.stem_type)}</strong> stem to an attributed sample.
        Every field below is required — an incompletely-credited sample cannot be created.
      </p>

      <Field
        label="Source artist"
        hint="Who made the original recording."
      >
        {({ id, describedBy }) => (
          <input
            id={id}
            aria-describedby={describedBy}
            className="input"
            value={artist}
            onChange={(e) => setArtist(e.target.value)}
            autoComplete="off"
          />
        )}
      </Field>

      <Field
        label="Source title"
        hint={fallbackTitle ? `Defaults to the track title "${fallbackTitle}" if left blank.` : 'The source track title.'}
      >
        {({ id, describedBy }) => (
          <input
            id={id}
            aria-describedby={describedBy}
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={fallbackTitle ?? ''}
            autoComplete="off"
          />
        )}
      </Field>

      <div className="attr-form__range">
        <Field label="Start (ms)" hint="Where the slice begins.">
          {({ id, describedBy }) => (
            <input
              id={id}
              aria-describedby={describedBy}
              className="input"
              type="number"
              min={0}
              inputMode="numeric"
              value={startMs}
              onChange={(e) => setStartMs(e.target.value)}
            />
          )}
        </Field>
        <Field label="End (ms)" hint="Must be greater than start.">
          {({ id, describedBy }) => (
            <input
              id={id}
              aria-describedby={describedBy}
              className="input"
              type="number"
              min={0}
              inputMode="numeric"
              value={endMs}
              onChange={(e) => setEndMs(e.target.value)}
            />
          )}
        </Field>
      </div>

      <Field label="Rights status" hint="Honest from day one — recording the status is not clearance.">
        {({ id, describedBy }) => (
          <select
            id={id}
            aria-describedby={describedBy}
            className="input"
            value={rights}
            onChange={(e) => setRights(e.target.value as RightsStatus | '')}
          >
            <option value="">Choose…</option>
            {RIGHTS_STATUSES.map((r) => (
              <option key={r} value={r}>
                {rightsLabel(r)}
              </option>
            ))}
          </select>
        )}
      </Field>

      {rights !== '' ? <p className="attr-form__rights-note">{rightsNote(rights)}</p> : null}

      <div className="attr-form__missing" aria-live="polite">
        {complete ? (
          <p className="attr-form__ok">All required fields present.</p>
        ) : (
          <p className="attr-form__todo">
            Still required: {missing.map((m) => FIELD_LABELS[m] ?? m).join(', ')}.
          </p>
        )}
      </div>

      <Banner tone="warn" title="Attribution is not permission">
        Crediting a source does not make using it legal. Clear copyrighted or unknown samples before
        publishing any output that contains them.
      </Banner>

      <Button type="submit" variant="primary" busy={busy} disabled={!complete}>
        Add as sample
      </Button>
    </form>
  );
}
