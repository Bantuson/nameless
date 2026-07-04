//! Reference tracks — uploaded finished songs used as *conditioning context*, never as fragments.
//!
//! A producer uploads a song they love; the system extracts its **vibe + measurable non-melodic
//! sonic targets** and attaches that as conditioning to a project. The product line the architecture
//! draws (ARCHITECTURE.md Pattern 2, PITFALLS.md Pitfall 6) is a hard one: *imitate the vibe* must
//! never become *reproduce the song*.
//!
//! ## The non-cloning guarantee is STRUCTURAL, not conventional (REF-03 — the headline)
//!
//! This module makes cloning **physically un-representable**, not merely discouraged:
//!
//! 1. A [`ReferenceTrack`] is a SEPARATE type from [`crate::fragment::Fragment`]. It has no
//!    lifecycle state, no provenance, no `FragmentKind` — it can never enter the fragment state
//!    machine, so it can never be "placed", "mixed", or "rendered" into an arrangement.
//! 2. [`ReferenceContext`] — the only runtime surface a reference exposes — contains ONLY
//!    non-melodic fields: a CLAP *style* embedding, genre, tempo *range*, LUFS, tonal balance,
//!    stereo width, and a human-facing vibe description. **There is deliberately no melody / chroma
//!    / f0 / chord / structure column on it.** What you cannot store, you cannot clone from: a
//!    reference's tune is never extracted as a conditioning target, so it can never leak into
//!    generation (see [`crate::conditioning`] for the matching type-level barrier on the consuming
//!    side).
//!
//! The asymmetry is *typed*, exactly the rigour the PRD already applies to the eval gate: "the
//! harness gates; the agent explores." Here the type system gates — an LLM-driven caller cannot even
//! express the cloning operation.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::fragment::now_ms;

/// Strongly-typed reference-track identifier (newtype over UUID, serde-transparent).
///
/// A distinct newtype from `FragmentId`/`ProjectId` so a reference id can never be passed where a
/// fragment id is expected — the compiler keeps the two worlds (placeable fragments vs. read-only
/// conditioning context) from ever being confused at a call site.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ReferenceTrackId(pub Uuid);

impl ReferenceTrackId {
    /// Mint a fresh random id.
    pub fn new() -> Self {
        ReferenceTrackId(Uuid::new_v4())
    }
}

impl Default for ReferenceTrackId {
    fn default() -> Self {
        Self::new()
    }
}

impl std::fmt::Display for ReferenceTrackId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// An uploaded finished track — a distinct entity, NOT a [`crate::fragment::Fragment`].
///
/// Carries only enough to address the immutable audio (by content-hash uri, exactly like a
/// fragment's audio) and label it for the credits/UI. It intentionally has NO provenance, NO
/// lifecycle state, and NO `kind`: a reference is never placed, mixed, or rendered. The raw audio is
/// retained (Phase 8 stem-library shares this upload machinery) but it informs generation only via
/// the derived [`ReferenceContext`], never by being copied into an arrangement.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReferenceTrack {
    pub id: ReferenceTrackId,
    /// Immutable object-store key (SHA-256 content hash) — NEVER the audio bytes themselves.
    pub audio_uri: String,
    /// Optional human label (drives the credits sheet + UI; never used as a conditioning target).
    pub title: Option<String>,
    pub artist: Option<String>,
    pub duration_ms: Option<u32>,
    pub sample_rate: Option<u32>,
    /// Unix epoch milliseconds at upload.
    pub uploaded_at_ms: i64,
}

impl ReferenceTrack {
    /// Build a freshly-uploaded reference track. `audio_uri` is the content hash the caller already
    /// computed + stored via the [`crate::ports::ObjectStore`] (the same path a capture uses).
    pub fn new_upload(
        audio_uri: String,
        title: Option<String>,
        artist: Option<String>,
        duration_ms: Option<u32>,
        sample_rate: Option<u32>,
    ) -> Self {
        ReferenceTrack {
            id: ReferenceTrackId::new(),
            audio_uri,
            title,
            artist,
            duration_ms,
            sample_rate,
            uploaded_at_ms: now_ms(),
        }
    }
}

