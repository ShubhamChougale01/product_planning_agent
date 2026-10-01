"""Case 7 (S12.2) — business/workflow failure: workflow change, not retry.

Proven directly against `ppa.validation.workflow.check` (layer 3) fed
through `retry_operation` — `manage_plan` is legal only in `PLANNING`
(`ppa/validation/workflow.py`'s own `_LEGAL_STATES`); attempting it while
still in `DISCOVERY` is `BUSINESS`/`CHANGE_WORKFLOW`, and `is_retryable` is
fixed `False` for that category — the caller must change what it's doing,
never resend the identical call. No model call.
"""

from __future__ import annotations

from ppa.recovery.retry import retry_operation
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.validation import workflow
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_07"
CASE_NAME = "business/workflow failure, not retried"


def run_case(tmp_path=None) -> CaseOutcome:
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        rejected = workflow.check("manage_plan", "DISCOVERY")
        assert rejected is not None, "manage_plan should be illegal in DISCOVERY"
        return rejected

    result, attempts = retry_operation(operation, budget=3, sleep=lambda _seconds: None)

    notes: list[str] = []
    passed = True
    if result.success:
        passed = False
        notes.append("a BUSINESS/workflow failure reported success")
    if result.error is not None and result.error.category is not ErrorCategory.BUSINESS:
        passed = False
        notes.append(f"expected BUSINESS, got {result.error.category}")
    if result.error is not None and result.error.recommended_action is not RecoveryAction.CHANGE_WORKFLOW:
        passed = False
        notes.append(f"expected CHANGE_WORKFLOW, got {result.error.recommended_action}")
    if attempts != 1 or calls["n"] != 1:
        passed = False
        notes.append(f"expected exactly one attempt, got {attempts}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=1, tool_calls_invalid=1,
        retries_attempted=attempts - 1, retries_unnecessary=max(attempts - 1, 0),
        workflow_violation=False,
    )


def test_business_workflow_failure_is_never_retried():
    outcome = run_case()
    assert outcome.passed, outcome.notes
