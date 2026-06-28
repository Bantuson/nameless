//! The fragment data model — the atomic unit of the Nameless graph (PRD §6).
//!
//! A fragment is "a piece of audio, plus the intent attached to it, plus everything the system
//! derived from it." Phase 1 carries only the fields needed for *capture*; later phases extend
//! the row (features, embeddings, placement role, lineage signals) without reshaping this type.
//!
//! Audio itself is never stored inline — `audio_uri` is an immutable content-hash key into the
//! [`crate::ports::ObjectStore`]. The raw bytes and (future) feature arrays are addressed by ID
//! and never enter agent context (the token strategy starts at the type level).

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::provenance::Provenance;
use crate::state_machine::FragmentState;

/// Strongly-typed fragment identifier (newtype over UUID, serde-transparent).
///
/// A newtype rather than a bare `Uuid` so a fragment id can never be passed where a project id
/// is expected — the compiler keeps the graph's edges honest.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct FragmentId(pub Uuid);

impl FragmentId {
    /// Mint a fresh random id.
    pub fn new() -> Self {
        FragmentId(Uuid::new_v4())
    }
}

impl Default for FragmentId {
    fn default() -> Self {
        Self::new()
    }
}

impl std::fmt::Display for FragmentId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Strongly-typed project identifier (newtype over UUID, serde-transparent).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ProjectId(pub Uuid);

impl ProjectId {
    /// Mint a fresh random id.
    pub fn new() -> Self {
        ProjectId(Uuid::new_v4())
    }
}

impl Default for ProjectId {
    fn default() -> Self {
        Self::new()
    }
}

impl std::fmt::Display for ProjectId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// The kind of musical material a fragment holds (PRD §6 `kind` enum).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FragmentKind {
    Melody,
    Hook,
    Beat,
    Rhythm,
    Chord,
    Pad,
    Adlib,
    Stem,
    Full,
}

impl FragmentKind {
    /// All variants — enables `--kind` value parsing and UI enumeration.
    pub const ALL: [FragmentKind; 9] = [
        FragmentKind::Melody,
        FragmentKind::Hook,
        FragmentKind::Beat,
        FragmentKind::Rhythm,
        FragmentKind::Chord,
        FragmentKind::Pad,
        FragmentKind::Adlib,
        FragmentKind::Stem,
        FragmentKind::Full,
    ];

    /// Stable lowercase label (matches serde + the DB text column).
    pub const fn as_str(self) -> &'static str {
        match self {
            FragmentKind::Melody => "melody",
            FragmentKind::Hook => "hook",
            FragmentKind::Beat => "beat",
            FragmentKind::Rhythm => "rhythm",
            FragmentKind::Chord => "chord",
            FragmentKind::Pad => "pad",
            FragmentKind::Adlib => "adlib",
            FragmentKind::Stem => "stem",
            FragmentKind::Full => "full",
        }
    }

    /// Parse from the canonical label. `None` for unknown labels.
    pub fn from_db_str(s: &str) -> Option<FragmentKind> {
        FragmentKind::ALL.into_iter().find(|k| k.as_str() == s)
    }
}

/// A project — the container a fragment graph belongs to.
///
/// Phase 1 keeps only id/title/created_at; the PRD's target_key/tempo/genre/lufs columns land
/// when arrangement work (M1) needs them.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Project {
    pub id: ProjectId,
    pub title: String,
    /// Unix epoch milliseconds at creation (sourced from `SystemTime`; no extra time crate).
    pub created_at_ms: i64,
}

impl Project {
    /// Create a project with a fresh id and the current timestamp.
    pub fn new(title: String) -> Self {
        Project {
            id: ProjectId::new(),
            title,
            created_at_ms: now_ms(),
        }
    }
}

/// A fragment — audio (by content-hash uri) + intent note + derived lifecycle state.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Fragment {
    pub id: FragmentId,
    pub project_id: ProjectId,
    pub kind: FragmentKind,
    pub provenance: Provenance,
    /// Immutable object-store key (SHA-256 content hash) — NEVER the audio bytes themselves.
    pub audio_uri: String,
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
    /// The intent channel — free text, also the compact node summary the agent reads.
    pub note_text: String,
    /// Lifecycle state. Mutated ONLY via [`Fragment::apply`] (see `state_machine`).
    pub state: FragmentState,
    /// Lineage edge (e.g. an AI fragment's parent human fragment). `None` for a raw capture.
    pub parent_fragment_id: Option<FragmentId>,
    pub created_at_ms: i64,
}

