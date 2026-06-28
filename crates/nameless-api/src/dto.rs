//! Wire DTOs — the JSON the HTTP API emits, mirroring `web/src/api/types.ts` field-for-field.
//!
//! ## Why these exist (and why they embed the domain enums)
//!
//! The CLI's `output.rs` prints the same compact summaries, but it prints to stdout via
//! `serde_json::json!` literals — there is no reusable `Serialize` value to hand to axum's `Json`.
//! So this module defines the response structs once, with `#[derive(Serialize)]`, and a pure
//! `from_domain` mapper for each. The enum fields embed the DOMAIN enums (`FragmentState`,
//! `FragmentKind`, `Provenance`, `StemType`, `RightsStatus`, `ReferenceRole`) directly: each already
//! derives `Serialize` with `rename_all = "snake_case"`, so they serialize to the exact canonical
//! labels the DB + the TS string-unions use. That makes a label drift impossible — the wire form is
//! the domain's own serde form, not a hand-copied string.
//!
//! ## The compact-output contract (PRD §12)
//!
//! There is deliberately NO field anywhere below that can carry a waveform, a feature array, or an
//! embedding vector. A reference's analysis carries `embedding_dim` (a count) and the 5-band
//! `tonal_balance` ratios — never the CLAP vector. The graph nodes carry a note + (once analyzed)
//! key/tempo scalars — never chroma/f0. The structure makes leaking an array impossible, exactly as
//! the core `ReferenceContextSummary` does.

use std::collections::HashSet;

use serde::Serialize;
use uuid::Uuid;

use nameless_core::attribution::{credits_sheet, RightsStatus, SampleAttribution};
use nameless_core::fragment::{Fragment, FragmentKind, Project};
use nameless_core::job::JobId;
use nameless_core::provenance::Provenance;
use nameless_core::reference::{ReferenceContextSummary, ReferenceRole, ReferenceTrack};
use nameless_core::state_machine::FragmentState;
use nameless_core::stems::{Stem, StemType};

// ---------------------------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------------------------

/// `Project` — `{ id, title, created_at_ms }`.
#[derive(Debug, Serialize)]
pub struct ProjectDto {
    pub id: Uuid,
    pub title: String,
    pub created_at_ms: i64,
}

