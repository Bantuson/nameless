//! Generation conditioning — and the type-level wall between *melodic* and *non-melodic* inputs.
//!
//! M1 generation is conditioned on two very different kinds of input, and the whole non-cloning
//! story (REF-03, PITFALLS.md Pitfall 6) lives in keeping them in **separate types** so one can
//! never be substituted for the other:
//!
//! * [`MelodicConditioning`] — the producer's OWN material. The generator may follow this melody /
//!   chroma (that is the point: "make a bass that locks to my hum"). It is gathered ONLY from
//!   `human_recorded` [`Fragment`]s.
//! * [`ReferenceConditioning`] — vibe + measurable sonic targets distilled from an uploaded
//!   reference. It carries NO melody/chroma/structure (there is no such field on a
//!   [`ReferenceContext`] to begin with), so feeding it to the generator can steer *atmosphere and
//!   numbers* but can never reproduce the reference's tune.
//!
//! ## Why the barrier is structural, not a runtime check
//!
//! A melody-conditioned generator (MusicGen-Stem / MuseControlLite) *is designed to follow* whatever
//! reaches its melodic input. If a finished reference track ever reached that input, the system would
//! clone it while the builder believed it was doing "style transfer". The single shared feature path
//! + one forgotten branch is exactly how the leak happens. We close it by TYPE:
//!
//! [`gather_melodic_conditioning`] accepts `&[Fragment]`. A [`ReferenceTrack`] is a *different type*
//! with no conversion into `Fragment` — so a reference cannot even be passed to the melodic path.
//! The compiler rejects it; there is no runtime branch to forget. The `compile_fail` doctest on
//! that function is an executable proof of the wall.

use crate::fragment::{Fragment, FragmentId};
use crate::provenance::Provenance;
use crate::reference::{ReferenceContext, ReferenceTrackId, TonalBalance};

/// Melodic/structural conditioning for generation — gathered ONLY from the producer's own
/// `human_recorded` fragments.
///
/// Holds fragment *ids*, not feature arrays: the actual chroma/f0 live in `fragment_features` keyed
/// by these ids (PRD by-ID rule — arrays never travel inline / into agent context). The generator
/// worker resolves the ids to features at the edge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MelodicConditioning {
    /// The human-recorded fragments whose melody/chroma may be followed.
    pub source_fragment_ids: Vec<FragmentId>,
}

impl MelodicConditioning {
    /// True when there is no human material to condition on (the arranger must then ask the human,
    /// not borrow a reference's melody).
    pub fn is_empty(&self) -> bool {
        self.source_fragment_ids.is_empty()
    }
}

/// Gather melodic conditioning from the producer's fragments.
///
/// **Structural non-cloning (REF-03).** The parameter is `&[Fragment]`. A [`ReferenceTrack`] is a
/// separate type and has no conversion into `Fragment`, so it is *compile-time barred* from this
/// path — a reference's melody can never reach the generator's melodic input. Among the fragments
/// passed, only `human_recorded` ones are gathered: `ai_generated` material must clear the eval gate
/// (it is not a melodic *source*), and `derived`/`sampled` are out of scope for melodic conditioning
/// here (Pitfall 6: "Only `human_recorded` fragments feed melody conditioning").
///
/// The type-level wall, proven to NOT compile:
///
/// ```compile_fail
/// use nameless_core::{gather_melodic_conditioning, ReferenceTrack};
/// let reference = ReferenceTrack::new_upload("abc123".into(), None, None, None, None);
/// // ReferenceTrack is NOT a Fragment — there is no From/Into and no shared trait object,
/// // so this fails to type-check. A reference physically cannot enter the melodic path.
/// let _ = gather_melodic_conditioning(&[reference]);
/// ```
///
/// The legal call, with fragments:
///
/// ```
/// use nameless_core::{gather_melodic_conditioning, Fragment, FragmentKind, ProjectId};
/// let hum = Fragment::new_capture(
///     ProjectId::new(), FragmentKind::Melody, "hash".into(), None, None, "my hook".into(),
/// );
/// let cond = gather_melodic_conditioning(std::slice::from_ref(&hum));
/// assert_eq!(cond.source_fragment_ids, vec![hum.id]);
/// ```
pub fn gather_melodic_conditioning(fragments: &[Fragment]) -> MelodicConditioning {
    let source_fragment_ids = fragments
        .iter()
        .filter(|f| f.provenance == Provenance::HumanRecorded)
        .map(|f| f.id)
        .collect();
    MelodicConditioning {
        source_fragment_ids,
    }
}