/// Coarse multiband energy balance — "where the energy sits", NOT the notes (PITFALLS.md Pitfall 5).
///
/// Five broad bands whose ratios sum to ~1.0. This is a *spectral-shape* descriptor (a mix target:
/// "is this track bright? bass-heavy?"), deliberately too coarse to encode a melody or chord — the
/// 12 chroma pitch classes are folded away into 5 frequency regions. The Python
/// `pure/tonal_balance.py` computes these from band RMS; this type only carries the result.
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct TonalBalance {
    /// ~20–120 Hz (sub).
    pub low: f32,
    /// ~120–500 Hz (low-mids / body).
    pub low_mid: f32,
    /// ~500–2k Hz (mids / presence).
    pub mid: f32,
    /// ~2k–6k Hz (high-mids / definition).
    pub high_mid: f32,
    /// ~6k–20k Hz (air / brilliance).
    pub high: f32,
}

// Hand-written Deserialize (WR-01): the DERIVED impl also accepts a positional SEQUENCE
// (`[0.3, 0.25, ...]` parses field-by-index), which is exactly the bands-array shape the
// cross-language jsonb contract forbids. Driving `deserialize_map` through a map-only visitor
// makes the array form a hard error while keeping the named-key object shape identical to what
// the Python analyzer's `model_dump()` persists.
impl<'de> serde::Deserialize<'de> for TonalBalance {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct TonalBalanceVisitor;

        impl<'de> serde::de::Visitor<'de> for TonalBalanceVisitor {
            type Value = TonalBalance;

            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("a tonal-balance object with named low/low_mid/mid/high_mid/high keys")
            }

            fn visit_map<A>(self, mut map: A) -> Result<TonalBalance, A::Error>
            where
                A: serde::de::MapAccess<'de>,
            {
                const FIELDS: &[&str] = &["low", "low_mid", "mid", "high_mid", "high"];
                let (mut low, mut low_mid, mut mid, mut high_mid, mut high) =
                    (None, None, None, None, None);
                while let Some(key) = map.next_key::<String>()? {
                    match key.as_str() {
                        "low" => {
                            if low.replace(map.next_value()?).is_some() {
                                return Err(serde::de::Error::duplicate_field("low"));
                            }
                        }
                        "low_mid" => {
                            if low_mid.replace(map.next_value()?).is_some() {
                                return Err(serde::de::Error::duplicate_field("low_mid"));
                            }
                        }
                        "mid" => {
                            if mid.replace(map.next_value()?).is_some() {
                                return Err(serde::de::Error::duplicate_field("mid"));
                            }
                        }
                        "high_mid" => {
                            if high_mid.replace(map.next_value()?).is_some() {
                                return Err(serde::de::Error::duplicate_field("high_mid"));
                            }
                        }
                        "high" => {
                            if high.replace(map.next_value()?).is_some() {
                                return Err(serde::de::Error::duplicate_field("high"));
                            }
                        }
                        other => return Err(serde::de::Error::unknown_field(other, FIELDS)),
                    }
                }
                Ok(TonalBalance {
                    low: low.ok_or_else(|| serde::de::Error::missing_field("low"))?,
                    low_mid: low_mid.ok_or_else(|| serde::de::Error::missing_field("low_mid"))?,
                    mid: mid.ok_or_else(|| serde::de::Error::missing_field("mid"))?,
                    high_mid: high_mid
                        .ok_or_else(|| serde::de::Error::missing_field("high_mid"))?,
                    high: high.ok_or_else(|| serde::de::Error::missing_field("high"))?,
                })
            }
        }

        deserializer.deserialize_map(TonalBalanceVisitor)
    }
}

impl TonalBalance {
    /// The five band ratios in low→high order. Useful for compact rendering + tests.
    pub fn bands(&self) -> [f32; 5] {
        [self.low, self.low_mid, self.mid, self.high_mid, self.high]
    }

