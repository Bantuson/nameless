"""Domain layer — pure types and rules, no I/O.

Mirrors the canonical Rust domain in ``crates/nameless-core`` (the source of truth) so the Python
worker speaks exactly the same provenance labels, lifecycle states, transition rules, and job-envelope
JSON. Where Rust and Python both encode a rule (the state machine), Rust remains canonical and this is
a documented, exhaustively-tested mirror — see :mod:`nameless_workers.domain.state`.
"""
