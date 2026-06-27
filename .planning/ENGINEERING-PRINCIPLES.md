# Engineering Principles (PERSISTENT — read before planning or writing any code)

**Status:** Authoritative, project-wide. Applies to EVERY phase, session, and milestone. Planners and executors MUST read this and honor it. It does not change WHAT is built — it governs HOW.

## 1. Build mode: course / learning project — code-complete, not run here

This project is built as a **complete, real, end-to-end codebase AND a learning artifact**. The user's dev machine (~4GB RAM, no Docker, no Rust/C++ toolchain) **cannot compile or run** the Rust control plane or the heavy ML, and that is **accepted and expected**.

- Deliver **real, complete, end-to-end code + logic for every phase** — Rust, Python/ML, TS/React — even though it will not execute on this machine. No stubbing-out of core logic to "make it runnable"; the logic must genuinely exist.
- **Do NOT gate progress on compiling / running / installing.** Never block a phase because `cargo`/`torch`/Postgres/Docker aren't available here.
- **"Verify" means review, not execution.** Verification = code review for correctness + completeness, requirement traceability, and **tests that EXIST** (written, not run here). Anything that genuinely needs real hardware/credentials is marked **env-gated** with the exact command the user runs later.
- **Go deep on the ML — it is a teaching subject.** The user explicitly wants to learn. ML-bearing phases ship a `LEARNING.md` (or inline doc-comments) explaining: what the technique is, why it's used here, how it works (the math/algorithm at a real level), trade-offs, and references. Course-quality, not hand-wavy.

## 2. Testability-first engineering law (non-negotiable, every phase)

Design for testability from day one. These are hard requirements, not aspirations:

- **Dependency injection / ports-and-adapters.** Every external or heavy dependency — database, object storage, ML model, network/HTTP, message queue, the system clock, randomness — sits behind a **trait/interface (a "port")** with a **real adapter** AND a **test double (fake/in-memory)**. Core code depends on the port, never on the concrete impl. Construct dependencies at the edge and inject them inward.
- **Pure functions for core logic.** The interesting logic (state-machine transitions, the citation-verification gate, claim cross-referencing, attribution rules, sonic-target math) is written as **pure functions**: deterministic, no I/O, no global state, output depends only on input. Side effects live at the boundary.
- **Separation of concerns.** Domain logic ≠ I/O ≠ orchestration ≠ presentation. Keep them in distinct modules/layers. A domain type must not import a DB driver or an HTTP client.
- **Loose coupling.** Depend on abstractions, not concretions. Modules communicate through narrow, explicit interfaces and typed messages. No hidden shared mutable state across module boundaries.

**Concretely, per language:**
- **Rust:** traits as ports; `impl Trait`/generics or `dyn Trait` for injection; pure functions + exhaustive `match` for domain logic; `#[cfg(test)]` in-memory fakes; `thiserror` typed errors; heavy/optional deps behind non-default cargo features.
- **Python:** `typing.Protocol`/ABCs as ports; constructor/function injection (no import-time singletons); pure functions for logic; `pydantic` for typed boundaries; fakes/`pytest` fixtures for doubles; ML models behind an interface so a deterministic fake stands in for tests.
- **TS/React:** props/context for injection; pure reducers/selectors and pure UI components; data-fetching behind a typed client interface with a mock; logic extracted from components into pure modules.

## 3. What every phase must produce

1. Real, complete code implementing the phase's plans (no placeholder bodies for core logic).
2. **Ports + adapters + test doubles** for all external/heavy dependencies.
3. **Tests that exist** (unit tests over pure logic + adapter contract tests via fakes) — written to be runnable in a real env, not run here.
4. For ML/DSP work: a `LEARNING.md` (or rich doc-comments) teaching the technique.
5. An honest note in the phase SUMMARY/VERIFICATION distinguishing **reviewed/complete** from **env-gated (not run here)**, with the exact commands to run later.

## 4. Persistence

This law persists across phases, sessions, and milestones. Its homes: this file (canonical), the `course-project-testability` memory (cross-session), `.planning/ENVIRONMENT.md` (verification policy), `.planning/PROJECT.md` (key decision/constraint), and `.claude/CLAUDE.md` (Conventions). If any drifts, this file wins — re-sync the others to it.