    /// Sum of the band ratios (≈1.0 when normalized; surfaced so a test/round-trip can assert it).
    pub fn total(&self) -> f32 {
        self.bands().iter().sum()
    }
}

/// What role a reference plays for a project (the link-table `role`).
///
/// A typed enum rather than free text so the link is exhaustively matchable, mirroring how
/// `Provenance`/`FragmentState` are typed. Both roles still expose ONLY non-melodic context — the
/// role tunes *emphasis* (atmosphere vs. measurable mix targets), never *what* is exposed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReferenceRole {
    /// "Steer the mood/atmosphere" — leans on the CLAP style embedding + vibe description.
    Vibe,
    /// "Hit these measurable numbers" — leans on tempo range / LUFS / tonal balance / stereo width.
    SonicTarget,
}

impl ReferenceRole {
    /// All variants — for `--role` parsing + UI enumeration.
    pub const ALL: [ReferenceRole; 2] = [ReferenceRole::Vibe, ReferenceRole::SonicTarget];

    /// Stable snake_case label, matching the Postgres `reference_role` enum + serde form.
    pub const fn as_str(self) -> &'static str {
        match self {
            ReferenceRole::Vibe => "vibe",
            ReferenceRole::SonicTarget => "sonic_target",
        }
    }

    /// Parse from the canonical label. Accepts the CLI-friendly `sonic-target` spelling too.
    pub fn from_db_str(s: &str) -> Option<ReferenceRole> {
        match s {
            "vibe" => Some(ReferenceRole::Vibe),
            "sonic_target" | "sonic-target" => Some(ReferenceRole::SonicTarget),
            _ => None,
        }
    }
}

/// Extracted reference CONTEXT — vibe + measurable NON-melodic targets only (REF-02).
///
/// This is the single runtime surface a reference exposes. Every field below is a non-melodic
/// descriptor:
/// * `clap_style_embedding` — a joint audio-text *style/vibe* vector (advisory conditioning +
///   retrieval). It is a global timbral fingerprint, NOT a note sequence; the worker computes it
///   with the CLAP **audio tower** over the whole track and never derives chroma/f0 from it.
/// * `genre`, `tempo_bpm_min`/`tempo_bpm_max` (a *range*, not a beat grid), `lufs`,
///   `tonal_balance`, `stereo_width` — measurable mix/atmosphere targets.
/// * `vibe_description` — an LLM's prose (mood/space/era/texture/energy), clearly an interpretation,
///   never a generation target.
///
/// ## What is deliberately ABSENT (the structural guarantee)
///
/// There is **no** `f0` / `chroma` / `melody` / `chord` / `structure` / `key` field on this struct,
/// and there is no way to add one without an explicit, reviewable schema + type change. The
/// reference's melodic content is simply never materialized as conditioning, so generation has
/// nothing to clone from — non-cloning falls out of the type, not out of a runtime check that could
/// be forgotten.
///
/// The Python worker writes this row (mirroring how the Phase-2 feature worker — not Rust — writes
/// `fragment_features`); the Rust control plane reads back the compact [`ReferenceContextSummary`]
/// for `reference show` and never surfaces the embedding vector (the token/compact-output contract).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReferenceContext {
    pub reference_track_id: ReferenceTrackId,
    /// CLAP audio-tower *style* embedding (advisory conditioning; addressed by ID, never printed).
    pub clap_style_embedding: Vec<f32>,
    pub genre: Option<String>,
    /// Tempo as a RANGE (a target band), not a per-beat grid — coarse on purpose.
    pub tempo_bpm_min: f32,
    pub tempo_bpm_max: f32,
    /// Integrated loudness (ITU-R BS.1770-4), a mastering target.
    pub lufs: f32,
    pub tonal_balance: TonalBalance,
    /// Mid/side energy ratio in [0,1]; 0 = mono, →1 = very wide.
    pub stereo_width: f32,
    /// LLM prose: mood / space / era / texture / energy. Interpretation, not a measured target.
    pub vibe_description: String,
    /// Which analyzer + checkpoint produced this (re-analysis is detectable when it changes).
    pub analyzer_version: String,
}

