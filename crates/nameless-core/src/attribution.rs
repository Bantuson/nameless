//! Attribution-clean sampling — the typed completeness invariant (SAMP-03, the integrity boundary).
//!
//! A `sampled` fragment is **literal copied audio** from someone else's recording. The project's
//! ethical line (PROJECT.md, PITFALLS.md Pitfall 7) is *attribution-clean sampling rather than
//! copy-and-claim-original*: a sample may enter an arrangement only if its source is fully recorded —
//! source track, artist, stem, and time-range. This module makes **incomplete-attribution placement
//! unrepresentable**, mirroring how the eval gate makes ungated AI placement unrepresentable: *the
//! harness gates; the agent explores.*
//!
//! ## The invariant, by type
//!
//! * [`PartialAttribution`] — what the CLI gathers from flags + the stem. Every field is
//!   `Option<…>`, because a human may supply an incomplete set.
//! * [`CompleteAttribution`] — every field is **non-`Option`**. It is therefore *structurally
//!   incapable* of representing a missing field. The ONLY way to obtain one from user input is
//!   [`PartialAttribution::into_complete`], which validates and, on success, hands back the proof.
//! * The sampled-placement gate ([`crate::state_machine::place`]) requires a `&CompleteAttribution`.
//!   A `sampled` fragment with only partial attribution simply has no value of the required type to
//!   pass — there is no bypass to forget, because the bypass cannot be spelled.
//!
//! This is the same rigour the PRD applies to the eval gate, expressed for attribution: the absence
//! of a constructor for an *incomplete* `CompleteAttribution` is the guarantee.
//!
//! ## Rights status is not permission (SAMP-04)
//!
//! Attribution records *provenance and honesty*; it does **not** confer the right to use the sample.
//! [`RightsStatus`] is a first-class field on every attribution, and the credits sheet
//! ([`credits_sheet`]) states explicitly that **attribution ≠ permission** — sampling a copyrighted
//! recording infringes regardless of personal/portfolio intent (PITFALLS.md Pitfall 7).

use serde::{Deserialize, Serialize};

use crate::fragment::{now_ms, FragmentId, ProjectId};
use crate::reference::ReferenceTrackId;
use crate::stems::{StemId, StemType};

/// The legal/clearance status of a sample's source — honest from day one (SAMP-04).
///
/// Clearance *gating* is out of scope (v2), but recording the status is cheap now and makes a future
/// commercial step tractable instead of a forensic nightmare (PITFALLS.md Pitfall 7). The system
/// never treats any of these as permission; the credits sheet says so.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RightsStatus {
    /// A copyrighted recording, not cleared. Using it is infringement; keep it out of public output.
    CopyrightedUncleared,
    /// Royalty-free / Creative-Commons / cleared library material.
    RoyaltyFree,
    /// The producer's own recording.
    OwnWork,
    /// Provenance not yet established. The honest default when unsure.
    Unknown,
}

impl RightsStatus {
    /// All variants — for `--rights` parsing + UI enumeration.
    pub const ALL: [RightsStatus; 4] = [
        RightsStatus::CopyrightedUncleared,
        RightsStatus::RoyaltyFree,
        RightsStatus::OwnWork,
        RightsStatus::Unknown,
    ];

