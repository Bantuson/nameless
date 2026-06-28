/**
 * Reference screen (UI-02) — upload a reference, view its vibe + NON-melodic sonic-target summary,
 * and attach it to the active project as conditioning. The "context, never cloned" boundary is
 * carried by the summary card itself.
 */

import { useEffect, useState, type FormEvent } from 'react';
import { REFERENCE_ROLES, type ReferenceRole } from '../api/types';
import { useActiveProject } from '../ActiveProjectContext';
import { ReferenceSummaryCard } from '../components/ReferenceSummaryCard';
import { Button, ErrorMessage, Field, Loading } from '../components/ui';
import { roleLabel } from '../lib/format';
import { useReferences, useReferenceSummary } from '../hooks/useReferences';

export function ReferenceScreen(): JSX.Element {
  const { activeProjectId } = useActiveProject();
  const { references, loading, error, uploadReference, attachReference } = useReferences();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Default the selection to the first reference once the list loads.
  useEffect(() => {
    if (selectedId === null && references.length > 0) setSelectedId(references[0].id);
  }, [references, selectedId]);

  const summary = useReferenceSummary(selectedId);

  // upload form state
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<Error | null>(null);
  const [formKey, setFormKey] = useState(0);

  // attach state
  const [role, setRole] = useState<ReferenceRole>('vibe');
  const [attachMsg, setAttachMsg] = useState<string | null>(null);
  const [attachError, setAttachError] = useState<Error | null>(null);
  const [attachBusy, setAttachBusy] = useState(false);

  async function onUpload(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setUploadError(null);
    try {
      const result = await uploadReference({
        file,
        fileName: file.name,
        title: title.trim() || undefined,
        artist: artist.trim() || undefined,
      });
      setSelectedId(result.reference);
      setFile(null);
      setTitle('');
      setArtist('');
      setFormKey((k) => k + 1);
    } catch (err) {
      setUploadError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }

  async function onAttach(): Promise<void> {
    if (!selectedId || !activeProjectId) return;
    setAttachBusy(true);
    setAttachError(null);
    setAttachMsg(null);
    try {
      await attachReference(selectedId, activeProjectId, role);
      setAttachMsg(`Attached as ${roleLabel(role).toLowerCase()} context.`);
    } catch (err) {
      setAttachError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setAttachBusy(false);
    }
  }

  return (
    <section className="screen" aria-labelledby="reference-title">
      <header className="screen__head">
        <h2 id="reference-title">Reference</h2>
        <p className="screen__lead">
          Upload a finished song you love. The system extracts its vibe and measurable non-melodic
          targets as conditioning — never its melody, chords, or structure.
        </p>
      </header>

      <form className="card form" onSubmit={onUpload} aria-label="Upload a reference track">
        <Field label="Reference audio" hint="A finished track (wav / mp3 / flac / m4a).">
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
        <div className="form__row">
          <Field label="Title (optional)" hint="For credits / UI only — never a conditioning target.">
            {({ id, describedBy }) => (
              <input id={id} aria-describedby={describedBy} className="input" value={title} onChange={(e) => setTitle(e.target.value)} autoComplete="off" />
            )}
          </Field>
          <Field label="Artist (optional)" hint="For credits / UI only.">
            {({ id, describedBy }) => (
              <input id={id} aria-describedby={describedBy} className="input" value={artist} onChange={(e) => setArtist(e.target.value)} autoComplete="off" />
            )}
          </Field>
        </div>
        <div className="form__actions">
          <Button type="submit" variant="primary" busy={busy} disabled={file === null || busy}>
            Upload reference
          </Button>
        </div>
        {uploadError ? <ErrorMessage error={uploadError} /> : null}
      </form>

      <section className="screen__section" aria-label="Reference summary">
        <div className="screen__section-head">
          <h3 className="screen__subtitle">Vibe &amp; sonic targets</h3>
          {references.length > 0 ? (
            <Field label="Reference">
              {({ id }) => (
                <select
                  id={id}
                  className="input input--inline"
                  value={selectedId ?? ''}
                  onChange={(e) => setSelectedId(e.target.value || null)}
                >
                  {references.map((r) => (
                    <option key={r.id} value={r.id}>
                      {(r.title ?? 'Untitled')} {r.artist ? `— ${r.artist}` : ''}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          ) : null}
        </div>

        {loading ? <Loading label="Loading references…" /> : null}
        {error ? <ErrorMessage error={error} /> : null}
        {!loading && references.length === 0 ? (
          <p className="empty-state">No references uploaded yet. Upload one above.</p>
        ) : null}

        {summary.loading ? <Loading label="Loading summary…" /> : null}
        {summary.error ? <ErrorMessage error={summary.error} /> : null}
        {summary.reference ? <ReferenceSummaryCard reference={summary.reference} /> : null}

        {summary.reference ? (
          <div className="card attach" aria-label="Attach reference to project">
            <h4 className="screen__subtitle">Attach as conditioning</h4>
            {activeProjectId ? (
              <div className="attach__controls">
                <Field label="Role" hint="Vibe leans on atmosphere; sonic target leans on the measurable numbers.">
                  {({ id, describedBy }) => (
                    <select
                      id={id}
                      aria-describedby={describedBy}
                      className="input input--inline"
                      value={role}
                      onChange={(e) => setRole(e.target.value as ReferenceRole)}
                    >
                      {REFERENCE_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {roleLabel(r)}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Button variant="secondary" busy={attachBusy} onClick={onAttach}>
                  Attach to project
                </Button>
              </div>
            ) : (
              <p className="empty-state">Select a project in the header to attach this reference.</p>
            )}
            {attachMsg ? (
              <p className="message message--ok" role="status">
                {attachMsg}
              </p>
            ) : null}
            {attachError ? <ErrorMessage error={attachError} /> : null}
          </div>
        ) : null}
      </section>
    </section>
  );
}
