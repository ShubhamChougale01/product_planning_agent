"""Mandatory validators, called directly by the Orchestrator — never
requested from the model (T21, DESIGN.md §2.2, §2.10, §2.11).

The model cannot skip a precondition because the model is never asked to
perform it. `ppa/orchestrator/loop.py` calls `validate_discovery_state`
itself, in plain Python, before it will let workflow state move out of
`DISCOVERY`/`DISCOVERY_VALIDATED` — no `tool_choice` trick, no dependency on
SDK internals.

`validate_discovery_state` is built on `ppa.engines.readiness.check_readiness`
rather than duplicating its five Discovery-relevant conditions — but it only
gates on a *subset* of check_readiness's seven. Two of the seven
(`unresolved_conflict`, `review_not_approved`) are REVIEW-mode concerns
(DESIGN.md §2.5's own diagram: REVIEW is a Discovery-*internal* mode, and
`review_not_approved`/`unresolved_conflict` are decision #19's
not-yet-buildable-before-T30 inputs) — irrelevant to whether Discovery's own
work is done, so a blocker on either must never block leaving DISCOVERY. See
decision #28 in `blockers.md`.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.config.profiles import UserProfile
from ppa.engines.readiness import Blocker, check_readiness
from ppa.ledger.models import BaseEntity

DISCOVERY_EXIT_CONDITIONS = frozenset(
    {
        "critical_area_coverage",
        "blocking_unknown",
        "unconfirmed_high_assumption",
        "blocking_decision_not_decided",
        "requirement_missing_for_critical_area",
    }
)
"""`check_readiness`'s seven `Condition` values, minus the two that belong to
REVIEW mode (`unresolved_conflict`, `review_not_approved`) rather than to
whether Discovery itself is done."""


class PreconditionResult(BaseModel):
    """`ok=True` iff every Discovery-exit condition holds. `blockers` is
    always the full remaining set (never truncated at the first failure),
    matching `check_readiness`'s own "never stop at the first failure" rule
    — a caller routing back to Discovery should see everything still open,
    not just one item at a time."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    blockers: list[Blocker]


def validate_discovery_state(
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    *,
    confirmed_areas: set[str] | None = None,
) -> PreconditionResult:
    """Plain Python, no model involved. Called directly by
    `ppa/orchestrator/loop.py` before it will let workflow state advance past
    `DISCOVERY_VALIDATED`, and again before it will let `DISCOVERY ->
    DISCOVERY_VALIDATED` stand."""

    # Ask `check_readiness` the full, honest truth (its own real defaults —
    # `review_approved=False` fails closed, exactly as decision #19 intends)
    # and then filter to only the conditions this narrower question cares
    # about, rather than passing `review_approved=True` to fake an answer
    # `check_readiness` was never actually given.
    _ready, all_blockers = check_readiness(entities, profile, confirmed_areas=confirmed_areas)
    relevant = [b for b in all_blockers if b.condition in DISCOVERY_EXIT_CONDITIONS]
    return PreconditionResult(ok=not relevant, blockers=relevant)
