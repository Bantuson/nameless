---
status: issues
phase: 01-typed-capture-spine
depth: standard
files_reviewed: 23
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
---

# Phase 1: Code Review Report — Typed Capture Spine

**Reviewed:** 2026-06-28T00:00:00Z
**Depth:** standard (per-file, Rust-specific; read-only, never compiled here)
**Files Reviewed:** 23
**Status:** issues_found

## Summary

The crown-jewel state machine (`state_machine.rs`) is genuinely well-built and I could
not find a logic hole in it by reading: `transition()` is a single exhaustive `match`
over `(from, t)` with a wildcard that *only ever* returns `Err`, provenance guards correctly
fence the path-entry and `Place` edges, there is no `Generated → Placed` edge, `Rejected`
is terminal, and the 480-triple matrix test plus the no-bypass sampled-placement test
encode the spec executably. `Fragment::apply` and `place()` are the only two mutators that
*call through* the machine, and the sampled-placement refusal in `apply` is correctly closed.

No active, provable correctness bug exists in any Phase-1 *shipped* code path (capture →
hash → store → probe → persist → enqueue). The findings below are (1) an encapsulation gap
that makes the headline "structurally impossible" claim actually convention-enforced, and
(2) contract/substitutability divergences in the env-gated `postgres` adapters that the
compiler here never checked. All env-gated items are tagged.

There are **zero** debug artifacts, no `unwrap`/`expect`/`panic!` on reachable non-test
paths, no string-built SQL (parameterized + compile-time-checked), no `eval`/unsafe, and the
object-store key validation correctly blocks path traversal. Compact-output contract holds
structurally in `output.rs` (no path can emit bytes/arrays).

## Warnings

### WR-01: Headline invariant is convention-enforced, not structural — `Fragment.state` and `Fragment.provenance` are public mutable fields

**File:** `crates/nameless-core/src/fragment.rs:147,155` (claim made in `crates/nameless-core/src/state_machine.rs:6-11`)
**Issue:** `state_machine.rs` states "exactly one method that may mutate a fragment's state —
`Fragment::apply`" and the phase goal is that it be **structurally impossible** to place an
unanalyzed/ungated fragment. But `Fragment.state`, `Fragment.provenance` (and every other
field) are declared `pub`. Any code anywhere in the workspace — or any future phase — can
write `frag.state = FragmentState::Placed;` or `frag.provenance = Provenance::HumanRecorded;`
directly, completely bypassing `transition`/`apply`/`place` and the Phase-8 attribution gate.
The tests themselves rely on this (`f.provenance = Provenance::Sampled;` at
`state_machine.rs:485`), which proves the door is open. The guarantee is therefore enforced by
documentation/discipline, not the type system; the doc comment "Mutated ONLY via
`Fragment::apply`" is literally false as written.
**Why it matters:** This is the phase's load-bearing security/integrity invariant ("an
ungated generation can never enter an arrangement"). A single stray assignment in a later
phase (or an LLM-driven code path) silently defeats the eval gate and the sampled-attribution
gate with no compiler error and no test failure. The cost of the gap is unbounded precisely
because nothing flags a violation.
**Fix:** Make the lifecycle-significant fields private and expose read-only getters; force all
state writes through `apply`/`place`. serde can still (de)serialize private fields, so the
repo adapters keep working; reconstruction from a DB row can go through an explicit
`Fragment::from_persisted(...)` constructor rather than field assignment. At minimum, make
`state` and `provenance` private (`pub(crate)` is weaker but still closes the cross-crate
door) and update the tests to use constructors.

### WR-02: `SqlxmqJobQueue` silently no-ops `consume`/`mark_done`/`mark_retry` and reports a fake `capacity` — diverges from the `JobQueue` contract and from the in-memory fake

**File:** `crates/nameless-adapters/src/queue_sqlxmq.rs:107-130`
**Issue:** `consume()` always returns `Ok(None)`, `mark_done` returns `Ok(())`, `mark_retry`
always returns `Ok(JobStatus::Failed)` (never increments attempts, never dead-letters), and
`capacity()` returns a hard-coded `256` while `enqueue` never applies backpressure (it cannot
return `JobError::Full`). The trait docs (`job.rs:148-166`) promise FIFO claim, ack,
attempt-counting + dead-lettering, and capacity-based backpressure — the in-memory fake
implements all of that and the retry-ceiling test (`queue_mem.rs:161`) depends on it.
**Why it matters:** The architecture's entire premise is "same trait, swap the heavy leaf, the
RAM tests prove the contract." That substitutability does **not** hold here: a behavior
verified against `InMemoryJobQueue` (retry/dead-letter/backpressure) would behave completely
differently against `SqlxmqJobQueue`. Phase 1 only enqueues so nothing is broken *today*, but
the divergence is a latent trap for Phase 2 the moment any code calls these methods believing
the contract holds.
**Fix:** Either (a) split the port so the Phase-1 adapter only implements an `Enqueue`
capability and the consume/ack/retry methods live on a separate trait the runner implements,
or (b) make the unimplemented methods return an explicit `Err(JobError::Backend{ msg:
"consume owned by the sqlxmq runner (Phase 2)" })` instead of a success-shaped lie, so a
mistaken Phase-1 caller fails loudly. *[env-gated: needs `--features postgres` compile to
confirm the no-op bodies type-check, but the contract divergence is provable by reading.]*

