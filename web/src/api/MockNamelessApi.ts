/**
 * `MockNamelessApi` — an in-memory implementation of the {@link NamelessApi} port.
 *
 * This is the engine that lets the entire UI run and be tested with NO backend. It holds the seeded
 * world (`createSeedState`) and implements every contract method against it, enforcing the same
 * invariants the real control plane does — most importantly the attribution-completeness gate
 * (`addSample` throws {@link IncompleteAttributionError} and creates nothing when a field is missing).
 *
 * It is deliberately deterministic: state is seeded from fixed fixtures and ids come from an
 * injectable generator (default `crypto.randomUUID`), so tests start from a known world. Reads return
 * deep copies so a caller cannot accidentally mutate internal state (avoids referential surprises in
 * React and keeps the fake honest).
 *
 * Where the mock simplifies (and the real backend differs), it is called out in a comment:
 *   - reference analysis + stem separation are job-driven (async) on the server; the mock simulates
 *     them as having completed immediately so the UI flows end-to-end without a worker.
 */

import type { NamelessApi } from './NamelessApi';
import {
  buildSixStems,
  createSeedState,
  synthesizeAnalysis,
  type AttributionRecord,
  type FragmentRecord,
  type MockState,
} from './fixtures';
import { IncompleteAttributionError, NotFoundError, ApiError } from './errors';
import { missingAttributionFields } from '../lib/attribution';
import { renderCreditsSheet } from '../lib/credits';
import { deriveEdges } from '../lib/graph';
import { newId, pseudoContentHash } from '../lib/ids';
import { rightsNote } from '../lib/rights';
import type {
  AddSampleInput,
  AttachReferenceInput,
  AttachReferenceResult,
  CaptureInput,
  CaptureResult,
  CreditSample,
  Credits,
  FragmentDetail,
  FragmentNode,
  FragmentSummary,
  Project,
  ProjectGraph,
  ReferenceListItem,
  ReferenceUploadInput,
  ReferenceUploadResult,
  ReferenceView,
  SampleAddResult,
  SampleView,
  StemSummary,
  Uuid,
} from './types';

export interface MockNamelessApiOptions {
  /** Override the seeded state (e.g. an empty world for a specific test). */
  state?: MockState;
  /** Override the id generator for deterministic tests. */
  idGen?: () => string;
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

export class MockNamelessApi implements NamelessApi {
  private state: MockState;
  private readonly idGen: () => string;

  constructor(opts: MockNamelessApiOptions = {}) {
    this.state = opts.state ?? createSeedState();
    this.idGen = opts.idGen ?? newId;
  }

  // ---- projects ----

  async listProjects(): Promise<Project[]> {
    return clone(
      [...this.state.projects].sort((a, b) => b.created_at_ms - a.created_at_ms),
    );
  }

  async createProject(title: string): Promise<Project> {
    const trimmed = title.trim();
    if (trimmed === '') throw new ApiError('project title is required', 400);
    const project: Project = { id: this.idGen(), title: trimmed, created_at_ms: Date.now() };
    this.state.projects.push(project);
    return clone(project);
  }

  // ---- capture (UI-01) ----

  async capture(input: CaptureInput): Promise<CaptureResult> {
    if (input.note.trim() === '') throw new ApiError('an intent note is required', 400);
    this.requireProject(input.projectId);
    const audio_uri = pseudoContentHash(`${input.fileName}:${input.file.size}`);
    const record: FragmentRecord = {
      id: this.idGen(),
      project_id: input.projectId,
      kind: input.kind,
      provenance: 'human_recorded',
      state: 'captured',
      audio_uri,
      duration_ms: null,
      sample_rate: null,
      note: input.note,
      parent_fragment_id: null,
      key: null,
      tempo_bpm: null,
      created_at_ms: Date.now(),
    };
    this.state.fragments.push(record);
    return { fragment: record.id, state: 'captured', audio_uri, enqueued_job: this.idGen() };
  }

  async listFragments(projectId?: Uuid): Promise<FragmentSummary[]> {
    const rows = this.state.fragments.filter((f) => !projectId || f.project_id === projectId);
    return rows.map((f) => ({ id: f.id, state: f.state, kind: f.kind, note: f.note }));
  }

