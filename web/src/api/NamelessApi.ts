/**
 * `NamelessApi` — the control-plane contract as a single typed port (the testability seam).
 *
 * This interface is the ONLY thing the UI's hooks and components know about. They never touch
 * `fetch`, a URL, or a backend detail directly. Two implementations satisfy it:
 *   - `HttpNamelessApi`  — the real adapter; talks to the axum control plane over HTTP.
 *   - `MockNamelessApi`  — an in-memory adapter with seeded fixtures; powers dev + every test.
 *
 * Because everything above depends on this interface (injected via React context), the entire app
 * is runnable and testable with NO backend. Swapping the real server in is a one-line change at the
 * composition root (`main.tsx`). This is the ports-and-adapters law applied to the frontend.
 *
 * The methods mirror the control-plane operations the `nameless` CLI exposes (capture, fragments,
 * reference upload/show/attach, stems separate/list, sample add/show, credits), plus two read
 * aggregations the interactive surface needs (`listProjects`, `getProjectGraph`) that the HTTP API
 * exposes as GET endpoints.
 */

import type {
  AddSampleInput,
  AttachReferenceInput,
  AttachReferenceResult,
  CaptureInput,
  CaptureResult,
  Credits,
  FragmentDetail,
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

export interface NamelessApi {
  // ---- projects ----
  /** All projects (newest first). HTTP: `GET /projects`. */
  listProjects(): Promise<Project[]>;
  /** Create a project. HTTP: `POST /projects`. */
  createProject(title: string): Promise<Project>;

  // ---- capture (UI-01) ----
  /** Capture a fragment + intent note. HTTP: `POST /projects/:id/fragments` (multipart). */
  capture(input: CaptureInput): Promise<CaptureResult>;
  /** List fragments, optionally scoped to a project. HTTP: `GET /fragments?project=:id`. */
  listFragments(projectId?: Uuid): Promise<FragmentSummary[]>;
  /** A single fragment's compact summary. HTTP: `GET /fragments/:id`. */
  getFragment(id: Uuid): Promise<FragmentDetail>;

  // ---- reference (UI-02) ----
  /** All uploaded references. HTTP: `GET /references`. */
  listReferences(): Promise<ReferenceListItem[]>;
  /** Upload a finished reference track. HTTP: `POST /references` (multipart). */
  uploadReference(input: ReferenceUploadInput): Promise<ReferenceUploadResult>;
  /** A reference's compact vibe/target summary (analysis null until analyzed). HTTP: `GET /references/:id`. */
  getReferenceSummary(id: Uuid): Promise<ReferenceView>;
  /** Attach a reference to a project as conditioning. HTTP: `POST /projects/:id/references`. */
  attachReference(input: AttachReferenceInput): Promise<AttachReferenceResult>;

  // ---- stem library + sampling (UI-03) ----
  /** Enqueue stem separation for a track. HTTP: `POST /tracks/:id/stems/separate`. */
  separateStems(trackId: Uuid): Promise<{ reference: Uuid; enqueued_job: Uuid }>;
  /** The retained stems of a track. HTTP: `GET /tracks/:id/stems`. */
  listStems(trackId: Uuid): Promise<StemSummary[]>;
  /**
   * Promote a stem to a `sampled` fragment with COMPLETE attribution. HTTP: `POST /projects/:id/samples`.
   * Throws {@link IncompleteAttributionError} if any required attribution field is missing — and in
   * that case nothing is created.
   */
  addSample(input: AddSampleInput): Promise<SampleAddResult>;
  /** A sampled fragment's attribution + rights status. HTTP: `GET /samples/:fragmentId`. */
  getSample(fragmentId: Uuid): Promise<SampleView>;

  // ---- project graph + credits (UI-04) ----
  /** The fragment graph (nodes + lineage edges + per-node key/tempo). HTTP: `GET /projects/:id/graph`. */
  getProjectGraph(projectId: Uuid): Promise<ProjectGraph>;
  /** The project's sample credits sheet. HTTP: `GET /projects/:id/credits`. */
  getCredits(projectId: Uuid): Promise<Credits>;
}
