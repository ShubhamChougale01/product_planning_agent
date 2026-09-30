"""Don't-know routing's own shape contract (T26, DESIGN.md §1.6, §3.3,
§3.4, S8.1-S8.3).

Like `ppa.agents.modes.intake` and `.clarify`, this module never trusts
what the model's own text claims it did — it checks a completed round's
*ledger state* (before/after) against the entity the routing table
(`ppa.engines.dont_know_classifier.ROUTE_FOR_KIND`) says that kind must
produce. `evaluate_dont_know_routing` is the assertion layer
`tests/eval/test_dont_know.py` checks against, for both a real live turn
and a direct, no-model call to the `manage_*` writers.

**Why every kind routes through an already-existing tool.** T26's own
"Files touched" list adds no new MCP tool — every route in the table is
reachable with `ask_user`, `manage_assumption`, `manage_decision` and
`manage_unknown`, all built by T16/T17. In particular:

- `unexplored` (and the anti-loop guard's forced escalation, S8.3) records
  an `Unknown` with `route="GUIDANCE"` — `Unknown.route`'s own literal
  already includes `"GUIDANCE"` (T02), so this needs no `request_guidance`
  hand-off tool to exist. That tool is real work for T28 (still a stub,
  `ppa/agents/subagents/guidance.py`); T26 only needs to *queue* the item
  correctly, the same way a `route="RESEARCH"` Unknown is queued today and
  picked up later rather than researched inline
  (`ppa/engines/open_items.py`'s own `"research_queued"` kind).
- `needs_external_input` records a *provisional* `Assumption`
  (`provisional=True`, `user_confirmation_required=True`) — the "provisional
  assumption flagged pending client confirmation" DESIGN.md §3.4 describes.
  Accumulating these into an actual client questionnaire is T27's job; T26
  only needs the entity to exist and be flagged correctly so T27 has
  something to collect.
- `depends_on_x` records an `Unknown` with `route="USER_DECISION"` — the
  dependency itself is not unknown-forever, it is something the user must
  still supply, which is exactly what `USER_DECISION` means in T02's own
  classification rule (§3.3: "YES, needed before build -> USER_DECISION").
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.engines.dont_know_classifier import DontKnowKind
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType


class DontKnowRoutingReport(BaseModel):
    """One `dont_know` answer's routing, checked against
    `tasks/t26_dont_know_routing.md`'s own per-kind Done-when boxes."""

    model_config = ConfigDict(extra="forbid")

    kind: DontKnowKind
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def _new_ids(before: Mapping[str, BaseEntity], after: Mapping[str, BaseEntity], entity_type: EntityType) -> list[str]:
    return [eid for eid in after if eid not in before and entity_type_for(eid) is entity_type]


def _new_or_changed_ids(before: Mapping[str, BaseEntity], after: Mapping[str, BaseEntity], entity_type: EntityType) -> list[str]:
    """Like `_new_ids`, but also counts an existing id whose *content*
    changed — `manage_decision`'s `open` then `defer` sequence keeps the
    same `DEC-nnn` id across both calls (a version bump, not a new id), so
    `not_my_call`'s check needs this instead of `_new_ids` alone."""

    return [
        eid
        for eid, entity in after.items()
        if entity_type_for(eid) is entity_type and (eid not in before or before[eid] != entity)
    ]


def evaluate_dont_know_routing(
    kind: DontKnowKind,
    entities_before: Mapping[str, BaseEntity],
    entities_after: Mapping[str, BaseEntity],
) -> DontKnowRoutingReport:
    """Diffs `entities_before`/`entities_after` (both
    `ppa.ledger.materialize.current_entities`'s own shape) to check that
    routing `kind` produced the entity DESIGN.md §3.4's table requires."""

    violations: list[str] = []

    new_assumptions = _new_ids(entities_before, entities_after, EntityType.ASSUMPTION)
    new_decisions = _new_or_changed_ids(entities_before, entities_after, EntityType.DECISION)
    new_unknowns = _new_ids(entities_before, entities_after, EntityType.UNKNOWN)
    new_questions = _new_ids(entities_before, entities_after, EntityType.QUESTION_ANSWER)
    new_research = _new_ids(entities_before, entities_after, EntityType.RESEARCH_FINDING)

    if kind == "dont_understand":
        if not new_questions:
            violations.append("dont_understand: no reframed question (new Q-nnn) was asked")
        research_routed_unknowns = [eid for eid in new_unknowns if entities_after[eid].route == "RESEARCH"]
        if research_routed_unknowns or new_research:
            violations.append("dont_understand: triggered research — never allowed, this is the cheap path")

    elif kind == "no_opinion":
        if not new_assumptions:
            violations.append("no_opinion: no Assumption was recorded")
        for eid in new_assumptions:
            if not entities_after[eid].user_confirmation_required:
                violations.append(f"no_opinion: {eid} was created without user_confirmation_required")

    elif kind == "depends_on_x":
        dependency_unknowns = [eid for eid in new_unknowns if entities_after[eid].route == "USER_DECISION"]
        if not dependency_unknowns:
            violations.append("depends_on_x: no Unknown(route=USER_DECISION) recorded for the dependency")

    elif kind == "not_my_call":
        deferred = [
            eid
            for eid in new_decisions
            if entities_after[eid].owner_type != "user" and entities_after[eid].status == "DECIDE_LATER"
        ]
        if not deferred:
            violations.append("not_my_call: no Decision with owner_type != user and status DECIDE_LATER")
        for eid in deferred:
            if entities_after[eid].expected_decision_date is None:
                violations.append(f"not_my_call: {eid} DECIDE_LATER without an expected_decision_date")

    elif kind == "unexplored":
        guidance_unknowns = [eid for eid in new_unknowns if entities_after[eid].route == "GUIDANCE"]
        if not guidance_unknowns:
            violations.append("unexplored: no Unknown(route=GUIDANCE) recorded — must hand off to Guidance Mode")
        for eid in guidance_unknowns:
            if not entities_after[eid].blocking:
                violations.append(f"unexplored: {eid} routed to GUIDANCE but not marked blocking")
        silent_assumptions = [eid for eid in new_assumptions if not entities_after[eid].user_confirmation_required]
        if silent_assumptions:
            violations.append("unexplored: a silent assumption was recorded instead of routing to Guidance")

    elif kind == "factually_unknown":
        research_unknowns = [eid for eid in new_unknowns if entities_after[eid].route == "RESEARCH"]
        if not research_unknowns:
            violations.append("factually_unknown: no Unknown(route=RESEARCH) recorded")

    elif kind == "needs_external_input":
        provisional = [
            eid
            for eid in new_assumptions
            if entities_after[eid].provisional and entities_after[eid].user_confirmation_required
        ]
        if not provisional:
            violations.append("needs_external_input: no provisional Assumption recorded pending external input")

    else:  # pragma: no cover - Literal makes this unreachable from typed callers
        violations.append(f"unknown dont_know kind: {kind!r}")

    return DontKnowRoutingReport(kind=kind, violations=violations)
