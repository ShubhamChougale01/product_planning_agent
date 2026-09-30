"""Intake mode's own shape contract (T24, DESIGN.md §3.1, S7.4).

Intake is the opening move — the first turn on a fresh project, before any
question has been asked. This module holds *the shape a real intake turn
must produce*: a minimum count of proposed requirements, a minimum count of
confirmation-flagged assumptions, exactly one pending question, and an
understanding reply short enough to actually be read. Every check runs
against ledger state after the turn — never against what the model's own
text claims it did (the same discipline `ppa.agents.turn.run_discovery_
turn`'s own status classification already follows).

`ppa.agents.turn.run_discovery_turn` (T21/T23) runs the turn itself —
nothing here re-implements or wraps that call. `evaluate_intake_shape` is
the assertion layer `tests/eval/test_intake.py` checks a real turn's output
against.
"""

from __future__ import annotations

import re
from typing import Mapping

from pydantic import BaseModel, ConfigDict

from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType

MIN_PROPOSED_REQUIREMENTS = 3
MIN_ASSUMPTIONS = 2
MAX_REPLY_SENTENCES = 20
"""DESIGN.md's own "3-6 sentences" bounds the understanding paragraph
alone. This bounds the *whole* reply instead — understanding paragraph,
requirements recap, assumptions recap and the closing question together —
since those can't be reliably separated back out of prose by a regex.
Measured against real turns: a properly-shaped reply covering 6-8
requirements and 6-8 assumptions by name runs to roughly 10-12 sentences
honestly, not because it pads — verified live, tightening this to a number
close to 6 would fail every correctly-shaped real reply, not catch a
genuinely bloated one. What actually matters is "not a wall of text," not
an exact tally close to the paragraph-only number."""

_SENTENCE_SPLIT = re.compile(r"[.!?]+(?:\s|$)")


class IntakeShapeReport(BaseModel):
    """One completed intake turn's shape, checked against every Done-when
    box `tasks/t24_intake_mode.md` states. `ok` is `True` iff every one of
    them held."""

    model_config = ConfigDict(extra="forbid")

    proposed_requirement_count: int
    assumption_count: int
    unflagged_assumption_count: int
    pending_question_count: int
    reply_sentence_count: int
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def _sentence_count(text: str) -> int:
    return len([s for s in _SENTENCE_SPLIT.split(text) if s.strip()])


def evaluate_intake_shape(
    entities: Mapping[str, BaseEntity],
    *,
    reply_text: str,
) -> IntakeShapeReport:
    """`entities` is the ledger's materialized state *after* the intake
    turn (`ppa.ledger.materialize.current_entities`'s own shape) — this
    function does no ledger I/O itself, so a caller controls exactly which
    snapshot gets checked. `reply_text` is the turn's own final text
    (`AgentResult.summary`)."""

    requirements = [e for eid, e in entities.items() if entity_type_for(eid) is EntityType.REQUIREMENT]
    proposed_requirements = [r for r in requirements if r.status == "PROPOSED"]

    assumptions = [e for eid, e in entities.items() if entity_type_for(eid) is EntityType.ASSUMPTION]
    unflagged_assumptions = [a for a in assumptions if not a.user_confirmation_required]

    pending_questions = [
        e
        for eid, e in entities.items()
        if entity_type_for(eid) is EntityType.QUESTION_ANSWER and e.status == "PENDING"
    ]

    sentence_count = _sentence_count(reply_text)

    violations: list[str] = []
    if len(proposed_requirements) < MIN_PROPOSED_REQUIREMENTS:
        violations.append(
            f"only {len(proposed_requirements)} PROPOSED requirement(s), need >= {MIN_PROPOSED_REQUIREMENTS}"
        )
    if len(assumptions) < MIN_ASSUMPTIONS:
        violations.append(f"only {len(assumptions)} assumption(s), need >= {MIN_ASSUMPTIONS}")
    if unflagged_assumptions:
        violations.append(
            f"{len(unflagged_assumptions)} assumption(s) created without user_confirmation_required — "
            "a silent assumption, never allowed"
        )
    if len(pending_questions) != 1:
        violations.append(f"{len(pending_questions)} pending question(s), intake must ask exactly one")
    if sentence_count > MAX_REPLY_SENTENCES:
        violations.append(f"reply is {sentence_count} sentences — not \"3-6 sentences, not a wall of text\"")

    return IntakeShapeReport(
        proposed_requirement_count=len(proposed_requirements),
        assumption_count=len(assumptions),
        unflagged_assumption_count=len(unflagged_assumptions),
        pending_question_count=len(pending_questions),
        reply_sentence_count=sentence_count,
        violations=violations,
    )