/// Non-melodic conditioning derived from a reference track's context — vibe + sonic targets ONLY.
///
/// This is the bundle the M1 arranger/generator/eval-gate may consume as an optional conditioning
/// input (ARCHITECTURE.md Pattern 2 envelope). It is built FROM a [`ReferenceContext`] and, like
/// its source, has no melody/chroma/structure field — there is nothing here for the generator to
/// clone, by construction. The human-facing `vibe_description` prose is intentionally NOT included:
/// a poetic LLM guess is human context, never a machine conditioning target (PITFALLS.md Pitfall 5 —
/// keep measured targets and interpreted vibe in separate trust levels).
#[derive(Debug, Clone, PartialEq)]
pub struct ReferenceConditioning {
    pub reference_track_id: ReferenceTrackId,
    /// CLAP *style* vector — advisory direction for atmosphere/retrieval, not a melody.
    pub clap_style_embedding: Vec<f32>,
    pub genre: Option<String>,
    pub tempo_bpm_min: f32,
    pub tempo_bpm_max: f32,
    pub lufs: f32,
    pub tonal_balance: TonalBalance,
    pub stereo_width: f32,
}

impl ReferenceConditioning {
    /// Build the conditioning bundle from a stored [`ReferenceContext`]. Copies only the
    /// non-melodic targets + the advisory style embedding; drops the vibe prose.
    pub fn from_context(ctx: &ReferenceContext) -> Self {
        ReferenceConditioning {
            reference_track_id: ctx.reference_track_id,
            clap_style_embedding: ctx.clap_style_embedding.clone(),
            genre: ctx.genre.clone(),
            tempo_bpm_min: ctx.tempo_bpm_min,
            tempo_bpm_max: ctx.tempo_bpm_max,
            lufs: ctx.lufs,
            tonal_balance: ctx.tonal_balance,
            stereo_width: ctx.stereo_width,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fragment::{Fragment, FragmentKind, ProjectId};
    use crate::reference::ReferenceContext;

    fn human(project: ProjectId, note: &str) -> Fragment {
        Fragment::new_capture(
            project,
            FragmentKind::Melody,
            "hash".into(),
            None,
            None,
            note.into(),
        )
    }

    /// A fragment with a non-human provenance, to prove the human-only filter.
    fn ai(project: ProjectId) -> Fragment {
        let mut f = human(project, "generated");
        f.provenance = Provenance::AiGenerated;
        f
    }

    #[test]
    fn gather_includes_only_human_recorded_fragments() {
        let p = ProjectId::new();
        let h1 = human(p, "chorus hum");
        let h2 = human(p, "verse idea");
        let g = ai(p);

        let cond = gather_melodic_conditioning(&[h1.clone(), g, h2.clone()]);
        // The ai_generated fragment is excluded; only the two human ids survive, in order.
        assert_eq!(cond.source_fragment_ids, vec![h1.id, h2.id]);
        assert!(!cond.is_empty());
    }

    #[test]
    fn empty_when_no_human_material() {
        let p = ProjectId::new();
        let cond = gather_melodic_conditioning(&[ai(p)]);
        assert!(cond.is_empty());
    }

    #[test]
    fn reference_conditioning_drops_vibe_prose_and_carries_no_melody() {
        let ctx = ReferenceContext {
            reference_track_id: ReferenceTrackId::new(),
            clap_style_embedding: vec![0.5; 8],
            genre: Some("deep-house".into()),
            tempo_bpm_min: 120.0,
            tempo_bpm_max: 124.0,
            lufs: -8.0,
            tonal_balance: TonalBalance {
                low: 0.3,
                low_mid: 0.25,
                mid: 0.2,
                high_mid: 0.15,
                high: 0.1,
            },
            stereo_width: 0.6,
            vibe_description: "hypnotic, deep, after-hours".into(),
            analyzer_version: "v".into(),
        };
        let cond = ReferenceConditioning::from_context(&ctx);
        assert_eq!(cond.genre.as_deref(), Some("deep-house"));
        assert_eq!(cond.clap_style_embedding.len(), 8);
        // Nothing on `ReferenceConditioning` can carry a melody — there is no such field to assert
        // against; this test documents the intent (the absence is the guarantee). The vibe prose is
        // intentionally not part of the machine conditioning bundle.
    }
}
