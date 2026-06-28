//! The persistent stem library — Demucs stems of uploaded tracks, retained indefinitely (SAMP-01).
//!
//! A [`crate::reference::ReferenceTrack`] uploaded for vibe/conditioning (Phase 7) is ALSO a
//! sampling source: the Python worker separates it into named stems (vocals / drums / bass / other,
//! plus piano / guitar under `htdemucs_6s`), and every stem is kept forever in object storage,
//! browsable by track. A producer can promote any stem to an attributed `sampled` fragment at any
//! time — even weeks later (ARCHITECTURE.md Flow B, Pattern 3).
//!
//! This module owns the control-plane view of that library: the [`Stem`] index row + its strongly
//! typed [`StemId`] / [`StemType`]. The audio bytes themselves live in the object store by
//! content-hash uri (never inline), exactly like a fragment's audio. The Python
//! `DemucsStemSeparator` is the WRITER of these rows (mirroring how the feature worker writes
//! `fragment_features`); the control plane reads them back for `stems list` and resolves a stem to
//! its `audio_uri` when promoting it to a fragment.
//!
//! ## Provenance of the separation itself
//!
//! Every stem records the `separator_model` + `separator_version` that produced it (e.g.
//! `htdemucs_ft` / `4.0.1`). Demucs is maintenance-only and a BS-RoFormer swap is anticipated
//! behind the worker port (STACK.md §4); recording the model means a future re-separation under a
//! better model is detectable and the credits sheet can state exactly how a sample was isolated.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::fragment::now_ms;
use crate::reference::ReferenceTrackId;

/// Strongly-typed stem identifier (newtype over UUID, serde-transparent).
///
/// A distinct newtype so a stem id can never be passed where a fragment / reference / project id is
/// expected — the compiler keeps the sampling graph's edges honest (same discipline as `FragmentId`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct StemId(pub Uuid);

impl StemId {
    /// Mint a fresh random id.
    pub fn new() -> Self {
        StemId(Uuid::new_v4())
    }
}

impl Default for StemId {
    fn default() -> Self {
        Self::new()
    }
}

impl std::fmt::Display for StemId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// The named source a stem isolates — the fixed Demucs output vocabulary.
///
/// `htdemucs` / `htdemucs_ft` emit the four-stem set (vocals, drums, bass, other); `htdemucs_6s`
/// additionally isolates piano + guitar — directly relevant to the project's alt-piano focus
/// (STACK.md §4). A typed enum (not free text) so the value is exhaustively matchable, mirroring
/// `Provenance` / `FragmentKind`. The DB column is `text`, mapped by the snake_case label.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StemType {
    Vocals,
    Drums,
    Bass,
    /// Everything not isolated into its own stem (the Demucs "other" residual).
    Other,
    /// Only produced by `htdemucs_6s`.
    Piano,
    /// Only produced by `htdemucs_6s`.
    Guitar,
}

impl StemType {
    /// All variants — for `--stem-type` parsing + UI enumeration.
    pub const ALL: [StemType; 6] = [
        StemType::Vocals,
        StemType::Drums,
        StemType::Bass,
        StemType::Other,
        StemType::Piano,
        StemType::Guitar,
    ];

    /// The four stems every `htdemucs` / `htdemucs_ft` separation produces.
    pub const HTDEMUCS_4: [StemType; 4] = [
        StemType::Vocals,
        StemType::Drums,
        StemType::Bass,
        StemType::Other,
    ];

    /// Stable snake_case label (matches serde + the DB text column + the Python `StemType`).
    pub const fn as_str(self) -> &'static str {
        match self {
            StemType::Vocals => "vocals",
            StemType::Drums => "drums",
            StemType::Bass => "bass",
            StemType::Other => "other",
            StemType::Piano => "piano",
            StemType::Guitar => "guitar",
        }
    }

    /// Parse from the canonical label. `None` for unknown labels.
    pub fn from_db_str(s: &str) -> Option<StemType> {
        StemType::ALL.into_iter().find(|k| k.as_str() == s)
    }
}

/// One retained stem — an index row over a separated, content-addressed audio object.
///
/// The `audio_uri` is the SHA-256 content hash the separation worker stored the stem bytes under
/// (immutable, by ID — never the bytes). `separator_model` + `separator_version` capture how the
/// stem was isolated (provenance of the separation), so the credits sheet can be honest about the
/// tool and a re-separation under a different model is auditable.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Stem {
    pub id: StemId,
    /// The uploaded track this stem was separated from (shared with the Phase-7 reference upload).
    pub reference_track_id: ReferenceTrackId,
    pub stem_type: StemType,
    /// Immutable object-store key (content hash) of the isolated stem audio.
    pub audio_uri: String,
    /// Which separator produced this stem (e.g. `htdemucs_ft`). Behind the worker port; swappable.
    pub separator_model: String,
    /// The separator's version (e.g. `4.0.1`) — bumped ⇒ a re-separation is detectable.
    pub separator_version: String,
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
    /// Unix epoch milliseconds at separation.
    pub created_at_ms: i64,
}

impl Stem {
    /// Build a stem index row. The caller (the separation worker / its control-plane mirror) has
    /// already content-hashed + stored the stem audio under `audio_uri`.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        reference_track_id: ReferenceTrackId,
        stem_type: StemType,
        audio_uri: String,
        separator_model: String,
        separator_version: String,
        duration_ms: Option<u32>,
        sample_rate: Option<u32>,
    ) -> Self {
        Stem {
            id: StemId::new(),
            reference_track_id,
            stem_type,
            audio_uri,
            separator_model,
            separator_version,
            duration_ms,
            sample_rate,
            created_at_ms: now_ms(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stem_type_round_trips_through_db_str() {
        for st in StemType::ALL {
            assert_eq!(StemType::from_db_str(st.as_str()), Some(st));
        }
        assert_eq!(StemType::from_db_str("kazoo"), None);
    }

    #[test]
    fn htdemucs_4_is_the_four_stem_set() {
        assert_eq!(StemType::HTDEMUCS_4.len(), 4);
        assert!(!StemType::HTDEMUCS_4.contains(&StemType::Piano));
        assert!(StemType::HTDEMUCS_4.contains(&StemType::Other));
    }

    #[test]
    fn stem_new_sets_id_and_timestamp() {
        let s = Stem::new(
            ReferenceTrackId::new(),
            StemType::Piano,
            "abc123".into(),
            "htdemucs_6s".into(),
            "4.0.1".into(),
            Some(210_000),
            Some(44_100),
        );
        assert_eq!(s.stem_type, StemType::Piano);
        assert_eq!(s.audio_uri, "abc123");
        assert_eq!(s.separator_model, "htdemucs_6s");
        assert!(s.created_at_ms >= 0);
    }

    #[test]
    fn stem_serde_json_round_trips_with_snake_case_labels() {
        let s = Stem::new(
            ReferenceTrackId::new(),
            StemType::Bass,
            "deadbeef".into(),
            "htdemucs_ft".into(),
            "4.0.1".into(),
            None,
            None,
        );
        let json = serde_json::to_string(&s).unwrap();
        assert!(json.contains("\"bass\""));
        let back: Stem = serde_json::from_str(&json).unwrap();
        assert_eq!(s, back);
    }
}
