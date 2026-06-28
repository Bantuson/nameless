/**
 * The compact control-plane contract, as TypeScript types.
 *
 * Every type here mirrors, field-for-field, the JSON the Rust CLI emits under `--json`
 * (`crates/nameless-cli/src/output.rs`) and the worker's compact read models
 * (`workers/.../domain/models.py`). The defining property is what is ABSENT: there is no field
 * anywhere below that can hold a waveform, a feature array, or an embedding vector. The contract
 * carries ids, labels, scalars, and the embedding *dimension* (a count) — never the vector. That is
 * the PRD §12 token-strategy boundary, expressed at the type level on the client just as it is on
 * the server: the UI physically cannot render a raw array because no type can carry one.
 *
 * Enum string unions use the canonical snake_case labels the DB + serde use, so a value that
 * round-trips through the real backend is identical to the one the mock produces.
 */

/** A UUID, as the string the control plane prints. */
export type Uuid = string;

// ---------------------------------------------------------------------------------------------
// Enums (canonical snake_case labels — match the Rust/Postgres enums)
// ---------------------------------------------------------------------------------------------

/** `FragmentKind` — the kind of musical material a fragment holds. */
export type FragmentKind =
  | 'melody'
  | 'hook'
  | 'beat'
  | 'rhythm'
  | 'chord'
  | 'pad'
  | 'adlib'
  | 'stem'
  | 'full';

export const FRAGMENT_KINDS: readonly FragmentKind[] = [
  'melody',
  'hook',
  'beat',
  'rhythm',
  'chord',
  'pad',
  'adlib',
  'stem',
  'full',
];

/** `Provenance` — where a fragment's audio came from (drives its lifecycle path). */
export type Provenance = 'human_recorded' | 'ai_generated' | 'derived' | 'sampled';

/** `FragmentState` — the typed lifecycle state (the human path + the AI eval-gate path). */
export type FragmentState =
  | 'captured'
  | 'analyzing'
  | 'analyzed'
  | 'placed'
  | 'mixed'
  | 'rendered'
  | 'requested'
  | 'generating'
  | 'generated'
  | 'evaluating'
  | 'promoted'
  | 'rejected';

/** `StemType` — the fixed Demucs output vocabulary (htdemucs_6s adds piano + guitar). */
export type StemType = 'vocals' | 'drums' | 'bass' | 'other' | 'piano' | 'guitar';

export const STEM_TYPES: readonly StemType[] = ['vocals', 'drums', 'bass', 'other', 'piano', 'guitar'];

/** `ReferenceRole` — what a reference steers for a project (atmosphere vs measurable targets). */
export type ReferenceRole = 'vibe' | 'sonic_target';

export const REFERENCE_ROLES: readonly ReferenceRole[] = ['vibe', 'sonic_target'];

/** `RightsStatus` — the legal/clearance status of a sample's source. Attribution is NOT permission. */
export type RightsStatus = 'copyrighted_uncleared' | 'royalty_free' | 'own_work' | 'unknown';

export const RIGHTS_STATUSES: readonly RightsStatus[] = [
  'copyrighted_uncleared',
  'royalty_free',
  'own_work',
  'unknown',
];

/** `AttributionField` — one named field that can be missing when validating a sample's attribution. */
export type AttributionField =
  | 'source_track'
  | 'stem'
  | 'source_title'
  | 'source_artist'
  | 'stem_type'
  | 'time_range'
  | 'rights';

// ---------------------------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------------------------

export interface Project {
  id: Uuid;
  title: string;
  created_at_ms: number;
}

// ---------------------------------------------------------------------------------------------
// Capture (UI-01) — mirrors `print_capture` / `print_fragment_list` / `print_fragment_show`
// ---------------------------------------------------------------------------------------------

/** Input to capture a fragment. The audio Blob travels as multipart form-data, never inline JSON. */
export interface CaptureInput {
  projectId: Uuid;
  note: string;
  kind: FragmentKind;
  /** The captured/uploaded audio. Sent file-to-multipart; its bytes never enter the contract. */
  file: Blob;
  fileName: string;
}

/** `capture` result — ids + state only. */
export interface CaptureResult {
  fragment: Uuid;
  state: FragmentState;
  audio_uri: string;
  enqueued_job: Uuid;
}

/** One compact line of `fragments list`. */
export interface FragmentSummary {
  id: Uuid;
  state: FragmentState;
  kind: FragmentKind;
  note: string;
}

/** The compact `fragments show` summary. */
export interface FragmentDetail {
  id: Uuid;
  project_id: Uuid;
  kind: FragmentKind;
  provenance: Provenance;
  state: FragmentState;
  duration_ms: number | null;
  sample_rate: number | null;
  audio_uri: string;
  note: string;
  parent_fragment_id: Uuid | null;
}