  async getFragment(id: Uuid): Promise<FragmentDetail> {
    const f = this.state.fragments.find((x) => x.id === id);
    if (!f) throw new NotFoundError(`fragment ${id}`);
    return this.toDetail(f);
  }

  // ---- reference (UI-02) ----

  async listReferences(): Promise<ReferenceListItem[]> {
    return this.state.references.map((r) => ({
      id: r.id,
      title: r.title,
      artist: r.artist,
      analyzed: r.analysis !== null,
    }));
  }

  async uploadReference(input: ReferenceUploadInput): Promise<ReferenceUploadResult> {
    const audio_uri = pseudoContentHash(`${input.fileName}:${input.file.size}`);
    const id = this.idGen();
    // The real analyzer runs as a job; the mock simulates it completing immediately so the summary
    // is viewable at once. It is NON-melodic by construction (synthesizeAnalysis cannot emit melody).
    const analysis = synthesizeAnalysis(`${input.fileName}:${input.title ?? ''}`);
    this.state.references.push({
      id,
      audio_uri,
      title: input.title ?? null,
      artist: input.artist ?? null,
      duration_ms: null,
      sample_rate: null,
      analysis,
    });
    return { reference: id, audio_uri, enqueued_job: this.idGen() };
  }

  async getReferenceSummary(id: Uuid): Promise<ReferenceView> {
    const r = this.state.references.find((x) => x.id === id);
    if (!r) throw new NotFoundError(`reference ${id}`);
    return clone({
      id: r.id,
      audio_uri: r.audio_uri,
      title: r.title,
      artist: r.artist,
      duration_ms: r.duration_ms,
      sample_rate: r.sample_rate,
      analysis: r.analysis,
    });
  }

  async attachReference(input: AttachReferenceInput): Promise<AttachReferenceResult> {
    if (!this.state.references.some((r) => r.id === input.referenceId)) {
      throw new NotFoundError(`reference ${input.referenceId}`);
    }
    this.requireProject(input.projectId);
    const existing = this.state.projectReferences.find(
      (p) => p.projectId === input.projectId && p.referenceId === input.referenceId,
    );
    if (existing) existing.role = input.role;
    else
      this.state.projectReferences.push({
        projectId: input.projectId,
        referenceId: input.referenceId,
        role: input.role,
      });
    return { reference: input.referenceId, project: input.projectId, role: input.role };
  }

  // ---- stem library + sampling (UI-03) ----

  async separateStems(trackId: Uuid): Promise<{ reference: Uuid; enqueued_job: Uuid }> {
    if (!this.state.references.some((r) => r.id === trackId)) {
      throw new NotFoundError(`reference ${trackId}`);
    }
    const already = this.state.stems.some((s) => s.reference_track_id === trackId);
    if (!already) {
      const ref = this.state.references.find((r) => r.id === trackId)!;
      // Real separation is a Demucs job; the mock materializes the retained stem rows immediately.
      this.state.stems.push(...buildSixStems(trackId, ref.duration_ms, this.idGen));
    }
    return { reference: trackId, enqueued_job: this.idGen() };
  }

  async listStems(trackId: Uuid): Promise<StemSummary[]> {
    if (!this.state.references.some((r) => r.id === trackId)) {
      throw new NotFoundError(`reference ${trackId}`);
    }
    return this.state.stems
      .filter((s) => s.reference_track_id === trackId)
      .map((s) => ({
        id: s.id,
        stem_type: s.stem_type,
        separator: s.separator,
        audio_uri: s.audio_uri,
        duration_ms: s.duration_ms,
      }));
  }