impl ReferenceContext {
    /// Project to the compact summary the CLI is allowed to print — drops the embedding vector,
    /// keeping only its dimension. This is the chokepoint that keeps the conditioning *vector*
    /// (a large array) out of agent context while still letting `reference show` report "vibe +
    /// targets". By construction `ReferenceContextSummary` has no field that can hold an array, so a
    /// renderer physically cannot leak one (mirrors the Python `SearchHit`/compact-model discipline).
    pub fn summary(&self) -> ReferenceContextSummary {
        ReferenceContextSummary {
            reference_track_id: self.reference_track_id,
            genre: self.genre.clone(),
            tempo_bpm_min: self.tempo_bpm_min,
            tempo_bpm_max: self.tempo_bpm_max,
            lufs: self.lufs,
            tonal_balance: self.tonal_balance,
            stereo_width: self.stereo_width,
            vibe_description: self.vibe_description.clone(),
            embedding_dim: self.clap_style_embedding.len(),
            analyzer_version: self.analyzer_version.clone(),
        }
    }
}

/// The compact, array-free view of a [`ReferenceContext`] for `reference show`.
///
/// Carries `embedding_dim` (a single integer) instead of the embedding itself, and — like the rest
/// of the type — has NO melodic field. Whatever the CLI does, it cannot print the style vector or a
/// melody, because neither has a field here to live in.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReferenceContextSummary {
    pub reference_track_id: ReferenceTrackId,
    pub genre: Option<String>,
    pub tempo_bpm_min: f32,
    pub tempo_bpm_max: f32,
    pub lufs: f32,
    pub tonal_balance: TonalBalance,
    pub stereo_width: f32,
    pub vibe_description: String,
    /// Dimension of the (un-exposed) CLAP style embedding — a count, never the vector.
    pub embedding_dim: usize,
    pub analyzer_version: String,
}

