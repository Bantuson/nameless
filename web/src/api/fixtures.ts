/**
 * Seed fixtures + the internal record model for the `MockNamelessApi`.
 *
 * `createSeedState()` returns a FRESH, independent state graph each call, so every test (and the dev
 * session) starts from the same known world with no shared mutable state. The data is themed to the
 * north-star aesthetic (Sonder / Brent Faiyaz, R&B × amapiano × deep house × alt-piano) but is
 * obviously fictional example content — titles/artists are illustrative, not real recordings.
 *
 * Fixed UUIDs are used for the seeded entities so tests can reference them directly.
 */

import type {
  Project,
  ReferenceAnalysis,
  ReferenceRole,
  RightsStatus,
  StemType,
  Uuid,
} from './types';
import { pseudoContentHash } from '../lib/ids';

// ---- internal record model (what the mock stores) ----

/** A stored fragment: the public detail fields plus the analysis-derived key/tempo + a timestamp. */
export interface FragmentRecord {
  id: Uuid;
  project_id: Uuid;
  kind: 'melody' | 'hook' | 'beat' | 'rhythm' | 'chord' | 'pad' | 'adlib' | 'stem' | 'full';
  provenance: 'human_recorded' | 'ai_generated' | 'derived' | 'sampled';
  state:
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
  audio_uri: string;
  duration_ms: number | null;
  sample_rate: number | null;
  note: string;
  parent_fragment_id: Uuid | null;
  key: string | null;
  tempo_bpm: number | null;
  created_at_ms: number;
}

export interface RefRecord {
  id: Uuid;
  audio_uri: string;
  title: string | null;
  artist: string | null;
  duration_ms: number | null;
  sample_rate: number | null;
  analysis: ReferenceAnalysis | null;
}

export interface StemRecord {
  id: Uuid;
  reference_track_id: Uuid;
  stem_type: StemType;
  separator: string;
  audio_uri: string;
  duration_ms: number | null;
}

export interface AttributionRecord {
  fragment_id: Uuid;
  project_id: Uuid;
  source_track_id: Uuid;
  stem_id: Uuid;
  source_title: string;
  source_artist: string;
  stem_type: StemType;
  start_ms: number;
  end_ms: number;
  rights: RightsStatus;
}

export interface ProjectReferenceRecord {
  projectId: Uuid;
  referenceId: Uuid;
  role: ReferenceRole;
}

export interface MockState {
  projects: Project[];
  fragments: FragmentRecord[];
  references: RefRecord[];
  stems: StemRecord[];
  attributions: AttributionRecord[];
  projectReferences: ProjectReferenceRecord[];
}

// ---- fixed ids for the seeded world ----

export const DEMO_PROJECT_ID: Uuid = '00000000-0000-4000-8000-000000000001';
const FRAG_HUM: Uuid = '00000000-0000-4000-8000-000000000010';
const FRAG_BEAT: Uuid = '00000000-0000-4000-8000-000000000011';
const FRAG_DERIVED: Uuid = '00000000-0000-4000-8000-000000000012';
const FRAG_SAMPLED: Uuid = '00000000-0000-4000-8000-000000000013';

export const DEMO_REFERENCE_ID: Uuid = '00000000-0000-4000-8000-000000000020';

const STEM_VOCALS: Uuid = '00000000-0000-4000-8000-000000000030';
const STEM_DRUMS: Uuid = '00000000-0000-4000-8000-000000000031';
const STEM_BASS: Uuid = '00000000-0000-4000-8000-000000000032';
const STEM_OTHER: Uuid = '00000000-0000-4000-8000-000000000033';
const STEM_PIANO: Uuid = '00000000-0000-4000-8000-000000000034';
const STEM_GUITAR: Uuid = '00000000-0000-4000-8000-000000000035';

/** A warm, bass-forward, late-night tonal balance (sums to ~1.0), low → high. */
const DEMO_TONAL_BALANCE = [0.34, 0.24, 0.2, 0.13, 0.09];

