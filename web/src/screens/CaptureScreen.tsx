/**
 * Capture screen (UI-01) — capture/upload a fragment + intent note, then see it listed by id/state.
 *
 * Composition only: it wires the `useFragments` hook to the pure `FragmentList` + a capture form.
 * No client calls, no fetch — the hook is the seam.
 */

import { useRef, useState, type FormEvent } from 'react';
import { FRAGMENT_KINDS, type FragmentKind } from '../api/types';
import { useActiveProject } from '../ActiveProjectContext';
import { FragmentList } from '../components/FragmentList';
import { Button, ErrorMessage, Field, Loading } from '../components/ui';
import { kindLabel, shortId } from '../lib/format';
import { useFragments } from '../hooks/useFragments';
import { NoProjectNotice } from './common';

export function CaptureScreen(): JSX.Element {
  const { activeProjectId } = useActiveProject();
  const { fragments, loading, error, capture } = useFragments(activeProjectId);

  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');
  const [kind, setKind] = useState<FragmentKind>('hook');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<Error | null>(null);
  const [lastCaptured, setLastCaptured] = useState<string | null>(null);
  const [formKey, setFormKey] = useState(0);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  if (!activeProjectId) return <NoProjectNotice action="capture into" />;

  const canSubmit = file !== null && note.trim() !== '' && !busy;

  async function onSubmit(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (!file || note.trim() === '') return;
    setBusy(true);
    setSubmitError(null);
    setLastCaptured(null);
    try {
      const result = await capture({ note: note.trim(), kind, file, fileName: file.name });
      setLastCaptured(result.fragment);
      setNote('');
      setFile(null);
      setFormKey((k) => k + 1);
      // A11y (IN-03): remounting the file input (formKey) drops focus to <body>. Return focus to the
      // note field — the natural next control for capturing another fragment.
      noteRef.current?.focus();
    } catch (err) {
      setSubmitError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="screen" aria-labelledby="capture-title">
      <header className="screen__head">
        <h2 id="capture-title">Capture</h2>
        <p className="screen__lead">
          Capture a musical fragment — a hum, a hook, a beat, a rhythm — and annotate it with intent.
          It enters the graph in the <code>captured</code> state and analysis is enqueued.
        </p>
      </header>

      <form className="card form" onSubmit={onSubmit} aria-label="Capture a fragment">
        <Field label="Audio file" hint="A short recording (wav / mp3 / flac / m4a). The bytes are stored by content hash, never inline.">
          {({ id, describedBy }) => (
            <input
              key={formKey}
              id={id}
              aria-describedby={describedBy}
              className="input input--file"
              type="file"
              accept="audio/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          )}
        </Field>

        <Field label="Intent note" hint='What this fragment is for, e.g. "chorus hook, sits over the 2nd drop".'>
          {({ id, describedBy }) => (
            <textarea
              ref={noteRef}
              id={id}
              aria-describedby={describedBy}
              className="input input--textarea"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
        </Field>

        <Field label="Kind" hint="The kind of musical material.">
          {({ id, describedBy }) => (
            <select
              id={id}
              aria-describedby={describedBy}
              className="input"
              value={kind}
              onChange={(e) => setKind(e.target.value as FragmentKind)}
            >
              {FRAGMENT_KINDS.map((k) => (
                <option key={k} value={k}>
                  {kindLabel(k)}
                </option>
              ))}
            </select>
          )}
        </Field>

        <div className="form__actions">
          <Button type="submit" variant="primary" busy={busy} disabled={!canSubmit}>
            Capture fragment
          </Button>
        </div>

        {submitError ? <ErrorMessage error={submitError} /> : null}
        {lastCaptured ? (
          <p className="message message--ok" role="status">
            Captured fragment <code>{shortId(lastCaptured)}</code> — feature extraction enqueued.
          </p>
        ) : null}
      </form>

      <section className="screen__section" aria-label="Fragments in this project">
        <h3 className="screen__subtitle">Fragments</h3>
        {loading ? <Loading label="Loading fragments…" /> : null}
        {error ? <ErrorMessage error={error} /> : null}
        {!loading && !error ? <FragmentList fragments={fragments} /> : null}
      </section>
    </section>
  );
}
