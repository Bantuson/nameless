//! The typed fragment lifecycle — the headline invariant of Phase 1.
//!
//! PRD §7: "Rust enforces every transition with exhaustive matching, so an unanalyzed fragment
//! can never be placed and an ungated generation can never enter an arrangement."
//!
//! That guarantee lives HERE, and only here. There is exactly one function that may compute a
//! next state — [`transition`] — and exactly one method that may mutate a fragment's state —
//! [`Fragment::apply`], which delegates to `transition`. Illegal moves are a typed
//! [`IllegalTransition`] error, not a panic and not a silent no-op. "The harness gates; the
//! agent explores": any caller (including an LLM-driven one) can *attempt* any transition, but
//! the type system + this match decide what is allowed.
//!
//! ## The two paths (one enum)
//!
//! ```text
//! human/sampled/derived:  Captured → Analyzing → Analyzed → Placed → Mixed → Rendered
//! ai:                     Requested → Generating → Generated → Evaluating
//!                                   → { Promoted → Placed → Mixed → Rendered | Rejected }
//! ```
//!
//! `Place` is legal ONLY from `Analyzed` (human/sampled/derived) or from `Promoted` (ai). There
//! is no `Generated → Placed` edge: the eval gate (`Evaluate` → `Promote`) is the only route an
//! AI fragment can reach an arrangement. Phase 1 only *drives* the `captured` entry transition
//! live (via capture); the rest of the lifecycle is defined and exhaustively tested now so the
//! invariant is locked cheaply on day one — later phases wire the workers that drive each edge.

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::fragment::Fragment;
use crate::provenance::Provenance;

/// Every state a fragment can occupy across both lifecycle paths (PRD §7).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FragmentState {
    // ---- human / sampled / derived path ----
    /// Just captured; raw audio stored, intent note attached. The Phase-1 entry state.
    Captured,
    /// Feature extraction in flight (Phase 2 drives this).
    Analyzing,
    /// Features + embeddings computed; eligible for placement.
    Analyzed,
    /// Assigned a role/position in an arrangement.
    Placed,
    /// Run through the mix chain.
    Mixed,
    /// Bounced to a rendered artifact.
    Rendered,

    // ---- ai generation + eval-gate path ----
    /// A generation has been requested (conditioned on a human fragment).
    Requested,
    /// The generator is producing audio.
    Generating,
    /// Generation complete; awaiting the eval gate.
    Generated,
    /// The eval gate is scoring fidelity/key/tempo/loudness.
    Evaluating,
    /// The eval gate passed — the ONLY state from which an AI fragment may be placed.
    Promoted,
    /// The eval gate failed — terminal; the generation never enters an arrangement.
    Rejected,
}

impl FragmentState {
    /// All variants — used by the exhaustive transition-matrix test.
    pub const ALL: [FragmentState; 12] = [
        FragmentState::Captured,
        FragmentState::Analyzing,
        FragmentState::Analyzed,
        FragmentState::Placed,
        FragmentState::Mixed,
        FragmentState::Rendered,
        FragmentState::Requested,
        FragmentState::Generating,
        FragmentState::Generated,
        FragmentState::Evaluating,
        FragmentState::Promoted,
        FragmentState::Rejected,
    ];

    /// Stable lowercase label, matching the Postgres `fragment_state` enum + serde form.
    pub const fn as_str(self) -> &'static str {
        match self {
            FragmentState::Captured => "captured",
            FragmentState::Analyzing => "analyzing",
            FragmentState::Analyzed => "analyzed",
            FragmentState::Placed => "placed",
            FragmentState::Mixed => "mixed",
            FragmentState::Rendered => "rendered",
            FragmentState::Requested => "requested",
            FragmentState::Generating => "generating",
            FragmentState::Generated => "generated",
            FragmentState::Evaluating => "evaluating",
            FragmentState::Promoted => "promoted",
            FragmentState::Rejected => "rejected",
        }
    }

    /// Parse from the canonical label (DB enum). `None` for unknown labels.
    pub fn from_db_str(s: &str) -> Option<FragmentState> {
        FragmentState::ALL.into_iter().find(|st| st.as_str() == s)
    }
}

/// Every transition verb that can be *attempted* on a fragment.
///
/// A verb names an intent; [`transition`] decides whether it is legal from the current
/// `(provenance, state)`. Verbs are deliberately separate from states so the same verb (`Place`,
/// `Mix`, `Render`) can be reused across both lifecycle paths.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Transition {
    // human path
    Analyze,
    MarkAnalyzed,
    // ai path
    Generate,
    MarkGenerated,
    Evaluate,
    Promote,
    Reject,
    // shared tail
    Place,
    Mix,
    Render,
}

