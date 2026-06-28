"""The restricted-feature invariant — a runtime tripwire backing the structural non-cloning guarantee.

The PRIMARY guarantee is structural: :class:`~nameless_workers.domain.reference.NonMelodicFeatures`
(and every type around it) is sealed with ``extra="forbid"`` and declares no melodic field, so a
melody literally cannot be constructed into a reference's context (REF-03, PITFALLS.md Pitfall 6).

This module is the BELT to that suspenders: a pure predicate/assertion that walks a pydantic model's
*declared fields* (recursively) and fails if any melodic field name appears. It's cheap insurance the
analyzer can call on its own output, and a clear executable statement of intent the tests assert on.
The check is over field NAMES on the type, not values — it proves the shape can't carry a melody, not
merely that this instance happens not to.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.reference import FORBIDDEN_MELODIC_FIELDS


class MelodicLeakError(AssertionError):
    """Raised when a reference-context model exposes a melodic/structural field (a clone-leak risk)."""


def _melodic_fields_in(model_type: type[BaseModel], _seen: set[type] | None = None) -> set[str]:
    """Collect any forbidden melodic field names declared on ``model_type`` or its nested models."""
    seen = _seen if _seen is not None else set()
    if model_type in seen:
        return set()
    seen.add(model_type)

    found: set[str] = set()
    for name, field in model_type.model_fields.items():
        if name in FORBIDDEN_MELODIC_FIELDS:
            found.add(name)
        # Recurse into nested pydantic models (e.g. NonMelodicFeatures.tonal_balance).
        annotation = field.annotation
        for candidate in _iter_model_types(annotation):
            found |= _melodic_fields_in(candidate, seen)
    return found


def _iter_model_types(annotation: object):
    """Yield any ``BaseModel`` subclasses referenced by a type annotation (handles Optional/Union)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    # typing constructs (Optional[X], Union[...], list[X], etc.) expose their args via __args__.
    for arg in getattr(annotation, "__args__", ()) or ():
        yield from _iter_model_types(arg)


def is_non_melodic(model: BaseModel) -> bool:
    """True iff ``model``'s type (and its nested models) declare no melodic/structural field."""
    return not _melodic_fields_in(type(model))


def assert_non_melodic(model: BaseModel) -> None:
    """Raise :class:`MelodicLeakError` if ``model`` (or a nested model) declares a melodic field.

    Call this on a :class:`ReferenceContext` / :class:`NonMelodicFeatures` before persisting it. With
    the current sealed types it never fires — that's the point: it stays green precisely because the
    structural guarantee holds, and turns red the instant someone adds a melodic column.
    """
    leaked = _melodic_fields_in(type(model))
    if leaked:
        raise MelodicLeakError(
            f"{type(model).__name__} exposes melodic/structural field(s) {sorted(leaked)} — "
            "a reference's context must never carry melody/chroma/structure (REF-03)."
        )