// ---------------------------------------------------------------------------------------------
// Reference (UI-02) — mirrors `print_reference_*`. Vibe + NON-melodic targets only.
// ---------------------------------------------------------------------------------------------

export interface ReferenceUploadInput {
  file: Blob;
  fileName: string;
  title?: string;
  artist?: string;
}

export interface ReferenceUploadResult {
  reference: Uuid;
  audio_uri: string;
  enqueued_job: Uuid;
}

/** A convenience list item for the reference picker (not a CLI command — the HTTP API exposes it). */
export interface ReferenceListItem {
  id: Uuid;
  title: string | null;
  artist: string | null;
  /** True once the analysis job has produced a `ReferenceAnalysis`. */
  analyzed: boolean;
}

/**
 * The measurable, NON-melodic analysis of a reference. There is deliberately no melody/chroma/f0/
 * key/chord/structure field — the same structural non-cloning guarantee the server enforces.
 * `tonal_balance` is the 5 band ratios low→high; `embedding_dim` is a count, never the vector.
 */
export interface ReferenceAnalysis {
  genre: string | null;
  tempo_bpm_min: number;
  tempo_bpm_max: number;
  lufs: number;
  tonal_balance: number[]; // [low, low_mid, mid, high_mid, high]
  stereo_width: number;
  vibe: string;
  embedding_dim: number;
  analyzer_version: string;
}

/** `reference show` — the track + its analysis (null until analyzed). */
export interface ReferenceView {
  id: Uuid;
  audio_uri: string;
  title: string | null;
  artist: string | null;
  duration_ms: number | null;
  sample_rate: number | null;
  analysis: ReferenceAnalysis | null;
}

export interface AttachReferenceInput {
  referenceId: Uuid;
  projectId: Uuid;
  role: ReferenceRole;
}

export interface AttachReferenceResult {
  reference: Uuid;
  project: Uuid;
  role: ReferenceRole;
}

// ---------------------------------------------------------------------------------------------
// Stem library + attributed sampling (UI-03) — mirrors `print_stem_list` / `print_sample_*`
// ---------------------------------------------------------------------------------------------

export interface StemSummary {
  id: Uuid;
  stem_type: StemType;
  /** "model@version", e.g. "htdemucs_ft@4.0.1". */
  separator: string;
  audio_uri: string;
  duration_ms: number | null;
}

export interface AddSampleInput {
  stemId: Uuid;
  projectId: Uuid;
  artist: string;
  startMs: number;
  endMs: number;
  rights: RightsStatus;
  /** Falls back to the source track's title when omitted (as the CLI does). */
  title?: string;
}

/** `sample add` result. */
export interface SampleAddResult {
  fragment: Uuid;
  provenance: Provenance;
  state: FragmentState;
  source_title: string;
  source_artist: string;
  stem_type: StemType;
  start_ms: number;
  end_ms: number;
  rights: RightsStatus;
  enqueued_job: Uuid;
}

/** `sample show` — a sampled fragment's full attribution + the honest rights note. */
export interface SampleView {
  fragment: Uuid;
  project: Uuid;
  source_track: Uuid;
  stem: Uuid;
  source_title: string;
  source_artist: string;
  stem_type: StemType;
  start_ms: number;
  end_ms: number;
  rights: RightsStatus;
  rights_note: string;
  attribution_is_not_permission: true;
}

// ---------------------------------------------------------------------------------------------
// Project graph + credits (UI-04)
// ---------------------------------------------------------------------------------------------

/** One node of the fragment graph — compact: note + key/tempo (once analyzed), never arrays. */
export interface FragmentNode {
  id: Uuid;
  kind: FragmentKind;
  provenance: Provenance;
  state: FragmentState;
  note: string;
  /** Canonical key label (e.g. "C:maj"); null until the fragment is analyzed. */
  key: string | null;
  tempo_bpm: number | null;
  parent_fragment_id: Uuid | null;
}

/** A lineage edge: `from` (parent) → `to` (child). */
export interface GraphEdge {
  from: Uuid;
  to: Uuid;
}

export interface ProjectGraph {
  projectId: Uuid;
  nodes: FragmentNode[];
  edges: GraphEdge[];
}

export interface CreditSample {
  fragment: Uuid;
  source_title: string;
  source_artist: string;
  stem_type: StemType;
  start_ms: number;
  end_ms: number;
  rights: RightsStatus;
}

/** `credits <project>` — the structured rows + the rendered markdown sheet. */
export interface Credits {
  project: string;
  attribution_is_not_permission: true;
  samples: CreditSample[];
  markdown: string;
}