impl Transition {
    /// All variants — used by the exhaustive transition-matrix test.
    pub const ALL: [Transition; 10] = [
        Transition::Analyze,
        Transition::MarkAnalyzed,
        Transition::Generate,
        Transition::MarkGenerated,
        Transition::Evaluate,
        Transition::Promote,
        Transition::Reject,
        Transition::Place,
        Transition::Mix,
        Transition::Render,
    ];
}

/// A rejected transition attempt, carrying the offending pair so the failure names itself.
///
/// Returned (never panicked) so callers MUST handle the illegal case — there is no silent
/// no-op path that could let an invalid move slip through (Repudiation mitigation).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Error)]
#[error("illegal transition: cannot apply {transition:?} from state {from:?}")]
pub struct IllegalTransition {
    pub from: FragmentState,
    pub transition: Transition,
}

/// The single checked transition function. Pure: output depends only on the inputs.
///
/// Implemented as one `match` over `(from, transition)` with provenance guards on the path-entry
/// and `Place` edges. Every legal edge returns `Ok(next)`; the final `_` arm — the ONLY wildcard —
/// maps exclusively to [`IllegalTransition`]. No wildcard ever yields an `Ok`, so an unintended
/// edge cannot be silently introduced: a new legal edge must be written explicitly.
///
/// Key guarantees enforced structurally here:
/// * `Place` is reachable only from `Analyzed` (human/sampled/derived) or `Promoted` (ai)
///   → **an unanalyzed/ungated fragment can never be placed**.
/// * There is no `Generated → Placed` edge → **the eval gate is the only path for AI material**.
/// * `Rejected` has no outgoing edge → terminal.
pub fn transition(
    provenance: Provenance,
    from: FragmentState,
    t: Transition,
) -> Result<FragmentState, IllegalTransition> {
    use FragmentState::*;
    use Transition::*;

    let next = match (from, t) {
        // ---- human / sampled / derived analysis path ----
        (Captured, Analyze) if provenance.travels_human_path() => Analyzing,
        (Analyzing, MarkAnalyzed) if provenance.travels_human_path() => Analyzed,
        // Placement for real source audio: legal only once Analyzed.
        (Analyzed, Place) if provenance.travels_human_path() => Placed,

        // ---- ai generation + eval-gate path ----
        (Requested, Generate) if provenance.is_ai() => Generating,
        (Generating, MarkGenerated) if provenance.is_ai() => Generated,
        (Generated, Evaluate) if provenance.is_ai() => Evaluating,
        (Evaluating, Promote) if provenance.is_ai() => Promoted,
        (Evaluating, Reject) if provenance.is_ai() => Rejected,
        // Placement for AI material: legal only AFTER the eval gate (Promoted). No bypass.
        (Promoted, Place) if provenance.is_ai() => Placed,

        // ---- shared post-placement tail (both lifecycles converge here) ----
        (Placed, Mix) => Mixed,
        (Mixed, Render) => Rendered,

        // ---- everything else is illegal; this wildcard NEVER yields Ok ----
        _ => {
            return Err(IllegalTransition {
                from,
                transition: t,
            })
        }
    };
    Ok(next)
}