impl Fragment {
    /// Build a freshly-captured human fragment: provenance `HumanRecorded`, state `Captured`.
    ///
    /// This is the single Phase-1 entry point into the graph. `audio_uri` is the content hash the
    /// caller has already computed + stored via the [`crate::ports::ObjectStore`].
    pub fn new_capture(
        project_id: ProjectId,
        kind: FragmentKind,
        audio_uri: String,
        duration_ms: Option<u32>,
        sample_rate: Option<u32>,
        note_text: String,
    ) -> Self {
        Fragment {
            id: FragmentId::new(),
            project_id,
            kind,
            provenance: Provenance::HumanRecorded,
            audio_uri,
            duration_ms,
            sample_rate,
            note_text,
            state: FragmentState::Captured,
            parent_fragment_id: None,
            created_at_ms: now_ms(),
        }
    }

    /// Promote a library stem into a `sampled` fragment (Phase 8 — SAMP-02).
    ///
    /// Provenance is [`Provenance::Sampled`] and state is `Captured`, so it enters the SAME human
    /// analysis path as a capture (Captured → Analyzing → Analyzed) — sampled material is real source
    /// audio, never the eval gate. `kind` is [`FragmentKind::Stem`]; `audio_uri` is the stem's
    /// content-hash (the full stem, or a trimmed slice). The attribution gate
    /// ([`crate::state_machine::place`]) then blocks placement until a complete attribution exists.
    pub fn new_sampled(
        project_id: ProjectId,
        audio_uri: String,
        duration_ms: Option<u32>,
        sample_rate: Option<u32>,
        note_text: String,
    ) -> Self {
        Fragment {
            id: FragmentId::new(),
            project_id,
            kind: FragmentKind::Stem,
            provenance: Provenance::Sampled,
            audio_uri,
            duration_ms,
            sample_rate,
            note_text,
            state: FragmentState::Captured,
            parent_fragment_id: None,
            created_at_ms: now_ms(),
        }
    }
}

/// Current Unix time in milliseconds. Clamps pre-epoch clocks to 0 rather than panicking.
pub fn now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state_machine::FragmentState;

    #[test]
    fn capture_fragment_starts_captured_and_human() {
        let f = Fragment::new_capture(
            ProjectId::new(),
            FragmentKind::Hook,
            "abc123".into(),
            Some(4200),
            Some(44_100),
            "chorus hook, over the 2nd drop".into(),
        );
        assert_eq!(f.state, FragmentState::Captured);
        assert_eq!(f.provenance, Provenance::HumanRecorded);
        assert_eq!(f.audio_uri, "abc123");
        assert!(f.parent_fragment_id.is_none());
    }

    #[test]
    fn fragment_serde_json_round_trips() {
        let f = Fragment::new_capture(
            ProjectId::new(),
            FragmentKind::Melody,
            "deadbeef".into(),
            None,
            Some(48_000),
            "humming idea".into(),
        );
        let json = serde_json::to_string(&f).unwrap();
        let back: Fragment = serde_json::from_str(&json).unwrap();
        assert_eq!(f, back);
        // Enums serialize as snake_case strings.
        assert!(json.contains("\"melody\""));
        assert!(json.contains("\"captured\""));
        assert!(json.contains("\"human_recorded\""));
    }

    #[test]
    fn new_sampled_is_sampled_stem_captured() {
        let f = Fragment::new_sampled(
            ProjectId::new(),
            "stemhash".into(),
            Some(6_000),
            Some(44_100),
            "sampled vocals from Trust — Brent Faiyaz".into(),
        );
        assert_eq!(f.provenance, Provenance::Sampled);
        assert_eq!(f.kind, FragmentKind::Stem);
        assert_eq!(f.state, FragmentState::Captured);
        assert_eq!(f.audio_uri, "stemhash");
        assert!(f.parent_fragment_id.is_none());
    }

    #[test]
    fn kind_round_trips_through_db_str() {
        for k in FragmentKind::ALL {
            assert_eq!(FragmentKind::from_db_str(k.as_str()), Some(k));
        }
        assert_eq!(FragmentKind::from_db_str("banjo"), None);
    }
}
