/**
 * The client-interface CONTRACT test. Exercises every `NamelessApi` method against the in-memory
 * mock and asserts the compact-contract invariants — most importantly the attribution gate
 * (incomplete → throws and creates nothing) and the absence of any melodic/array field in the
 * reference summary. The same assertions would hold against a conformant `HttpNamelessApi`.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { MockNamelessApi } from './MockNamelessApi';
import { IncompleteAttributionError, NotFoundError } from './errors';
import { DEMO_PROJECT_ID, DEMO_REFERENCE_ID } from './fixtures';

let api: MockNamelessApi;

beforeEach(() => {
  api = new MockNamelessApi();
});

describe('projects', () => {
  it('lists the seeded project and creates new ones', async () => {
    const projects = await api.listProjects();
    expect(projects.some((p) => p.id === DEMO_PROJECT_ID && p.title === 'Late Night Tape')).toBe(true);

    const created = await api.createProject('New Tape');
    expect(created.title).toBe('New Tape');
    expect((await api.listProjects()).some((p) => p.id === created.id)).toBe(true);
  });

  it('rejects a blank project title', async () => {
    await expect(api.createProject('   ')).rejects.toThrow();
  });
});

describe('capture (UI-01)', () => {
  it('captures a fragment and lists it by id/state', async () => {
    const before = (await api.listFragments(DEMO_PROJECT_ID)).length;
    const result = await api.capture({
      projectId: DEMO_PROJECT_ID,
      note: 'a new hum idea',
      kind: 'melody',
      file: new Blob(['fake-audio']),
      fileName: 'hum.wav',
    });
    expect(result.state).toBe('captured');
    expect(result.audio_uri).toMatch(/^sha256:/);

    const after = await api.listFragments(DEMO_PROJECT_ID);
    expect(after.length).toBe(before + 1);
    expect(after.some((f) => f.id === result.fragment && f.note === 'a new hum idea')).toBe(true);
  });

  it('requires an intent note', async () => {
    await expect(
      api.capture({ projectId: DEMO_PROJECT_ID, note: '  ', kind: 'hook', file: new Blob(['x']), fileName: 'x.wav' }),
    ).rejects.toThrow();
  });

  it('throws NotFound for an unknown fragment', async () => {
    await expect(api.getFragment('does-not-exist')).rejects.toBeInstanceOf(NotFoundError);
  });
});

describe('reference (UI-02)', () => {
  it('returns a NON-melodic summary with the embedding dimension but no vector or melody', async () => {
    const view = await api.getReferenceSummary(DEMO_REFERENCE_ID);
    expect(view.analysis).not.toBeNull();
    const analysis = view.analysis!;
    expect(analysis.genre).toBe('amapiano');
    expect(analysis.tempo_bpm_min).toBeGreaterThan(0);
    expect(analysis.embedding_dim).toBe(512);
    expect(analysis.tonal_balance).toHaveLength(5);

    // The compact-contract invariant: no melodic / array-vector field is present.
    const keys = Object.keys(analysis);
    for (const forbidden of ['f0', 'chroma', 'chroma_mean', 'melody', 'key', 'chord', 'chords', 'structure', 'midi', 'pitch', 'vector', 'embedding']) {
      expect(keys).not.toContain(forbidden);
    }
  });

  it('uploads a reference and then returns its analyzed summary', async () => {
    const up = await api.uploadReference({ file: new Blob(['song']), fileName: 'ref.wav', title: 'Test Ref', artist: 'Someone' });
    const view = await api.getReferenceSummary(up.reference);
    expect(view.title).toBe('Test Ref');
    expect(view.analysis).not.toBeNull();

    const list = await api.listReferences();
    expect(list.some((r) => r.id === up.reference && r.analyzed)).toBe(true);
  });

  it('attaches a reference to a project', async () => {
    const res = await api.attachReference({ referenceId: DEMO_REFERENCE_ID, projectId: DEMO_PROJECT_ID, role: 'sonic_target' });
    expect(res.role).toBe('sonic_target');
  });
});

describe('stem library + sampling (UI-03)', () => {
  it('lists the retained stems of the seeded track', async () => {
    const stems = await api.listStems(DEMO_REFERENCE_ID);
    expect(stems.length).toBe(6);
    expect(stems.map((s) => s.stem_type)).toContain('piano');
    expect(stems[0].separator).toContain('htdemucs');
  });

  it('separates an uploaded track idempotently', async () => {
    const up = await api.uploadReference({ file: new Blob(['s']), fileName: 's.wav' });
    expect(await api.listStems(up.reference)).toHaveLength(0);
    await api.separateStems(up.reference);
    const once = await api.listStems(up.reference);
    expect(once.length).toBe(6);
    await api.separateStems(up.reference);
    expect(await api.listStems(up.reference)).toHaveLength(6); // no duplication
  });

  it('THE GATE: rejects an incomplete sample and creates nothing', async () => {
    const stems = await api.listStems(DEMO_REFERENCE_ID);
    const vocals = stems.find((s) => s.stem_type === 'vocals')!;
    const fragsBefore = (await api.listFragments(DEMO_PROJECT_ID)).length;
    const creditsBefore = (await api.getCredits(DEMO_PROJECT_ID)).samples.length;

    const attempt = api.addSample({
      stemId: vocals.id,
      projectId: DEMO_PROJECT_ID,
      artist: '   ', // whitespace-only artist = missing
      startMs: 1000,
      endMs: 1000, // zero span = missing time range
      rights: 'unknown',
      // title falls back to the track title, so source_title is NOT missing
    });
    await expect(attempt).rejects.toBeInstanceOf(IncompleteAttributionError);
    await attempt.catch((e: IncompleteAttributionError) => {
      expect(e.missing).toContain('source_artist');
      expect(e.missing).toContain('time_range');
    });

    // Nothing was created.
    expect((await api.listFragments(DEMO_PROJECT_ID)).length).toBe(fragsBefore);
    expect((await api.getCredits(DEMO_PROJECT_ID)).samples.length).toBe(creditsBefore);
  });

  it('adds a complete sample and surfaces it in credits', async () => {
    const stems = await api.listStems(DEMO_REFERENCE_ID);
    const piano = stems.find((s) => s.stem_type === 'piano')!;
    const creditsBefore = (await api.getCredits(DEMO_PROJECT_ID)).samples.length;

    const result = await api.addSample({
      stemId: piano.id,
      projectId: DEMO_PROJECT_ID,
      artist: 'Esther Vale',
      startMs: 30_000,
      endMs: 36_000,
      rights: 'royalty_free',
      title: 'Midnight Reverie',
    });
    expect(result.provenance).toBe('sampled');
    expect(result.stem_type).toBe('piano');

    const credits = await api.getCredits(DEMO_PROJECT_ID);
    expect(credits.samples.length).toBe(creditsBefore + 1);
    expect(credits.attribution_is_not_permission).toBe(true);
    expect(credits.markdown).toContain('Attribution is not permission');

    const sample = await api.getSample(result.fragment);
    expect(sample.attribution_is_not_permission).toBe(true);
    expect(sample.rights_note).toMatch(/royalty-free/i);
  });
});

describe('project graph + credits (UI-04)', () => {
  it('returns nodes with key/tempo on analyzed fragments and a lineage edge', async () => {
    const graph = await api.getProjectGraph(DEMO_PROJECT_ID);
    expect(graph.nodes.length).toBeGreaterThanOrEqual(4);

    const analyzed = graph.nodes.find((n) => n.key === 'C:min');
    expect(analyzed?.tempo_bpm).toBe(112);

    // The seeded derived fragment forms an edge from its parent hum.
    expect(graph.edges.length).toBeGreaterThanOrEqual(1);
    const derived = graph.nodes.find((n) => n.provenance === 'derived');
    expect(derived?.parent_fragment_id).not.toBeNull();
    expect(graph.edges.some((e) => e.to === derived?.id)).toBe(true);
  });

  it('lists the seeded sample in credits with the permission notice', async () => {
    const credits = await api.getCredits(DEMO_PROJECT_ID);
    expect(credits.samples.some((s) => s.source_artist.includes('Esther Vale'))).toBe(true);
    expect(credits.attribution_is_not_permission).toBe(true);
  });
});