/// A project↔reference attachment with its role (one row of `project_reference_context`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectReference {
    pub reference_track_id: ReferenceTrackId,
    pub role: ReferenceRole,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn upload_sets_id_uri_and_timestamp() {
        let r = ReferenceTrack::new_upload(
            "deadbeef".into(),
            Some("Trust".into()),
            Some("Brent Faiyaz".into()),
            Some(210_000),
            Some(44_100),
        );
        assert_eq!(r.audio_uri, "deadbeef");
        assert_eq!(r.artist.as_deref(), Some("Brent Faiyaz"));
        assert!(r.uploaded_at_ms >= 0);
    }

    #[test]
    fn reference_role_round_trips_and_accepts_cli_spelling() {
        for role in ReferenceRole::ALL {
            assert_eq!(ReferenceRole::from_db_str(role.as_str()), Some(role));
        }
        // CLI-friendly hyphen spelling parses to the same variant the DB stores as snake_case.
        assert_eq!(
            ReferenceRole::from_db_str("sonic-target"),
            Some(ReferenceRole::SonicTarget)
        );
        assert_eq!(ReferenceRole::from_db_str("melody"), None);
    }

    #[test]
    fn tonal_balance_bands_and_total() {
        let tb = TonalBalance {
            low: 0.30,
            low_mid: 0.25,
            mid: 0.20,
            high_mid: 0.15,
            high: 0.10,
        };
        assert_eq!(tb.bands().len(), 5);
        assert!((tb.total() - 1.0).abs() < 1e-6);
    }

    /// WR-01 — pin the cross-language `tonal_balance` jsonb contract. The Python analyzer persists
    /// `NonMelodicFeatures.tonal_balance.model_dump()`, i.e. the named-key OBJECT, and this is the
    /// exact shape `get_context_summary` deserializes. This test deserializes that object shape and
    /// asserts the bands-ARRAY shape (used only for compact CLI/log output) is REJECTED — so a writer
    /// that accidentally emitted the array would be caught here rather than failing at runtime.
    #[test]
    fn tonal_balance_jsonb_contract_is_the_named_object_not_an_array() {
        // The persisted/object shape (matches Python model_dump()).
        let object = r#"{"low":0.3,"low_mid":0.25,"mid":0.2,"high_mid":0.15,"high":0.1}"#;
        let tb: TonalBalance = serde_json::from_str(object).expect("named-key object must parse");
        assert_eq!(tb.bands(), [0.3, 0.25, 0.2, 0.15, 0.1]);
        assert!((tb.total() - 1.0).abs() < 1e-6);

        // The bands-array shape is the WRONG contract and must NOT deserialize into the struct.
        let array = r#"[0.3,0.25,0.2,0.15,0.1]"#;
        assert!(
            serde_json::from_str::<TonalBalance>(array).is_err(),
            "the bands ARRAY form must not parse as TonalBalance — only the named-key object is the \
             pinned jsonb contract"
        );
    }

    #[test]
    fn summary_drops_the_embedding_vector_but_keeps_its_dim() {
        // Fill the embedding with a DISTINCTIVE sentinel value that appears nowhere else (not in the
        // tonal-balance ratios, tempo, lufs, etc.), so "it's absent from the summary JSON" actually
        // proves the vector was dropped rather than colliding with another field's value.
        let sentinel = 0.137913f32;
        let ctx = ReferenceContext {
            reference_track_id: ReferenceTrackId::new(),
            clap_style_embedding: vec![sentinel; 512],
            genre: Some("amapiano".into()),
            tempo_bpm_min: 110.0,
            tempo_bpm_max: 116.0,
            lufs: -9.5,
            tonal_balance: TonalBalance {
                low: 0.3,
                low_mid: 0.25,
                mid: 0.2,
                high_mid: 0.15,
                high: 0.1,
            },
            stereo_width: 0.42,
            vibe_description: "warm, spacious, late-night".into(),
            analyzer_version: "fake-ref-0".into(),
        };
        let s = ctx.summary();
        // The compact view reports the dimension, never the vector itself.
        assert_eq!(s.embedding_dim, 512);
        // And it serializes WITHOUT any embedding/array field — the compact-output contract.
        let json = serde_json::to_string(&s).unwrap();
        assert!(!json.contains("clap_style_embedding"));
        assert!(!json.contains("style_embedding"));
        assert!(!json.contains("0.137913")); // the sentinel embedding value never leaks
        assert!(json.contains("\"embedding_dim\":512"));
    }

    /// STRUCTURAL non-cloning proof (REF-03), expressed as far as Rust reflection allows: the
    /// serialized `ReferenceContext` contains none of the melodic field names. If a future edit
    /// tried to add a melody/chroma/f0/structure column, this test fails — a deliberate tripwire.
    #[test]
    fn reference_context_carries_no_melodic_field() {
        let ctx = ReferenceContext {
            reference_track_id: ReferenceTrackId::new(),
            clap_style_embedding: vec![],
            genre: None,
            tempo_bpm_min: 90.0,
            tempo_bpm_max: 96.0,
            lufs: -10.0,
            tonal_balance: TonalBalance {
                low: 0.2,
                low_mid: 0.2,
                mid: 0.2,
                high_mid: 0.2,
                high: 0.2,
            },
            stereo_width: 0.5,
            vibe_description: "x".into(),
            analyzer_version: "v".into(),
        };
        let json = serde_json::to_string(&ctx).unwrap();
        // Check for the forbidden names as serialized JSON KEYS (`"name":`), not bare substrings:
        // a random UUID value can innocently contain hex like `f0`, but never the key form `"f0":`.
        for forbidden in [
            "\"f0\":",
            "\"f0_contour\":",
            "\"chroma\":",
            "\"chroma_mean\":",
            "\"melody\":",
            "\"chord\":",
            "\"chords\":",
            "\"structure\":",
            "\"key\":",
            "\"midi\":",
            "\"pitch\":",
        ] {
            assert!(
                !json.contains(forbidden),
                "ReferenceContext must expose no melodic field, found {forbidden:?}"
            );
        }
    }
}
