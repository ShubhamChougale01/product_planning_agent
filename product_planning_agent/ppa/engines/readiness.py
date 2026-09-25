"""Readiness gate — the stopping criterion (DESIGN.md §1.2, §6.2, §6.5,
S4.1, S4.3).

Arithmetic, computed in Python, never a model judgment: `check_readiness`
evaluates seven fixed conditions against materialized ledger state and
returns exactly which ones are unmet. Two of the seven ordinarily depend on
work this build order has not reached yet — conflict adjudication (T30,
built on T11's candidate detection) and an explicit REVIEW-mode approval
record (T30) — so both are accepted as parameters here rather than computed,
the same pattern `ppa/ledger/digest.py` (T09) uses for coverage state.
Neither parameter defaults to a permissive stand-in that could silently wave
a session through: `unresolved_conflicts` defaults to empty (nothing to
adjudicate yet in a codebase where nothing produces conflicts yet) but
`review_approved` defaults to `False` (the fail-safe direction — REVIEW
approval must always be supplied explicitly, never assumed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from ppa.config.areas import AreaStatus
from ppa.config.profiles import UserProfile, critical_areas
from ppa.engines.coverage import compute_coverage
from ppa.ledger.events import EventType
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType
from ppa.ledger.store import append_event

Condition = Literal[
    "critical_area_coverage",
    "blocking_unknown",
    "unconfirmed_high_assumption",
    "blocking_decision_not_decided",
    "requirement_missing_for_critical_area",
    "unresolved_conflict",
    "review_not_approved",
]


class Blocker(BaseModel):
    """Names the entity (or area, for an area-level condition) and states
    what would clear it — DESIGN.md's own requirement for every gate
    failure, not just a bare boolean."""

    model_config = ConfigDict(extra="forbid")

    condition: Condition
    entity_id: str | None
    area: str | None
    description: str


def _conflict_id(conflict: Any) -> str | None:
    if isinstance(conflict, dict):
        return conflict.get("id")
    return getattr(conflict, "id", None)


def check_readiness(
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    *,
    confirmed_areas: set[str] | None = None,
    unresolved_conflicts: Sequence[Any] | None = None,
    review_approved: bool = False,
) -> tuple[bool, list[Blocker]]:
    """`READY` iff all seven conditions in `tasks/t10_coverage_and_readiness_
    engines.md` hold. Every unmet condition produces its own `Blocker` —
    `check_readiness` never stops at the first failure, so a caller always
    sees the *whole* remaining gap in one call."""

    confirmed_areas = confirmed_areas or set()
    unresolved_conflicts = unresolved_conflicts or []
    critical = critical_areas(profile)
    coverage = compute_coverage(entities, profile, confirmed_areas=confirmed_areas)

    blockers: list[Blocker] = []

    # 1. Every area critical for this profile is SUFFICIENT or CONFIRMED.
    for area in sorted(critical):
        state = coverage[area]
        if state not in (AreaStatus.SUFFICIENT, AreaStatus.CONFIRMED):
            blockers.append(
                Blocker(
                    condition="critical_area_coverage",
                    entity_id=None,
                    area=area,
                    description=(
                        f"critical area {area!r} is {state.value} — needs a CONFIRMED "
                        "requirement covering it"
                    ),
                )
            )

    # 2. Zero Unknowns with blocking == True and status == OPEN, except
    #    owner_type == external (§6.2 — those convert to a provisional
    #    assumption and do not block; the exception is evaluated live, on
    #    owner_type alone, so a session never stalls waiting for the actual
    #    conversion to happen).
    for entity_id, entity in entities.items():
        if entity_type_for(entity_id) is not EntityType.UNKNOWN:
            continue
        if entity.blocking and entity.status == "OPEN" and entity.owner_type != "external":
            blockers.append(
                Blocker(
                    condition="blocking_unknown",
                    entity_id=entity_id,
                    area=entity.area,
                    description=f"{entity_id} is blocking and still OPEN — resolve or convert it",
                )
            )

    # 3. Every HIGH-impact Assumption has status in {CONFIRMED, REJECTED} —
    #    a provisional assumption satisfies this only once the user
    #    acknowledges it in REVIEW, i.e. it still needs a real CONFIRMED or
    #    REJECTED status, "provisional" grants no exemption.
    for entity_id, entity in entities.items():
        if entity_type_for(entity_id) is not EntityType.ASSUMPTION:
            continue
        if entity.impact == "HIGH" and entity.status not in ("CONFIRMED", "REJECTED"):
            blockers.append(
                Blocker(
                    condition="unconfirmed_high_assumption",
                    entity_id=entity_id,
                    area=None,
                    description=(
                        f"{entity_id} is HIGH impact and still {entity.status} — "
                        "confirm or reject it"
                    ),
                )
            )

    # 4. Every blocking Decision has status == DECIDED (DECIDE_LATER is
    #    permitted only when blocking == False).
    for entity_id, entity in entities.items():
        if entity_type_for(entity_id) is not EntityType.DECISION:
            continue
        if entity.blocking and entity.status != "DECIDED":
            blockers.append(
                Blocker(
                    condition="blocking_decision_not_decided",
                    entity_id=entity_id,
                    area=None,
                    description=(
                        f"{entity_id} is blocking and still {entity.status} — DECIDE_LATER "
                        "is not permitted for a blocking decision"
                    ),
                )
            )

    # 5. At least one Requirement covers each critical area — checked
    #    directly against entities, independent of `coverage`'s own SUFFICIENT/
    #    CONFIRMED labels, so a coverage-engine defect can't silently mask a
    #    critical area with zero requirements at all.
    covered_by_any_requirement = {area: False for area in critical}
    for entity_id, entity in entities.items():
        if entity_type_for(entity_id) is not EntityType.REQUIREMENT:
            continue
        for area in entity.covers_areas:
            if area in covered_by_any_requirement:
                covered_by_any_requirement[area] = True
    for area in sorted(critical):
        if not covered_by_any_requirement[area]:
            blockers.append(
                Blocker(
                    condition="requirement_missing_for_critical_area",
                    entity_id=None,
                    area=area,
                    description=f"no Requirement covers critical area {area!r} yet",
                )
            )

    # 6. Zero unresolved conflicts.
    for conflict in unresolved_conflicts:
        blockers.append(
            Blocker(
                condition="unresolved_conflict",
                entity_id=_conflict_id(conflict),
                area=None,
                description="an unresolved conflict must be adjudicated before READY",
            )
        )

    # 7. The user has explicitly approved the REVIEW summary.
    if not review_approved:
        blockers.append(
            Blocker(
                condition="review_not_approved",
                entity_id=None,
                area=None,
                description="the user has not yet approved the REVIEW summary",
            )
        )

    return (len(blockers) == 0, blockers)


def force_ready(
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    reason: str,
    events_path: Any,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    confirmed_areas: set[str] | None = None,
    unresolved_conflicts: Sequence[Any] | None = None,
    review_approved: bool = False,
    now: datetime | None = None,
) -> str:
    """User override. Runs the same gate `check_readiness` would, then
    emits `user.forced_ready` naming every blocker that was skipped —
    `force_ready` never silently succeeds without recording what it bypassed."""

    _ready, blockers = check_readiness(
        entities,
        profile,
        confirmed_areas=confirmed_areas,
        unresolved_conflicts=unresolved_conflicts,
        review_approved=review_approved,
    )

    return append_event(
        dict(
            ts=now or datetime.now(timezone.utc),
            type=EventType.USER_FORCED_READY,
            entity_id=None,
            actor_id=actor_id,
            actor_role="user",
            agent_name=None,
            workflow_state=workflow_state,
            txn_id=None,
            source="readiness_gate",
            reason=reason,
            before=None,
            after={"skipped_blockers": [b.model_dump(mode="json") for b in blockers]},
            session_id=session_id,
        ),
        events_path,
    )