impl ProjectDto {
    pub fn from_domain(p: &Project) -> Self {
        Self {
            id: p.id.0,
            title: p.title.clone(),
            created_at_ms: p.created_at_ms,
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Capture (UI-01)
// ---------------------------------------------------------------------------------------------

/// `CaptureResult` — ids + state only.
#[derive(Debug, Serialize)]
pub struct CaptureResultDto {
    pub fragment: Uuid,
    pub state: FragmentState,
    pub audio_uri: String,
    pub enqueued_job: Uuid,
}

impl CaptureResultDto {
    pub fn from_domain(frag: &Fragment, job: JobId) -> Self {
        Self {
            fragment: frag.id.0,
            state: frag.state(),
            audio_uri: frag.audio_uri.clone(),
            enqueued_job: job.0,
        }
    }
}

/// One compact line of `fragments list`.
#[derive(Debug, Serialize)]
pub struct FragmentSummaryDto {
    pub id: Uuid,
    pub state: FragmentState,
    pub kind: FragmentKind,
    pub note: String,
}

impl FragmentSummaryDto {
    pub fn from_domain(f: &Fragment) -> Self {
        Self {
            id: f.id.0,
            state: f.state(),
            kind: f.kind,
            note: f.note_text.clone(),
        }
    }
}

/// The compact `fragments show` summary.
#[derive(Debug, Serialize)]
pub struct FragmentDetailDto {
    pub id: Uuid,
    pub project_id: Uuid,
    pub kind: FragmentKind,
    pub provenance: Provenance,
    pub state: FragmentState,
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
    pub audio_uri: String,
    pub note: String,
    pub parent_fragment_id: Option<Uuid>,
}

impl FragmentDetailDto {
    pub fn from_domain(f: &Fragment) -> Self {
        Self {
            id: f.id.0,
            project_id: f.project_id.0,
            kind: f.kind,
            provenance: f.provenance(),
            state: f.state(),
            duration_ms: f.duration_ms,
            sample_rate: f.sample_rate,
            audio_uri: f.audio_uri.clone(),
            note: f.note_text.clone(),
            parent_fragment_id: f.parent_fragment_id.map(|p| p.0),
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Reference (UI-02)
// ---------------------------------------------------------------------------------------------

/// `ReferenceUploadResult`.
#[derive(Debug, Serialize)]
pub struct ReferenceUploadResultDto {
    pub reference: Uuid,
    pub audio_uri: String,
    pub enqueued_job: Uuid,
}

impl ReferenceUploadResultDto {
    pub fn from_domain(track: &ReferenceTrack, job: JobId) -> Self {
        Self {
            reference: track.id.0,
            audio_uri: track.audio_uri.clone(),
            enqueued_job: job.0,
        }
    }
}

/// A convenience list item for the reference picker (`GET /references`).
#[derive(Debug, Serialize)]
pub struct ReferenceListItemDto {
    pub id: Uuid,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub analyzed: bool,
}

impl ReferenceListItemDto {
    pub fn from_domain(track: &ReferenceTrack, analyzed: bool) -> Self {
        Self {
            id: track.id.0,
            title: track.title.clone(),
            artist: track.artist.clone(),
            analyzed,
        }
    }
}

/// The measurable, NON-melodic analysis of a reference. No melody/chroma/f0/key/chord/structure
/// field — `embedding_dim` is a count, `tonal_balance` is the 5 band ratios low→high.
#[derive(Debug, Serialize)]
pub struct ReferenceAnalysisDto {
    pub genre: Option<String>,
    pub tempo_bpm_min: f32,
    pub tempo_bpm_max: f32,
    pub lufs: f32,
    pub tonal_balance: [f32; 5],
    pub stereo_width: f32,
    pub vibe: String,
    pub embedding_dim: usize,
    pub analyzer_version: String,
}

impl ReferenceAnalysisDto {
    pub fn from_summary(s: &ReferenceContextSummary) -> Self {
        Self {
            genre: s.genre.clone(),
            tempo_bpm_min: s.tempo_bpm_min,
            tempo_bpm_max: s.tempo_bpm_max,
            lufs: s.lufs,
            tonal_balance: s.tonal_balance.bands(),
            stereo_width: s.stereo_width,
            vibe: s.vibe_description.clone(),
            embedding_dim: s.embedding_dim,
            analyzer_version: s.analyzer_version.clone(),
        }
    }
}

/// `reference show` — the track + its analysis (null until analyzed).
#[derive(Debug, Serialize)]
pub struct ReferenceViewDto {
    pub id: Uuid,
    pub audio_uri: String,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
    pub analysis: Option<ReferenceAnalysisDto>,
}

impl ReferenceViewDto {
    pub fn from_domain(track: &ReferenceTrack, summary: Option<&ReferenceContextSummary>) -> Self {
        Self {
            id: track.id.0,
            audio_uri: track.audio_uri.clone(),
            title: track.title.clone(),
            artist: track.artist.clone(),
            duration_ms: track.duration_ms,
            sample_rate: track.sample_rate,
            analysis: summary.map(ReferenceAnalysisDto::from_summary),
        }
    }
}

/// `reference attach` result.
#[derive(Debug, Serialize)]
pub struct AttachReferenceResultDto {
    pub reference: Uuid,
    pub project: Uuid,
    pub role: ReferenceRole,
}

// ---------------------------------------------------------------------------------------------
// Stem library + attributed sampling (UI-03)
// ---------------------------------------------------------------------------------------------

/// `stems separate` result.
#[derive(Debug, Serialize)]
pub struct SeparateStemsResultDto {
    pub reference: Uuid,
    pub enqueued_job: Uuid,
}

/// One compact line of `stems list`.
#[derive(Debug, Serialize)]
pub struct StemSummaryDto {
    pub id: Uuid,
    pub stem_type: StemType,
    /// "model@version", e.g. "htdemucs_ft@4.0.1".
    pub separator: String,
    pub audio_uri: String,
    pub duration_ms: Option<u32>,
}

impl StemSummaryDto {
    pub fn from_domain(s: &Stem) -> Self {
        Self {
            id: s.id.0,
            stem_type: s.stem_type,
            separator: format!("{}@{}", s.separator_model, s.separator_version),
            audio_uri: s.audio_uri.clone(),
            duration_ms: s.duration_ms,
        }
    }
}

/// `sample add` result.
#[derive(Debug, Serialize)]
pub struct SampleAddResultDto {
    pub fragment: Uuid,
    pub provenance: Provenance,
    pub state: FragmentState,
    pub source_title: String,
    pub source_artist: String,
    pub stem_type: StemType,
    pub start_ms: u32,
    pub end_ms: u32,
    pub rights: RightsStatus,
    pub enqueued_job: Uuid,
}

impl SampleAddResultDto {
    pub fn from_domain(frag: &Fragment, attr: &SampleAttribution, job: JobId) -> Self {
        let a = &attr.attribution;
        Self {
            fragment: frag.id.0,
            provenance: frag.provenance(),
            state: frag.state(),
            source_title: a.source_title.clone(),
            source_artist: a.source_artist.clone(),
            stem_type: a.stem_type,
            start_ms: a.start_ms,
            end_ms: a.end_ms,
            rights: a.rights_status,
            enqueued_job: job.0,
        }
    }
}

/// `sample show` — a sampled fragment's full attribution + the honest rights note.
#[derive(Debug, Serialize)]
pub struct SampleViewDto {
    pub fragment: Uuid,
    pub project: Uuid,
    pub source_track: Uuid,
    pub stem: Uuid,
    pub source_title: String,
    pub source_artist: String,
    pub stem_type: StemType,
    pub start_ms: u32,
    pub end_ms: u32,
    pub rights: RightsStatus,
    pub rights_note: String,
    /// Always `true` — attribution is NOT permission (SAMP-04).
    pub attribution_is_not_permission: bool,
}

impl SampleViewDto {
    pub fn from_domain(attr: &SampleAttribution) -> Self {
        let a = &attr.attribution;
        Self {
            fragment: attr.fragment_id.0,
            project: attr.project_id.0,
            source_track: a.source_track_id.0,
            stem: a.stem_id.0,
            source_title: a.source_title.clone(),
            source_artist: a.source_artist.clone(),
            stem_type: a.stem_type,
            start_ms: a.start_ms,
            end_ms: a.end_ms,
            rights: a.rights_status,
            rights_note: a.rights_status.note().to_string(),
            attribution_is_not_permission: true,
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Project graph + credits (UI-04)
// ---------------------------------------------------------------------------------------------

/// One node of the fragment graph — compact: note + (once analyzed) key/tempo, never arrays.
#[derive(Debug, Serialize)]
pub struct FragmentNodeDto {
    pub id: Uuid,
    pub kind: FragmentKind,
    pub provenance: Provenance,
    pub state: FragmentState,
    pub note: String,
    /// Canonical key label (e.g. "C:maj"); null until a feature-read path exists (see below).
    pub key: Option<String>,
    pub tempo_bpm: Option<f32>,
    pub parent_fragment_id: Option<Uuid>,
}

impl FragmentNodeDto {
    /// Build a node from a fragment.
    ///
    /// `key`/`tempo_bpm` are `None`: in M0 the control plane has NO port to read `fragment_features`
    /// (the Python feature worker is the writer, and M0 only enqueues the job — no consumer runs), so
    /// the server cannot yet surface a key/tempo. This matches the web `MockNamelessApi` for a
    /// freshly-captured fragment (`key: null, tempo_bpm: null`); the wire shape is identical and the
    /// scalars light up once a feature-read port lands (M1+). See `10-VERIFICATION.md` (flagged).
    pub fn from_domain(f: &Fragment) -> Self {
        Self {
            id: f.id.0,
            kind: f.kind,
            provenance: f.provenance(),
            state: f.state(),
            note: f.note_text.clone(),
            key: None,
            tempo_bpm: None,
            parent_fragment_id: f.parent_fragment_id.map(|p| p.0),
        }
    }
}

/// A lineage edge: `from` (parent) → `to` (child).
#[derive(Debug, Serialize)]
pub struct GraphEdgeDto {
    pub from: Uuid,
    pub to: Uuid,
}

/// `GET /projects/:id/graph` — note the camelCase `projectId` (the one exception in the contract;
/// every other field is snake_case). The `#[serde(rename)]` pins it to the TS `ProjectGraph` shape.
#[derive(Debug, Serialize)]
pub struct ProjectGraphDto {
    #[serde(rename = "projectId")]
    pub project_id: Uuid,
    pub nodes: Vec<FragmentNodeDto>,
    pub edges: Vec<GraphEdgeDto>,
}

/// Derive lineage edges from nodes — a port of `web/src/lib/graph.ts` `deriveEdges`: an edge exists
/// wherever a node names a `parent_fragment_id` that is ALSO present in the node set. Pure (nodes in,
/// edges out) so it unit-tests without a backend, exactly like the TS it mirrors.
pub fn derive_edges(nodes: &[FragmentNodeDto]) -> Vec<GraphEdgeDto> {
    let ids: HashSet<Uuid> = nodes.iter().map(|n| n.id).collect();
    let mut edges = Vec::new();
    for n in nodes {
        if let Some(parent) = n.parent_fragment_id {
            if ids.contains(&parent) {
                edges.push(GraphEdgeDto {
                    from: parent,
                    to: n.id,
                });
            }
        }
    }
    edges
}

/// Assemble the `ProjectGraph` for a project's fragments.
pub fn build_project_graph(project_id: Uuid, frags: &[Fragment]) -> ProjectGraphDto {
    let nodes: Vec<FragmentNodeDto> = frags.iter().map(FragmentNodeDto::from_domain).collect();
    let edges = derive_edges(&nodes);
    ProjectGraphDto {
        project_id,
        nodes,
        edges,
    }
}

/// One row of a credits sheet.
#[derive(Debug, Serialize)]
pub struct CreditSampleDto {
    pub fragment: Uuid,
    pub source_title: String,
    pub source_artist: String,
    pub stem_type: StemType,
    pub start_ms: u32,
    pub end_ms: u32,
    pub rights: RightsStatus,
}

impl CreditSampleDto {
    pub fn from_domain(row: &SampleAttribution) -> Self {
        let a = &row.attribution;
        Self {
            fragment: row.fragment_id.0,
            source_title: a.source_title.clone(),
            source_artist: a.source_artist.clone(),
            stem_type: a.stem_type,
            start_ms: a.start_ms,
            end_ms: a.end_ms,
            rights: a.rights_status,
        }
    }
}

/// `credits <project>` — the structured rows + the rendered markdown sheet (which always leads with
/// the attribution-≠-permission notice, built into [`credits_sheet`]).
#[derive(Debug, Serialize)]
pub struct CreditsDto {
    pub project: String,
    /// Always `true`.
    pub attribution_is_not_permission: bool,
    pub samples: Vec<CreditSampleDto>,
    pub markdown: String,
}

impl CreditsDto {
    pub fn from_domain(project_title: &str, rows: &[SampleAttribution]) -> Self {
        Self {
            project: project_title.to_string(),
            attribution_is_not_permission: true,
            samples: rows.iter().map(CreditSampleDto::from_domain).collect(),
            markdown: credits_sheet(project_title, rows),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::attribution::PartialAttribution;
    use nameless_core::reference::{ReferenceTrackId, TonalBalance};
    use nameless_core::stems::StemId;

    fn node(id: Uuid, parent: Option<Uuid>) -> FragmentNodeDto {
        FragmentNodeDto {
            id,
            kind: FragmentKind::Hook,
            provenance: Provenance::HumanRecorded,
            state: FragmentState::Captured,
            note: "n".into(),
            key: None,
            tempo_bpm: None,
            parent_fragment_id: parent,
        }
    }

    #[test]
    fn derive_edges_links_in_graph_parents_only() {
        let parent = Uuid::new_v4();
        let child = Uuid::new_v4();
        let orphan_parent = Uuid::new_v4(); // not present as a node
        let nodes = vec![
            node(parent, None),
            node(child, Some(parent)),
            node(Uuid::new_v4(), Some(orphan_parent)), // parent absent → no edge
        ];
        let edges = derive_edges(&nodes);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].from, parent);
        assert_eq!(edges[0].to, child);
    }

    #[test]
    fn project_graph_serializes_camel_case_project_id() {
        let pid = Uuid::new_v4();
        let graph = build_project_graph(pid, &[]);
        let v = serde_json::to_value(&graph).unwrap();
        // The ONE camelCase exception in the contract.
        assert_eq!(v["projectId"], serde_json::json!(pid.to_string()));
        assert!(v.get("project_id").is_none());
        assert!(v["nodes"].is_array());
        assert!(v["edges"].is_array());
    }

    #[test]
    fn reference_analysis_carries_dim_not_the_vector() {
        let summary = ReferenceContextSummary {
            reference_track_id: ReferenceTrackId::new(),
            genre: Some("amapiano".into()),
            tempo_bpm_min: 110.0,
            tempo_bpm_max: 116.0,
            lufs: -9.0,
            tonal_balance: TonalBalance {
                low: 0.3,
                low_mid: 0.25,
                mid: 0.2,
                high_mid: 0.15,
                high: 0.1,
            },
            stereo_width: 0.42,
            vibe_description: "warm late-night".into(),
            embedding_dim: 512,
            analyzer_version: "fake-ref-0".into(),
        };
        let v = serde_json::to_value(ReferenceAnalysisDto::from_summary(&summary)).unwrap();
        // The dimension count is present; no embedding/style vector field can exist (structural).
        assert_eq!(v["embedding_dim"], serde_json::json!(512));
        assert_eq!(v["vibe"], serde_json::json!("warm late-night"));
        assert!(v.get("clap_style_embedding").is_none());
        assert!(v.get("embedding").is_none());
        assert!(v.get("style_embedding").is_none());
        // `tonal_balance` is the 5 coarse band ratios — a target, not a melody.
        assert_eq!(v["tonal_balance"].as_array().unwrap().len(), 5);
    }

    #[test]
    fn sample_view_marks_attribution_not_permission() {
        let attribution = PartialAttribution {
            source_track_id: Some(ReferenceTrackId::new()),
            stem_id: Some(StemId::new()),
            source_title: Some("Trust".into()),
            source_artist: Some("Brent Faiyaz".into()),
            stem_type: Some(StemType::Vocals),
            start_ms: Some(12_000),
            end_ms: Some(18_000),
            rights_status: Some(RightsStatus::CopyrightedUncleared),
        }
        .into_complete()
        .unwrap();
        let row = SampleAttribution::new(
            nameless_core::fragment::FragmentId::new(),
            nameless_core::fragment::ProjectId::new(),
            attribution,
        );
        let v = serde_json::to_value(SampleViewDto::from_domain(&row)).unwrap();
        assert_eq!(v["attribution_is_not_permission"], serde_json::json!(true));
        assert_eq!(v["rights"], serde_json::json!("copyrighted_uncleared"));
        assert_eq!(v["stem_type"], serde_json::json!("vocals"));
        assert!(v["rights_note"].as_str().unwrap().contains("NOT cleared"));
    }

    #[test]
    fn project_dto_keys_match_contract() {
        let p = Project::new("Late Night Tape".into());
        let v = serde_json::to_value(ProjectDto::from_domain(&p)).unwrap();
        assert_eq!(v["title"], serde_json::json!("Late Night Tape"));
        assert!(v["id"].is_string());
        assert!(v["created_at_ms"].is_number());
    }
}