    /// Stable snake_case label (matches serde + the DB `rights_status` enum).
    pub const fn as_str(self) -> &'static str {
        match self {
            RightsStatus::CopyrightedUncleared => "copyrighted_uncleared",
            RightsStatus::RoyaltyFree => "royalty_free",
            RightsStatus::OwnWork => "own_work",
            RightsStatus::Unknown => "unknown",
        }
    }

    /// Parse from the canonical label. Also accepts the CLI-friendly hyphen spellings.
    pub fn from_db_str(s: &str) -> Option<RightsStatus> {
        match s {
            "copyrighted_uncleared" | "copyrighted-uncleared" => {
                Some(RightsStatus::CopyrightedUncleared)
            }
            "royalty_free" | "royalty-free" => Some(RightsStatus::RoyaltyFree),
            "own_work" | "own-work" => Some(RightsStatus::OwnWork),
            "unknown" => Some(RightsStatus::Unknown),
            _ => None,
        }
    }

    /// A short human note shown next to the status — reinforces that a status is not a clearance.
    pub const fn note(self) -> &'static str {
        match self {
            RightsStatus::CopyrightedUncleared => {
                "copyrighted, NOT cleared — do not publish output containing this sample"
            }
            RightsStatus::RoyaltyFree => "royalty-free / cleared library material",
            RightsStatus::OwnWork => "the producer's own recording",
            RightsStatus::Unknown => "provenance unestablished — treat as uncleared until verified",
        }
    }
}

/// One named field that was missing when validating a [`PartialAttribution`].
///
/// Returned inside [`IncompleteAttribution`] so the failure names exactly what to supply (the CLI
/// prints these). A typed enum (not a string) so callers can match/aggregate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttributionField {
    SourceTrack,
    Stem,
    SourceTitle,
    SourceArtist,
    StemType,
    TimeRange,
    RightsStatus,
}

impl AttributionField {
    /// The CLI-facing name of the field / flag that supplies it.
    pub const fn as_str(self) -> &'static str {
        match self {
            AttributionField::SourceTrack => "source_track",
            AttributionField::Stem => "stem",
            AttributionField::SourceTitle => "source_title",
            AttributionField::SourceArtist => "artist",
            AttributionField::StemType => "stem_type",
            AttributionField::TimeRange => "time_range",
            AttributionField::RightsStatus => "rights",
        }
    }
}

/// The hard block on promoting/placing a sample without full attribution (SAMP-03).
///
/// Returned (never panicked, never a silent default) so a caller MUST handle the incomplete case —
/// this is the typed error that makes "place a sample with missing attribution" an explicit,
/// unignorable failure rather than a quietly-accepted blank credit (PITFALLS.md Anti-Pattern 5).
/// `Display` lists exactly the fields still required (`Error` impl is hand-written so the message can
/// join the field list — a derive macro cannot).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IncompleteAttribution {
    pub missing: Vec<AttributionField>,
}

impl std::fmt::Display for IncompleteAttribution {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let names: Vec<&str> = self.missing.iter().map(|m| m.as_str()).collect();
        write!(f, "incomplete attribution: missing {}", names.join(", "))
    }
}

impl std::error::Error for IncompleteAttribution {}

/// Attribution as GATHERED — every field optional, because user input may be incomplete.
///
/// This is the *input* to validation. It can be built field-by-field (the CLI fills it from the
/// resolved stem + the `--artist` / `--time-range` / `--rights` flags). It carries no authority on
/// its own: only [`into_complete`](PartialAttribution::into_complete) can turn it into the gate token.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct PartialAttribution {
    pub source_track_id: Option<ReferenceTrackId>,
    pub stem_id: Option<StemId>,
    pub source_title: Option<String>,
    pub source_artist: Option<String>,
    pub stem_type: Option<StemType>,
    pub start_ms: Option<u32>,
    pub end_ms: Option<u32>,
    pub rights_status: Option<RightsStatus>,
}

impl PartialAttribution {
    /// List the fields still missing for completeness — the pure completeness *predicate*.
    ///
    /// Empty ⇒ complete. Non-empty ⇒ exactly what [`into_complete`](Self::into_complete) will reject
    /// on. A blank/whitespace title or artist counts as missing (an empty credit is not a credit).
    /// A time range present but inverted (`end <= start`) reports `TimeRange` as missing too.
    pub fn missing_fields(&self) -> Vec<AttributionField> {
        let mut missing = Vec::new();
        if self.source_track_id.is_none() {
            missing.push(AttributionField::SourceTrack);
        }
        if self.stem_id.is_none() {
            missing.push(AttributionField::Stem);
        }
        if self.source_title.as_deref().map(str::trim).unwrap_or("").is_empty() {
            missing.push(AttributionField::SourceTitle);
        }
        if self
            .source_artist
            .as_deref()
            .map(str::trim)
            .unwrap_or("")
            .is_empty()
        {
            missing.push(AttributionField::SourceArtist);
        }
        if self.stem_type.is_none() {
            missing.push(AttributionField::StemType);
        }
        // A time range needs both ends AND a positive span.
        match (self.start_ms, self.end_ms) {
            (Some(s), Some(e)) if e > s => {}
            _ => missing.push(AttributionField::TimeRange),
        }
        if self.rights_status.is_none() {
            missing.push(AttributionField::RightsStatus);
        }
        missing
    }