const DEMO_REFERENCE_ANALYSIS: ReferenceAnalysis = {
  genre: 'amapiano',
  tempo_bpm_min: 110,
  tempo_bpm_max: 114,
  lufs: -9.4,
  tonal_balance: DEMO_TONAL_BALANCE,
  stereo_width: 0.46,
  vibe: 'Warm, spacious, late-night. Soft-focus pads under a patient log-drum groove; intimate, after-hours, a little melancholy.',
  embedding_dim: 512,
  analyzer_version: 'restricted-ref-analyzer@0.1',
};

const SIX_STEM_SEPARATOR = 'htdemucs_6s@4.0.1';

/**
 * Synthesize a plausible NON-melodic analysis for a freshly-uploaded reference, deterministically
 * seeded by a string. The real backend computes this asynchronously via the analysis job; the mock
 * simulates the job having completed so the UI can show a full summary immediately. NEVER melodic —
 * only genre/tempo-range/LUFS/tonal-balance/stereo-width/vibe, mirroring the structural guarantee.
 */
export function synthesizeAnalysis(seed: string): ReferenceAnalysis {
  // Derive small variations from a stable hash so two different uploads look distinct but fixed.
  const h = parseInt(pseudoContentHash(seed).slice(7), 16);
  const tempoMin = 100 + (h % 24); // 100–123
  const genres = ['amapiano', 'r&b', 'deep house', 'alt-piano'];
  const balance = [0.3, 0.24, 0.22, 0.14, 0.1];
  return {
    genre: genres[h % genres.length],
    tempo_bpm_min: tempoMin,
    tempo_bpm_max: tempoMin + 4,
    lufs: -11 + (h % 5), // -11 … -7
    tonal_balance: balance,
    stereo_width: 0.35 + (h % 40) / 100, // 0.35 … 0.74
    vibe: 'Atmospheric and intimate — extracted as conditioning context only, never to reproduce the song.',
    embedding_dim: 512,
    analyzer_version: 'restricted-ref-analyzer@0.1',
  };
}

/** Build the six htdemucs_6s stem rows for a track. */
export function buildSixStems(
  trackId: Uuid,
  durationMs: number | null,
  ids?: () => string,
): StemRecord[] {
  const types: StemType[] = ['vocals', 'drums', 'bass', 'other', 'piano', 'guitar'];
  return types.map((stem_type) => ({
    id: ids ? ids() : crypto.randomUUID(),
    reference_track_id: trackId,
    stem_type,
    separator: SIX_STEM_SEPARATOR,
    audio_uri: pseudoContentHash(`${trackId}:${stem_type}`),
    duration_ms: durationMs,
  }));
}

