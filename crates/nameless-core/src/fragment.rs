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

use crate::attribution::CompleteAttribution;
use crate::provenance::Provenance;
use crate::state_machine::{
    place, transition, FragmentState, IllegalTransition, PlaceError, Transition,
};

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
    /// Provenance — how this fragment entered the graph. **PRIVATE by design:** it is set once at
    /// construction (`new_capture`/`new_sampled`/`from_persisted`) and never reassigned, so the
    /// eval gate (AI) and attribution gate (sampled) that key on it cannot be defeated by a stray
    /// `frag.provenance = …` (which will not compile outside this module). Read via
    /// [`Fragment::provenance`].
    provenance: Provenance,
    /// Immutable object-store key (SHA-256 content hash) — NEVER the audio bytes themselves.
    pub audio_uri: String,
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
    /// The intent channel — free text, also the compact node summary the agent reads.
    pub note_text: String,
    /// Lifecycle state. **PRIVATE by design** and mutated ONLY via [`Fragment::apply`] /
    /// [`Fragment::place`] (which drive the validated [`crate::state_machine::transition`]). A direct
    /// `frag.state = …` will not compile outside this module — that is what makes "an unanalyzed /
    /// ungated fragment can never be placed" a *structural* guarantee rather than a convention. Read
    /// via [`Fragment::state`].
    state: FragmentState,
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

    /// Read-only access to provenance. The field is private; provenance is fixed at construction.
    pub fn provenance(&self) -> Provenance {
        self.provenance
    }

    /// Read-only access to the lifecycle state. The field is private; the ONLY way to *change* it is
    /// [`Fragment::apply`] / [`Fragment::place`], so callers can observe but never forge state.
    pub fn state(&self) -> FragmentState {
        self.state
    }

    /// Reassemble a fragment from an already-persisted row (repository-adapter reconstruction path).
    ///
    /// This is the single sanctioned way to set `state`/`provenance` to *arbitrary* values, and it
    /// exists solely so an adapter can rebuild a fragment whose state was produced — and validated —
    /// by a prior live transition before being written to storage. It performs no transition check
    /// by design (the stored state is already legal). Because it is the only such constructor, every
    /// *live* mutation still funnels through `apply`/`place`; a stray field write elsewhere will not
    /// compile.
    #[allow(clippy::too_many_arguments)]
    pub fn from_persisted(
        id: FragmentId,
        project_id: ProjectId,
        kind: FragmentKind,
        provenance: Provenance,
        audio_uri: String,
        duration_ms: Option<u32>,
        sample_rate: Option<u32>,
        note_text: String,
        state: FragmentState,
        parent_fragment_id: Option<FragmentId>,
        created_at_ms: i64,
    ) -> Self {
        Fragment {
            id,
            project_id,
            kind,
            provenance,
            audio_uri,
            duration_ms,
            sample_rate,
            note_text,
            state,
            parent_fragment_id,
            created_at_ms,
        }
    }
}

impl Fragment {
    /// The ONLY way to mutate a fragment's lifecycle state for the non-placement verbs (and for
    /// non-sampled placement). Delegates to [`crate::state_machine::transition`] and assigns the
    /// result on success. Lives in this module (with the private `state` field) so that it — and
    /// [`Fragment::place`] — are the sole code that can write `state`; there is no setter to abuse.
    ///
    /// **Sampled placement is deliberately refused here.** A `sampled` fragment's `Place` edge
    /// carries an extra precondition — complete attribution — that `apply` cannot supply, so `apply`
    /// returns [`IllegalTransition`] for `(Sampled, Place)` and the ONLY way to place a sample is
    /// [`Fragment::place`] with a [`CompleteAttribution`]. This closes the would-be bypass: there is
    /// no ungated path that writes `Placed` onto a sample. (For human / ai / derived material `apply`
    /// keeps driving `Place` exactly as before — they have no attribution precondition.)
    pub fn apply(&mut self, t: Transition) -> Result<(), IllegalTransition> {
        if self.provenance == Provenance::Sampled && t == Transition::Place {
            return Err(IllegalTransition {
                from: self.state,
                transition: t,
            });
        }
        let next = transition(self.provenance, self.state, t)?;
        self.state = next;
        Ok(())
    }

    /// Place a fragment, enforcing the sampled-attribution gate (SAMP-03).
    ///
    /// This is the attribution-aware placement chokepoint. For a `sampled` fragment it REQUIRES a
    /// `Some(&CompleteAttribution)`; for any other provenance the argument is ignored (pass `None`).
    /// A driver that places a sample loads its [`crate::attribution::SampleAttribution`] row and
    /// passes `Some(&row.attribution)` — and since that row can only exist as a complete value, the
    /// gate is satisfiable exactly when (and only when) the sample is fully credited.
    pub fn place(&mut self, attribution: Option<&CompleteAttribution>) -> Result<(), PlaceError> {
        let next = place(self.provenance, self.state, attribution)?;
        self.state = next;
        Ok(())
    }
}

/// Test-only sanctioned builder. Compiled ONLY under `cfg(test)`, so production code in any phase
/// or crate physically cannot use it to forge provenance — it exists purely to set up fixtures
/// (e.g. an `AiGenerated` fragment) that the public constructors do not directly reach.
#[cfg(test)]
impl Fragment {
    /// Test-only: override provenance for a fixture. `cfg(test)` only.
    pub(crate) fn test_with_provenance(mut self, p: Provenance) -> Self {
        self.provenance = p;
        self
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