    /// True when nothing is missing.
    pub fn is_complete(&self) -> bool {
        self.missing_fields().is_empty()
    }

    /// Validate → the gate token, or the typed list of what is missing (SAMP-03).
    ///
    /// This is the ONLY path from user-supplied (partial) attribution to a [`CompleteAttribution`].
    /// On success every field is present and the time range is a positive span; the returned value
    /// is the proof the placement gate demands.
    pub fn into_complete(self) -> Result<CompleteAttribution, IncompleteAttribution> {
        let missing = self.missing_fields();
        if !missing.is_empty() {
            return Err(IncompleteAttribution { missing });
        }
        // Every unwrap below is guarded by the missing-field check above.
        Ok(CompleteAttribution {
            source_track_id: self.source_track_id.unwrap(),
            stem_id: self.stem_id.unwrap(),
            source_title: self.source_title.unwrap().trim().to_string(),
            source_artist: self.source_artist.unwrap().trim().to_string(),
            stem_type: self.stem_type.unwrap(),
            start_ms: self.start_ms.unwrap(),
            end_ms: self.end_ms.unwrap(),
            rights_status: self.rights_status.unwrap(),
        })
    }
}

/// Attribution that is COMPLETE by construction — the placement gate's required token (SAMP-03).
///
/// Every field is non-`Option`: this type *cannot represent* a missing field, so a value of this
/// type is always a full, honest credit. There is no public constructor that yields an incomplete
/// instance — [`PartialAttribution::into_complete`] validates user input, and [`CompleteAttribution::new`]
/// (used to rehydrate a row the DB already validated as `NOT NULL`) likewise demands every field. The
/// `derive(Deserialize)` is safe for the same reason: a JSON object missing any field fails to
/// deserialize, so it can never produce an incomplete value.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CompleteAttribution {
    pub source_track_id: ReferenceTrackId,
    pub stem_id: StemId,
    pub source_title: String,
    pub source_artist: String,
    pub stem_type: StemType,
    pub start_ms: u32,
    pub end_ms: u32,
    pub rights_status: RightsStatus,
}

impl CompleteAttribution {
    /// Rehydrate from already-validated parts (e.g. a `NOT NULL` DB row). Because every parameter is
    /// non-`Option`, a caller physically cannot build an incomplete value through here either — the
    /// completeness guarantee is the *type*, not the constructor.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        source_track_id: ReferenceTrackId,
        stem_id: StemId,
        source_title: String,
        source_artist: String,
        stem_type: StemType,
        start_ms: u32,
        end_ms: u32,
        rights_status: RightsStatus,
    ) -> Self {
        CompleteAttribution {
            source_track_id,
            stem_id,
            source_title,
            source_artist,
            stem_type,
            start_ms,
            end_ms,
            rights_status,
        }
    }

    /// The sample's span in milliseconds.
    pub fn duration_ms(&self) -> u32 {
        self.end_ms.saturating_sub(self.start_ms)
    }
}