/** A fresh, independent copy of the seeded world. */
export function createSeedState(): MockState {
  const now = 1_750_000_000_000; // a fixed epoch-ms so timestamps are deterministic in fixtures

  const project: Project = {
    id: DEMO_PROJECT_ID,
    title: 'Late Night Tape',
    created_at_ms: now,
  };

  const fragments: FragmentRecord[] = [
    {
      id: FRAG_HUM,
      project_id: DEMO_PROJECT_ID,
      kind: 'hook',
      provenance: 'human_recorded',
      state: 'analyzed',
      audio_uri: pseudoContentHash('hum-hook'),
      duration_ms: 8200,
      sample_rate: 44_100,
      note: 'Chorus hook hum — sits over the 2nd drop. Breathy, doubled an octave up.',
      parent_fragment_id: null,
      key: 'C:min',
      tempo_bpm: 112,
      created_at_ms: now + 1,
    },
    {
      id: FRAG_BEAT,
      project_id: DEMO_PROJECT_ID,
      kind: 'beat',
      provenance: 'human_recorded',
      state: 'captured',
      audio_uri: pseudoContentHash('logdrum-sketch'),
      duration_ms: 16_000,
      sample_rate: 44_100,
      note: 'Amapiano log-drum groove sketch — needs swing tightened. (awaiting analysis)',
      parent_fragment_id: null,
      key: null,
      tempo_bpm: null,
      created_at_ms: now + 2,
    },
    {
      id: FRAG_DERIVED,
      project_id: DEMO_PROJECT_ID,
      kind: 'pad',
      provenance: 'derived',
      state: 'analyzed',
      audio_uri: pseudoContentHash('pad-bounce'),
      duration_ms: 8200,
      sample_rate: 44_100,
      note: 'Pitched-down pad bounce of the hook — locked to the hum key.',
      parent_fragment_id: FRAG_HUM,
      key: 'C:min',
      tempo_bpm: 112,
      created_at_ms: now + 3,
    },
    {
      id: FRAG_SAMPLED,
      project_id: DEMO_PROJECT_ID,
      kind: 'stem',
      provenance: 'sampled',
      state: 'captured',
      audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:vocals`),
      duration_ms: 6000,
      sample_rate: 44_100,
      note: 'sampled vocals from "Midnight Reverie" — Esther Vale (example)',
      parent_fragment_id: null,
      key: null,
      tempo_bpm: null,
      created_at_ms: now + 4,
    },
  ];

  const references: RefRecord[] = [
    {
      id: DEMO_REFERENCE_ID,
      audio_uri: pseudoContentHash('midnight-reverie'),
      title: 'Midnight Reverie',
      artist: 'Esther Vale (example)',
      duration_ms: 214_000,
      sample_rate: 44_100,
      analysis: DEMO_REFERENCE_ANALYSIS,
    },
  ];

  const stems: StemRecord[] = [
    { id: STEM_VOCALS, reference_track_id: DEMO_REFERENCE_ID, stem_type: 'vocals', separator: SIX_STEM_SEPARATOR, audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:vocals`), duration_ms: 214_000 },
    { id: STEM_DRUMS, reference_track_id: DEMO_REFERENCE_ID, stem_type: 'drums', separator: SIX_STEM_SEPARATOR, audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:drums`), duration_ms: 214_000 },
    { id: STEM_BASS, reference_track_id: DEMO_REFERENCE_ID, stem_type: 'bass', separator: SIX_STEM_SEPARATOR, audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:bass`), duration_ms: 214_000 },
    { id: STEM_OTHER, reference_track_id: DEMO_REFERENCE_ID, stem_type: 'other', separator: SIX_STEM_SEPARATOR, audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:other`), duration_ms: 214_000 },
    { id: STEM_PIANO, reference_track_id: DEMO_REFERENCE_ID, stem_type: 'piano', separator: SIX_STEM_SEPARATOR, audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:piano`), duration_ms: 214_000 },
    { id: STEM_GUITAR, reference_track_id: DEMO_REFERENCE_ID, stem_type: 'guitar', separator: SIX_STEM_SEPARATOR, audio_uri: pseudoContentHash(`${DEMO_REFERENCE_ID}:guitar`), duration_ms: 214_000 },
  ];

  const attributions: AttributionRecord[] = [
    {
      fragment_id: FRAG_SAMPLED,
      project_id: DEMO_PROJECT_ID,
      source_track_id: DEMO_REFERENCE_ID,
      stem_id: STEM_VOCALS,
      source_title: 'Midnight Reverie',
      source_artist: 'Esther Vale (example)',
      stem_type: 'vocals',
      start_ms: 48_000,
      end_ms: 54_000,
      rights: 'copyrighted_uncleared',
    },
  ];

  const projectReferences: ProjectReferenceRecord[] = [
    { projectId: DEMO_PROJECT_ID, referenceId: DEMO_REFERENCE_ID, role: 'vibe' },
  ];

  return { projects: [project], fragments, references, stems, attributions, projectReferences };
}
