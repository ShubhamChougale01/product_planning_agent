"""Case 4 (S12.2) — validation error: `CORRECT_AND_RETRY`; the corrected
request succeeds.

Proven directly against `ppa.tools.interaction.ask_user` — a question
missing `why_asked` is rejected `VALIDATION`/`CORRECT_AND_RETRY` before any
event is written (its own docstring: "the whole batch rejected... nothing
is written"); supplying the missing field and calling again succeeds. No
model call: this is `ask_user`'s own validation contract, not a claim about
what a live turn would send.
"""

from __future__ import annotations

from ppa.ledger.materialize import current_entities
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.tools.interaction import ask_user
from tests.eval.cases._helpers import make_project, writer_kwargs
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_04"
CASE_NAME = "validation error, corrected and retried"

_BROKEN_QUESTION = [{"text": "Which payment processor should we integrate?"}]  # missing why_asked
_CORRECTED_QUESTION = [{
    "text": "Which payment processor should we integrate?",
    "why_asked": "determines integration scope and PCI posture",
}]


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path)
    entities_before = current_entities(project.events_path)

    first = ask_user(_BROKEN_QUESTION, project, **writer_kwargs())

    notes: list[str] = []
    passed = True

    if first.success:
        passed = False
        notes.append("the broken batch (missing why_asked) succeeded — should have been rejected")
    if first.error is not None and first.error.category is not ErrorCategory.VALIDATION:
        passed = False
        notes.append(f"expected VALIDATION, got {first.error.category}")
    if first.error is not None and first.error.recommended_action is not RecoveryAction.CORRECT_AND_RETRY:
        passed = False
        notes.append(f"expected CORRECT_AND_RETRY, got {first.error.recommended_action}")

    entities_after_reject = current_entities(project.events_path)
    if entities_after_reject != entities_before:
        passed = False
        notes.append("the rejected batch still wrote to the ledger")

    second = ask_user(_CORRECTED_QUESTION, project, **writer_kwargs())
    if not second.success:
        passed = False
        notes.append(f"the corrected request still failed: {second.error}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        recovery_applicable=True, recovered=second.success,
        tool_calls_attempted=2, tool_calls_invalid=1 if not first.success else 0,
    )


def test_validation_error_is_corrected_and_retried(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