/// A persisted `sample_attribution` row — a [`CompleteAttribution`] bound to its sampled fragment.
///
/// Present iff a fragment has `provenance = sampled`. It carries the project (so the credits sheet
/// can enumerate a project's samples directly) and the fragment it credits, plus the complete
/// attribution proof. Built only from a [`CompleteAttribution`], so a persisted attribution is
/// always complete by construction — the credits exporter just reads these rows (no lazy fill-in).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SampleAttribution {
    pub fragment_id: FragmentId,
    pub project_id: ProjectId,
    pub attribution: CompleteAttribution,
    pub created_at_ms: i64,
}

impl SampleAttribution {
    /// Bind a complete attribution to a sampled fragment in a project.
    pub fn new(
        fragment_id: FragmentId,
        project_id: ProjectId,
        attribution: CompleteAttribution,
    ) -> Self {
        SampleAttribution {
            fragment_id,
            project_id,
            attribution,
            created_at_ms: now_ms(),
        }
    }
}

/// Render a credits sheet from a project's sample-attribution rows (SAMP-05). Pure: text in, text out.
///
/// Markdown, deterministic (sorted by artist then title), and ALWAYS prefixed with the honest legal
/// notice that **attribution is not permission** (SAMP-04 / PITFALLS.md Pitfall 7). Each sample lists
/// source title + artist, the stem isolated, the time-range used, and its rights status with a plain
/// note. The exporter at M1 will attach this sheet to the rendered track (and write tags); here it is
/// produced from the rows the control plane already holds.
pub fn credits_sheet(project_title: &str, rows: &[SampleAttribution]) -> String {
    let mut sorted: Vec<&SampleAttribution> = rows.iter().collect();
    sorted.sort_by(|a, b| {
        let aa = &a.attribution;
        let bb = &b.attribution;
        aa.source_artist
            .to_lowercase()
            .cmp(&bb.source_artist.to_lowercase())
            .then_with(|| aa.source_title.to_lowercase().cmp(&bb.source_title.to_lowercase()))
    });

    let mut out = String::new();
    out.push_str(&format!("# Credits — {project_title}\n\n"));

    // The non-negotiable honesty line (SAMP-04). It leads, so it can never be missed.
    out.push_str(
        "> **Attribution is not permission.** Sampling a copyrighted recording is infringement \
         regardless of personal or portfolio intent; crediting a source does not make using it \
         legal. Clear every `copyrighted_uncleared` / `unknown` sample before publishing output \
         that contains it.\n\n",
    );

    if sorted.is_empty() {
        out.push_str("_No samples in this project._\n");
        return out;
    }

    out.push_str(&format!(
        "{} sampled fragment{} in this project:\n\n",
        sorted.len(),
        if sorted.len() == 1 { "" } else { "s" }
    ));

    for (i, row) in sorted.iter().enumerate() {
        let a = &row.attribution;
        out.push_str(&format!(
            "{}. **{}** — {}\n",
            i + 1,
            a.source_title,
            a.source_artist
        ));
        out.push_str(&format!(
            "   - stem: `{}`  ·  range: {}–{} ms ({} ms)\n",
            a.stem_type.as_str(),
            a.start_ms,
            a.end_ms,
            a.duration_ms()
        ));
        out.push_str(&format!(
            "   - rights: `{}` — {}\n",
            a.rights_status.as_str(),
            a.rights_status.note()
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn full_partial() -> PartialAttribution {
        PartialAttribution {
            source_track_id: Some(ReferenceTrackId::new()),
            stem_id: Some(StemId::new()),
            source_title: Some("Trust".into()),
            source_artist: Some("Brent Faiyaz".into()),
            stem_type: Some(StemType::Vocals),
            start_ms: Some(12_000),
            end_ms: Some(18_000),
            rights_status: Some(RightsStatus::CopyrightedUncleared),
        }
    }

    #[test]
    fn rights_status_round_trips_and_accepts_hyphen_spelling() {
        for r in RightsStatus::ALL {
            assert_eq!(RightsStatus::from_db_str(r.as_str()), Some(r));
        }
        assert_eq!(
            RightsStatus::from_db_str("royalty-free"),
            Some(RightsStatus::RoyaltyFree)
        );
        assert_eq!(RightsStatus::from_db_str("cleared"), None);
    }

    #[test]
    fn full_partial_is_complete_and_validates() {
        let p = full_partial();
        assert!(p.is_complete());
        assert!(p.missing_fields().is_empty());
        let c = p.into_complete().unwrap();
        assert_eq!(c.source_title, "Trust");
        assert_eq!(c.duration_ms(), 6_000);
    }

    #[test]
    fn missing_fields_are_reported_and_block_completion() {
        let p = PartialAttribution {
            source_artist: Some("   ".into()), // whitespace = missing (empty credit is no credit)
            start_ms: Some(5_000),
            end_ms: Some(5_000), // zero span = missing time range
            ..Default::default()
        };
        let missing = p.missing_fields();
        assert!(missing.contains(&AttributionField::SourceTrack));
        assert!(missing.contains(&AttributionField::Stem));
        assert!(missing.contains(&AttributionField::SourceTitle));
        assert!(missing.contains(&AttributionField::SourceArtist)); // whitespace-only
        assert!(missing.contains(&AttributionField::StemType));
        assert!(missing.contains(&AttributionField::TimeRange)); // end == start
        assert!(missing.contains(&AttributionField::RightsStatus));

        let err = p.into_complete().unwrap_err();
        assert_eq!(err.missing, missing);
        assert!(err.to_string().contains("artist"));
        assert!(err.to_string().contains("time_range"));
    }

    #[test]
    fn inverted_time_range_is_incomplete() {
        let mut p = full_partial();
        p.start_ms = Some(20_000);
        p.end_ms = Some(10_000); // end < start
        assert!(!p.is_complete());
        assert_eq!(p.missing_fields(), vec![AttributionField::TimeRange]);
        assert!(p.into_complete().is_err());
    }

    #[test]
    fn complete_attribution_deserialize_requires_every_field() {
        // A JSON object missing a field cannot produce a CompleteAttribution — the type's
        // completeness survives the serde boundary (there is no Option to leave null).
        let c = full_partial().into_complete().unwrap();
        let json = serde_json::to_string(&c).unwrap();
        let back: CompleteAttribution = serde_json::from_str(&json).unwrap();
        assert_eq!(c, back);
        // Drop a required field → deserialization fails (cannot represent an incomplete value).
        let broken = json.replace(",\"source_artist\":\"Brent Faiyaz\"", "");
        assert!(serde_json::from_str::<CompleteAttribution>(&broken).is_err());
    }

    #[test]
    fn credits_sheet_leads_with_the_permission_notice_and_lists_each_sample() {
        let project = ProjectId::new();
        let rows = vec![
            SampleAttribution::new(
                FragmentId::new(),
                project,
                full_partial().into_complete().unwrap(),
            ),
            SampleAttribution::new(FragmentId::new(), project, {
                let mut p = full_partial();
                p.source_title = Some("Wasting Time".into());
                p.source_artist = Some("Brent Faiyaz".into());
                p.stem_type = Some(StemType::Piano);
                p.rights_status = Some(RightsStatus::OwnWork);
                p.into_complete().unwrap()
            }),
        ];
        let sheet = credits_sheet("Late Night Tape", &rows);
        // The permission notice leads.
        assert!(sheet.contains("Attribution is not permission"));
        // Both samples are present, with stem + range + rights.
        assert!(sheet.contains("Trust"));
        assert!(sheet.contains("Wasting Time"));
        assert!(sheet.contains("`piano`"));
        assert!(sheet.contains("copyrighted_uncleared"));
        assert!(sheet.contains("12000–18000 ms"));
        // Deterministic count line.
        assert!(sheet.contains("2 sampled fragments in this project"));
    }

    #[test]
    fn credits_sheet_handles_empty_project() {
        let sheet = credits_sheet("Empty", &[]);
        assert!(sheet.contains("Attribution is not permission"));
        assert!(sheet.contains("No samples in this project"));
    }
}
