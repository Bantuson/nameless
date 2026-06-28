/**
 * Stem Library screen (UI-03) — browse a track's retained stems and promote one to an attributed
 * `sampled` fragment. The attribution-completeness gate is enforced by the server and mirrored in the
 * form; "attribution is not permission" is surfaced at the point of action.
 */

import { useEffect, useMemo, useState } from 'react';
import { useActiveProject } from '../ActiveProjectContext';
import { IncompleteAttributionError } from '../api/errors';
import type { SampleAddResult } from '../api/types';
import { AttributionForm, type AttributionFormValues } from '../components/AttributionForm';
import { StemTable } from '../components/StemTable';
import { Banner, Button, ErrorMessage, Field, Loading } from '../components/ui';
import { useReferences } from '../hooks/useReferences';
import { useStemLibrary } from '../hooks/useStemLibrary';
import { NoProjectNotice } from './common';

export function StemLibraryScreen(): JSX.Element {
  const { activeProjectId } = useActiveProject();
  const { references } = useReferences();

  const [trackId, setTrackId] = useState<string | null>(null);
  useEffect(() => {
    if (trackId === null && references.length > 0) setTrackId(references[0].id);
  }, [references, trackId]);

  const { stems, loading, error, separate, addSample } = useStemLibrary(trackId);

  const [selectedStemId, setSelectedStemId] = useState<string | null>(null);
  const [separating, setSeparating] = useState(false);
  const [separateError, setSeparateError] = useState<Error | null>(null);
  const [adding, setAdding] = useState(false);
  const [addResult, setAddResult] = useState<SampleAddResult | null>(null);
  const [addError, setAddError] = useState<Error | null>(null);

  const selectedTrack = useMemo(
    () => references.find((r) => r.id === trackId) ?? null,
    [references, trackId],
  );
  const selectedStem = useMemo(
    () => stems.find((s) => s.id === selectedStemId) ?? null,
    [stems, selectedStemId],
  );

  if (!activeProjectId) return <NoProjectNotice action="add samples to" />;

  async function onSeparate(): Promise<void> {
    setSeparating(true);
    setSeparateError(null);
    try {
      await separate();
    } catch (err) {
      // Surface backend failures (the real control plane can reject/​error here) instead of letting
      // the rejection vanish — the list's `error` only covers the list load, not this action.
      setSeparateError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setSeparating(false);
    }
  }

  async function onAddSample(values: AttributionFormValues): Promise<void> {
    if (!selectedStem || !activeProjectId) return;
    setAdding(true);
    setAddError(null);
    setAddResult(null);
    try {
      const result = await addSample(activeProjectId, {
        stemId: selectedStem.id,
        artist: values.artist,
        startMs: values.startMs,
        endMs: values.endMs,
        rights: values.rights,
        title: values.title,
      });
      setAddResult(result);
      setSelectedStemId(null);
    } catch (err) {
      if (err instanceof IncompleteAttributionError) {
        setAddError(new Error(`Incomplete attribution — missing: ${err.missing.join(', ')}. Nothing was created.`));
      } else {
        setAddError(err instanceof Error ? err : new Error(String(err)));
      }
    } finally {
      setAdding(false);
    }
  }

  return (
    <section className="screen" aria-labelledby="library-title">
      <header className="screen__head">
        <h2 id="library-title">Stem Library</h2>
        <p className="screen__lead">
          Every uploaded track is separated into stems and retained indefinitely. Promote any stem to a
          sample at any time — with complete attribution.
        </p>
      </header>

      <div className="card">
        <div className="screen__section-head">
          <Field label="Track">
            {({ id }) =>
              references.length > 0 ? (
                <select
                  id={id}
                  className="input input--inline"
                  value={trackId ?? ''}
                  onChange={(e) => {
                    setTrackId(e.target.value || null);
                    setSelectedStemId(null);
                    setAddResult(null);
                  }}
                >
                  {references.map((r) => (
                    <option key={r.id} value={r.id}>
                      {(r.title ?? 'Untitled')} {r.artist ? `— ${r.artist}` : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="empty-state">No uploaded tracks yet — upload one on the Reference screen.</span>
              )
            }
          </Field>
          {trackId && stems.length === 0 && !loading ? (
            <Button variant="primary" busy={separating} onClick={onSeparate}>
              Separate into stems
            </Button>
          ) : null}
        </div>

        {loading ? <Loading label="Loading stems…" /> : null}
        {error ? <ErrorMessage error={error} /> : null}
        {separateError ? <ErrorMessage error={separateError} /> : null}
        {!loading && !error && trackId ? (
          <StemTable stems={stems} selectedStemId={selectedStemId} onSelect={setSelectedStemId} />
        ) : null}
      </div>

      {selectedStem && selectedTrack ? (
        <div className="card">
          <AttributionForm
            stem={selectedStem}
            trackId={selectedTrack.id}
            fallbackTitle={selectedTrack.title}
            busy={adding}
            onSubmit={onAddSample}
          />
          {addError ? <ErrorMessage error={addError} /> : null}
        </div>
      ) : null}

      {addResult ? (
        <Banner tone="info" title="Sample added">
          Created sampled fragment <code>{addResult.fragment.slice(0, 8)}</code> from{' '}
          <strong>{addResult.source_title}</strong> — {addResult.source_artist}. It travels the human
          analysis path; its credit appears on the Project screen.
        </Banner>
      ) : null}
    </section>
  );
}