### WR-03: Every `JobEnvelope` variant is enqueued under the single `feature_extract_job` registration / `features` channel

**File:** `crates/nameless-adapters/src/queue_sqlxmq.rs:84-105` (handler at `:35-43`)
**Issue:** `enqueue()` spawns *all* envelope kinds — `FeatureExtract`, `Separate`,
`SeparateTrack`, `AnalyzeReference` — through `feature_extract_job.builder()`, i.e. under one
sqlxmq job name on `channel_name = "features"`. sqlxmq routes a stored message to the handler
matching its registered job name, so when a runner is wired (Phase 2+), a `SeparateTrack` or
`AnalyzeReference` message is delivered to the *feature-extraction* handler. Job-kind
discrimination then depends entirely on each consumer re-inspecting the JSON `job` tag, and
the Demucs/reference jobs are explicitly meant for the **Python** worker plane, not a Rust
sqlxmq handler.
**Why it matters:** This couples three distinct worker destinations onto one channel/handler
and pushes correct routing onto runtime payload inspection rather than the queue's own
dispatch — exactly the kind of seam that produces "job ran on the wrong worker" bugs later.
It also means per-kind concurrency/retry tuning is impossible (one policy for all).
**Fix:** Register one sqlxmq job/channel per envelope kind (or per worker plane), and select
the builder by matching on `env` in `enqueue`. If the Python workers consume `mq_msgs`
directly rather than via a Rust runner, document that explicitly and keep distinct channels so
the Python side can filter. *[env-gated + forward-looking: spans Phase 2/8; confirm against
the intended Python-vs-Rust consumer design.]*

## Info

### IN-01: `fragments.kind` is an unconstrained `text` column while `provenance`/`state` are DB enums

**File:** `migrations/0001_init.sql:50`
**Issue:** `kind text not null` has no `CHECK` constraint or enum type, unlike `provenance`
and `fragment_state`. Rust always writes a valid `as_str()` label and `from_db_str` validates
on read, so the round trip is safe *through Rust*, but the DB itself would accept `kind =
'banjo'`. A read of such a row fails with `RepoError::Serialization` (`repo_pg.rs:85-86`).
**Fix:** Add a `fragment_kind` enum type (mirroring the Rust enum) or a
`check (kind in ('melody','hook',...))` constraint, and bind it with the same
`$n::text::fragment_kind` cast the other two enums use, so the DB enforces the same closed set.

### IN-02: Adapter list ordering is inconsistent — Postgres orders by `created_at_ms`, file/mem order by insertion

**File:** `crates/nameless-adapters/src/repo_pg.rs:187` vs `crates/nameless-adapters/src/repo_file.rs:101` / `repo_mem.rs:57`
**Issue:** `PostgresFragmentRepo::list_fragments` does `order by created_at_ms desc`; the file
and in-memory repos return reverse-insertion order. The trait contract (`ports.rs:55-57`)
permits this ("callers that need ordering should sort"), so it is not a contract violation,
but the same call yields different orderings across adapters whenever `created_at_ms` is not
monotonic with insertion (e.g. back-dated/imported rows, or two captures in the same ms).
**Fix:** Pick one canonical ordering and apply it in all three adapters (sort the file/mem
results by `created_at_ms desc`, tie-breaking on `id`), or have Postgres add `, id desc` as a
deterministic tiebreaker — so tests written against the fake match production.

### IN-03: `S3ObjectStore::exists` infers "absent" by substring-matching `"404"` in the transport error string

**File:** `crates/nameless-adapters/src/object_store_s3.rs:150-156`
**Issue:** On a transport `Err`, the code returns `Ok(false)` iff `e.to_string().contains("404")`.
This is brittle: error-string formatting can change across `rust-s3` versions, and a 404
substring could appear coincidentally in an unrelated message, misclassifying a real failure
as "object absent" — which, via the write-if-absent path in `put` (`:108`), could turn a
transient error into an unnecessary re-upload (harmless under content addressing) or mask a
genuine connectivity problem.
**Fix:** Match on the typed status/error variant the client exposes rather than the formatted
string; only treat a structured 404/NotFound as absent and surface everything else as
`Backend`. *[env-gated: needs `--features postgres` + live R2 to exercise.]*

### IN-04: `do_capture`/`do_sample_add`/`do_reference_upload` read the whole file into memory before hashing

**File:** `crates/nameless-cli/src/cli.rs:513,549` (and `content_hash` in `object_store_fs.rs:24`)
**Issue:** `fs::read(&args.path)` loads the entire audio file into RAM, then `content_hash`
hashes the whole `&[u8]` and the bytes are held again for `store.put`. On the documented 4GB
box, a large captured file (or a hostile multi-GB upload) is fully resident; probe also clones
the bytes again (`probe.rs:30` `bytes.to_vec()`). Not a correctness bug and performance is out
of v1 scope, but it is a robustness/DoS-resilience note given the stated hardware envelope.
**Fix:** Stream the file through the hasher and into the store in fixed-size chunks (the
`ObjectStore::put` contract would need a streaming variant), and feed `probe` a bounded prefix
rather than a full second copy. Track as a follow-up; acceptable for the Phase-1 skeleton.

---

_Reviewed: 2026-06-28T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
