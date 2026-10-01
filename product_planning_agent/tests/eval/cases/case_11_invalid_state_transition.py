"""Case 11 (S12.2) — invalid state transition: rejected, naming the
blocking rule.

Proven directly against `ppa.validation.consistency.check_transition` (layer
5) — `REJECTED` is terminal for a `Requirement` (`ppa/ledger/transitions.
py`'s own matrix: `"REJECTED": set()`), so `REJECTED -> CONFIRMED` must be
rejected `BUSINESS`/`ILLEGAL_TRANSITION`, and the rejection's own
description must name the entity type and both statuses, not just say "no."
No model call.
"""

from __future__ import annotations

from ppa.ledger.models import EntityType
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.validation.consistency import check_transition
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_11"
CASE_NAME = "invalid state transition, blocking rule named"


def run_case(tmp_path=None) -> CaseOutcome:
    result = check_transition(EntityType.REQUIREMENT, "REJECTED", "CONFIRMED")

    notes: list[str] = []
    passed = True
    if result is None:
        passed = False
        notes.append("REJECTED -> CONFIRMED was accepted as legal — it must not be")
    else:
        if result.success:
            passed = False
            notes.append("check_transition reported success for an illegal move")
        if result.error is not None and result.error.category is not ErrorCategory.BUSINESS:
            passed = False
            notes.append(f"expected BUSINESS, got {result.error.category}")
        if result.error is not None and result.error.recommended_action is not RecoveryAction.CHANGE_WORKFLOW:
            passed = False
            notes.append(f"expected CHANGE_WORKFLOW, got {result.error.recommended_action}")
        description = result.error.description if result.error else ""
        if "REJECTED" not in description or "CONFIRMED" not in description:
            passed = False
            notes.append(f"description does not name the blocking statuses: {description!r}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=1, tool_calls_invalid=1,
    )


def test_invalid_state_transition_is_rejected_naming_the_rule():
    outcome = run_case()
    assert outcome.passed, outcome.notes