  async addSample(input: AddSampleInput): Promise<SampleAddResult> {
    const stem = this.state.stems.find((s) => s.id === input.stemId);
    if (!stem) throw new NotFoundError(`stem ${input.stemId}`);
    this.requireProject(input.projectId);

    const track = this.state.references.find((r) => r.id === stem.reference_track_id);
    const title = input.title ?? track?.title ?? undefined;

    // THE HARD GATE — identical rule to the Rust `PartialAttribution::into_complete`.
    const missing = missingAttributionFields({
      sourceTrackId: stem.reference_track_id,
      stemId: stem.id,
      sourceTitle: title,
      sourceArtist: input.artist,
      stemType: stem.stem_type,
      startMs: input.startMs,
      endMs: input.endMs,
      rights: input.rights,
    });
    if (missing.length > 0) throw new IncompleteAttributionError(missing);

    // Validated: every field present. Create the sampled fragment + its attribution row.
    const completeTitle = (title as string).trim();
    const completeArtist = input.artist.trim();
    const fragment: FragmentRecord = {
      id: this.idGen(),
      project_id: input.projectId,
      kind: 'stem',
      provenance: 'sampled',
      state: 'captured',
      audio_uri: stem.audio_uri,
      duration_ms: input.endMs - input.startMs,
      sample_rate: null,
      note: `sampled ${stem.stem_type} from "${completeTitle}" — ${completeArtist}`,
      parent_fragment_id: null,
      key: null,
      tempo_bpm: null,
      created_at_ms: Date.now(),
    };
    this.state.fragments.push(fragment);

    const attribution: AttributionRecord = {
      fragment_id: fragment.id,
      project_id: input.projectId,
      source_track_id: stem.reference_track_id,
      stem_id: stem.id,
      source_title: completeTitle,
      source_artist: completeArtist,
      stem_type: stem.stem_type,
      start_ms: input.startMs,
      end_ms: input.endMs,
      rights: input.rights,
    };
    this.state.attributions.push(attribution);

    return {
      fragment: fragment.id,
      provenance: 'sampled',
      state: 'captured',
      source_title: completeTitle,
      source_artist: completeArtist,
      stem_type: stem.stem_type,
      start_ms: input.startMs,
      end_ms: input.endMs,
      rights: input.rights,
      enqueued_job: this.idGen(),
    };
  }

  async getSample(fragmentId: Uuid): Promise<SampleView> {
    const a = this.state.attributions.find((x) => x.fragment_id === fragmentId);
    if (!a) throw new NotFoundError(`sample attribution for fragment ${fragmentId}`);
    return {
      fragment: a.fragment_id,
      project: a.project_id,
      source_track: a.source_track_id,
      stem: a.stem_id,
      source_title: a.source_title,
      source_artist: a.source_artist,
      stem_type: a.stem_type,
      start_ms: a.start_ms,
      end_ms: a.end_ms,
      rights: a.rights,
      rights_note: rightsNote(a.rights),
      attribution_is_not_permission: true,
    };
  }

  // ---- project graph + credits (UI-04) ----

  async getProjectGraph(projectId: Uuid): Promise<ProjectGraph> {
    const nodes: FragmentNode[] = this.state.fragments
      .filter((f) => f.project_id === projectId)
      .map((f) => ({
        id: f.id,
        kind: f.kind,
        provenance: f.provenance,
        state: f.state,
        note: f.note,
        key: f.key,
        tempo_bpm: f.tempo_bpm,
        parent_fragment_id: f.parent_fragment_id,
      }));
    return clone({ projectId, nodes, edges: deriveEdges(nodes) });
  }

  async getCredits(projectId: Uuid): Promise<Credits> {
    const project = this.state.projects.find((p) => p.id === projectId);
    const title = project?.title ?? projectId;
    const samples: CreditSample[] = this.state.attributions
      .filter((a) => a.project_id === projectId)
      .map((a) => ({
        fragment: a.fragment_id,
        source_title: a.source_title,
        source_artist: a.source_artist,
        stem_type: a.stem_type,
        start_ms: a.start_ms,
        end_ms: a.end_ms,
        rights: a.rights,
      }));
    return {
      project: title,
      attribution_is_not_permission: true,
      samples: clone(samples),
      markdown: renderCreditsSheet(title, samples),
    };
  }

  // ---- internals ----

  private requireProject(projectId: Uuid): void {
    if (!this.state.projects.some((p) => p.id === projectId)) {
      throw new NotFoundError(`project ${projectId}`);
    }
  }

  private toDetail(f: FragmentRecord): FragmentDetail {
    return {
      id: f.id,
      project_id: f.project_id,
      kind: f.kind,
      provenance: f.provenance,
      state: f.state,
      duration_ms: f.duration_ms,
      sample_rate: f.sample_rate,
      audio_uri: f.audio_uri,
      note: f.note,
      parent_fragment_id: f.parent_fragment_id,
    };
  }
}
