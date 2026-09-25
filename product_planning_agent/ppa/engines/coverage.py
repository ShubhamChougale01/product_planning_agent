"""Coverage engine — the single place an area's state may be derived
(DESIGN.md §1.2, §6.1, S4.1).

Coverage is **derived**, never declared: the model moves the meter only by
recording real entities (a Requirement that covers an area, an Assumption
that affects one), never by asserting progress directly. That is what
`__all__` below enforces by omission — there is deliberately no setter, and
no other module in this codebase is allowed to invent a second way to read
an area's state (`ppa/ledger/digest.py`, T09, is the example this was
written against: it renders whatever `coverage` mapping it is handed, and
never computes one itself).
"""

from __future__ import annotations

from typing import Mapping

from ppa.config.areas import AREA_KEYS, AreaStatus
from ppa.config.profiles import UserProfile, critical_areas
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType

__all__ = ["compute_coverage", "progress"]


def _covering_requirements(entities: Mapping[str, BaseEntity], area: str) -> list[BaseEntity]:
    return [
        entity
        for entity_id, entity in entities.items()
        if entity_type_for(entity_id) is EntityType.REQUIREMENT and area in entity.covers_areas
    ]


def _covering_assumptions(entities: Mapping[str, BaseEntity], area: str) -> list[BaseEntity]:
    return [
        entity
        for entity_id, entity in entities.items()
        if entity_type_for(entity_id) is EntityType.ASSUMPTION and area in entity.affects_areas
    ]


def compute_coverage(
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    *,
    confirmed_areas: set[str] | None = None,
) -> dict[str, AreaStatus]:
    """One `AreaStatus` per area in `ppa/config/areas.py::AREA_KEYS`, derived
    from `entities` alone:

    - `UNTOUCHED` — no Requirement or Assumption references the area at all.
    - `PARTIAL` — referenced only by non-CONFIRMED Requirements, or by
      Assumptions alone (with or without a PROPOSED Requirement too).
    - `SUFFICIENT` — at least one CONFIRMED Requirement covers it.
    - `CONFIRMED` — SUFFICIENT, and the user has explicitly confirmed the
      area in REVIEW.

    `profile` is accepted for signature symmetry with `progress` and because
    every other engine entry point takes one — this function's own output
    does not vary by profile (only which areas are *critical* does, which is
    `progress`'s concern, not this one's).

    `confirmed_areas` is the set of areas the user has explicitly confirmed
    in REVIEW. Nothing in this codebase yet persists that set on disk (T30,
    Review mode, owns building that flow) — this engine only renders
    whatever set it is handed, exactly like T09's digest renders whatever
    coverage mapping *it* is handed. Omit it (or pass `set()`) and no area
    can ever reach `CONFIRMED`, only `SUFFICIENT`.
    """

    del profile  # signature symmetry only — see docstring.
    confirmed_areas = confirmed_areas or set()

    coverage: dict[str, AreaStatus] = {}
    for area in AREA_KEYS:
        requirements = _covering_requirements(entities, area)
        confirmed_requirements = [r for r in requirements if r.status == "CONFIRMED"]

        if confirmed_requirements:
            state = AreaStatus.CONFIRMED if area in confirmed_areas else AreaStatus.SUFFICIENT
        elif requirements or _covering_assumptions(entities, area):
            state = AreaStatus.PARTIAL
        else:
            state = AreaStatus.UNTOUCHED

        coverage[area] = state

    return coverage


def progress(
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    *,
    confirmed_areas: set[str] | None = None,
) -> tuple[int, int]:
    """`(n_critical_sufficient, n_critical)` — reported against the critical
    set for `profile`, not all twelve areas, so the number does not drift
    just because a non-critical area happens to fill in."""

    critical = critical_areas(profile)
    coverage = compute_coverage(entities, profile, confirmed_areas=confirmed_areas)
    n_sufficient = sum(
        1 for area in critical if coverage[area] in (AreaStatus.SUFFICIENT, AreaStatus.CONFIRMED)
    )
    return n_sufficient, len(critical)