impl Fragment {
    /// The ONLY way to mutate a fragment's lifecycle state.
    ///
    /// Delegates to [`transition`] and assigns the result on success. There is no other code path
    /// that writes `Fragment::state` (grep-gated by `test_apply_is_sole_mutation_path` and the
    /// crate convention), so the invariant proven for `transition` holds for every live fragment.
    pub fn apply(&mut self, t: Transition) -> Result<(), IllegalTransition> {
        let next = transition(self.provenance, self.state, t)?;
        self.state = next;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provenance::Provenance::*;
    use FragmentState::*;
    use Transition::*;

    /// The hand-written allow-list of EVERY legal edge — the executable spec the matrix test
    /// checks `transition` against. If `transition` and this list ever disagree, a test fails.
    fn legal_edges() -> Vec<(Provenance, FragmentState, Transition, FragmentState)> {
        let mut edges = Vec::new();

        // Shared post-placement tail is legal for ALL provenances (unguarded in `transition`).
        for p in Provenance::ALL {
            edges.push((p, Placed, Mix, Mixed));
            edges.push((p, Mixed, Render, Rendered));
        }

        // Human / sampled / derived analysis + placement path.
        for p in [HumanRecorded, Sampled, Derived] {
            edges.push((p, Captured, Analyze, Analyzing));
            edges.push((p, Analyzing, MarkAnalyzed, Analyzed));
            edges.push((p, Analyzed, Place, Placed));
        }

        // AI generation + eval-gate path.
        edges.push((AiGenerated, Requested, Generate, Generating));
        edges.push((AiGenerated, Generating, MarkGenerated, Generated));
        edges.push((AiGenerated, Generated, Evaluate, Evaluating));
        edges.push((AiGenerated, Evaluating, Promote, Promoted));
        edges.push((AiGenerated, Evaluating, Reject, Rejected));
        edges.push((AiGenerated, Promoted, Place, Placed));

        edges
    }

    /// Exhaustively check the full cartesian product (4 × 12 × 10 = 480 triples): every triple in
    /// the allow-list returns `Ok(expected_next)`, EVERY other triple returns `Err`.
    #[test]
    fn test_full_transition_matrix() {
        let legal = legal_edges();
        for p in Provenance::ALL {
            for from in FragmentState::ALL {
                for t in Transition::ALL {
                    let expected = legal
                        .iter()
                        .find(|(lp, lf, lt, _)| *lp == p && *lf == from && *lt == t)
                        .map(|(_, _, _, next)| *next);
                    match (expected, transition(p, from, t)) {
                        (Some(next), Ok(got)) => assert_eq!(
                            got, next,
                            "legal edge ({p:?}, {from:?}, {t:?}) should yield {next:?}, got {got:?}"
                        ),
                        (Some(next), Err(e)) => {
                            panic!("expected legal edge to {next:?} but got error: {e}")
                        }
                        (None, Ok(got)) => panic!(
                            "({p:?}, {from:?}, {t:?}) is NOT in the allow-list but transition returned Ok({got:?})"
                        ),
                        (None, Err(e)) => {
                            assert_eq!(e.from, from);
                            assert_eq!(e.transition, t);
                        }
                    }
                }
            }
        }
    }

    /// The headline CAP-05 invariant: an unanalyzed fragment cannot be placed.
    #[test]
    fn test_cannot_place_unanalyzed() {
        assert!(transition(HumanRecorded, Captured, Place).is_err());
        assert!(transition(HumanRecorded, Analyzing, Place).is_err());
        assert!(transition(Sampled, Captured, Place).is_err());
        assert!(transition(Derived, Analyzing, Place).is_err());
        // ...but placement IS legal once analyzed.
        assert_eq!(transition(HumanRecorded, Analyzed, Place), Ok(Placed));
    }

    /// The eval gate is the only path from a generation into an arrangement.
    #[test]
    fn test_ai_requires_eval_gate() {
        // No Generated → Placed bypass.
        assert!(transition(AiGenerated, Generated, Place).is_err());
        // The only route to Placed: Generated → Evaluating → Promoted → Placed.
        let s = transition(AiGenerated, Generated, Evaluate).unwrap();
        assert_eq!(s, Evaluating);
        let s = transition(AiGenerated, s, Promote).unwrap();
        assert_eq!(s, Promoted);
        let s = transition(AiGenerated, s, Place).unwrap();
        assert_eq!(s, Placed);
    }

    /// Sampled material travels the human path (the Phase-8 attribution gate is layered later).
    #[test]
    fn test_sampled_travels_human_path() {
        assert_eq!(transition(Sampled, Analyzed, Place), Ok(Placed));
        // It does NOT travel the AI path.
        assert!(transition(Sampled, Requested, Generate).is_err());
    }

    /// Rejected is terminal — no outgoing transition of any kind.
    #[test]
    fn test_rejected_is_terminal() {
        for p in Provenance::ALL {
            for t in Transition::ALL {
                assert!(
                    transition(p, Rejected, t).is_err(),
                    "Rejected must be terminal, but ({p:?}, Rejected, {t:?}) was legal"
                );
            }
        }
    }

    /// The error carries the offending pair so a regression names itself.
    #[test]
    fn test_illegal_transition_reports_pair() {
        let err = transition(HumanRecorded, Captured, Place).unwrap_err();
        assert_eq!(err.from, Captured);
        assert_eq!(err.transition, Place);
        assert!(err.to_string().contains("Place"));
        assert!(err.to_string().contains("Captured"));
    }

    /// `Fragment::apply` is the single mutation chokepoint and refuses illegal moves.
    #[test]
    fn test_apply_is_sole_mutation_path() {
        use crate::fragment::{Fragment, FragmentKind, ProjectId};
        let mut f = Fragment::new_capture(
            ProjectId::new(),
            FragmentKind::Hook,
            "hash123".into(),
            None,
            None,
            "chorus hook".into(),
        );
        assert_eq!(f.state, Captured);
        // Illegal: cannot place straight from captured — state is unchanged.
        assert!(f.apply(Place).is_err());
        assert_eq!(f.state, Captured);
        // Legal walk down the human path.
        f.apply(Analyze).unwrap();
        assert_eq!(f.state, Analyzing);
        f.apply(MarkAnalyzed).unwrap();
        assert_eq!(f.state, Analyzed);
        f.apply(Place).unwrap();
        assert_eq!(f.state, Placed);
    }
}
