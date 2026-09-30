"""Clarify mode's own shape contract (T25, DESIGN.md §1.4, §3.2, S7.5).

"This is the product." The filter — deciding what *not* to ask — is the
entire point; an agent that asks every generated candidate has failed no
matter how well-formed the questions are. This module checks one completed
round's ledger state against that filter actually having run: how many
questions it spent, how many assumptions it recorded instead of asking, how
many candidates it routed to research, and whether it spread across areas
rather than clustering in one.

Like `ppa.agents.modes.intake`, every check here runs against entities the
round actually wrote — never against what the model's own text claims.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.engines.question_engine import MAX_QUESTIONS_PER_ROUND
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType


class ClarifyRoundReport(BaseModel):
    """One completed CLARIFY round, checked against
    `tasks/t25_clarify_mode_question_engine.md`'s own per-round Done-when
    boxes. The "at least one candidate per session routed to research" box
    is session-level, not per-round — checked separately, across rounds, by
    summing `unknowns_routed_to_research_count`."""

    model_config = ConfigDict(extra="forbid")

    questions_asked_count: int
    assumptions_recorded_count: int
    unknowns_routed_to_research_count: int
    distinct_areas_asked_about: int
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def _new_ids(before: Mapping[str, BaseEntity], after: Mapping[str, BaseEntity], entity_type: EntityType) -> list[str]:
    return [
        eid
        for eid in after
        if eid not in before and entity_type_for(eid) is entity_type
    ]


def evaluate_clarify_round(
    entities_before: Mapping[str, BaseEntity],
    entities_after: Mapping[str, BaseEntity],
) -> ClarifyRoundReport:
    """Diffs `entities_before`/`entities_after` (both
    `ppa.ledger.materialize.current_entities`'s own shape) to find exactly
    what this one round wrote, then checks it against the filter actually
    having done its job. **"Records at least one assumption instead of
    asking about it" is the criterion that matters** (DESIGN.md's own
    framing) — if a round asks the hard cap and records nothing, the filter
    did not run, no matter how well-formed the five questions are.
    """

    new_questions = _new_ids(entities_before, entities_after, EntityType.QUESTION_ANSWER)
    new_assumptions = _new_ids(entities_before, entities_after, EntityType.ASSUMPTION)
    new_unknowns = [
        eid for eid in _new_ids(entities_before, entities_after, EntityType.UNKNOWN)
        if entities_after[eid].route == "RESEARCH"
    ]

    areas_asked: set[str] = set()
    for eid in new_questions:
        areas_asked.update(entities_after[eid].target_areas)

    violations: list[str] = []
    if len(new_questions) > MAX_QUESTIONS_PER_ROUND:
        violations.append(f"{len(new_questions)} questions asked this round, hard cap is {MAX_QUESTIONS_PER_ROUND}")
    if not new_assumptions:
        violations.append(
            "zero assumptions recorded this round — the filter is not working if every "
            "candidate became a question"
        )
    if new_questions and len(areas_asked) < min(len(new_questions), 2):
        violations.append(
            f"{len(new_questions)} question(s) covering only {len(areas_asked)} distinct area(s) — "
            "prefer a spread across areas over clustering in one"
        )

    return ClarifyRoundReport(
        questions_asked_count=len(new_questions),
        assumptions_recorded_count=len(new_assumptions),
        unknowns_routed_to_research_count=len(new_unknowns),
        distinct_areas_asked_about=len(areas_asked),
        violations=violations,
    )
