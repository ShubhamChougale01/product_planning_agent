"""Case 6 (S12.2) — permission failure: rejected, routed, **not** retried.

Proven directly against `ppa.tools.dispatch.permission_error` fed through
`ppa.recovery.retry.retry_operation` — `PERMISSION`'s own fixed rule
(`ppa/results/categories.py`: `is_retryable=False`) means `retry_operation`
must return after exactly one attempt, no matter how large the budget. No
model call.
"""

from __future__ import annotations

from ppa.recovery.retry import retry_operation
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.tools.dispatch import permission_error
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_06"
CASE_NAME = "permission failure, rejected and never retried"


def run_case(tmp_path=None) -> CaseOutcome:
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        return permission_error("manage_linear_issue", "discovery")

    result, attempts = retry_operation(operation, budget=3, sleep=lambda _seconds: None)

    notes: list[str] = []
    passed = True
    if result.success:
        passed = False
        notes.append("a PERMISSION failure reported success")
    if result.error is not None and result.error.category is not ErrorCategory.PERMISSION:
        passed = False
        notes.append(f"expected PERMISSION, got {result.error.category}")
    if result.error is not None and result.error.recommended_action is not RecoveryAction.ABORT_AND_ROUTE:
        passed = False
        notes.append(f"expected ABORT_AND_ROUTE, got {result.error.recommended_action}")
    if attempts != 1 or calls["n"] != 1:
        passed = False
        notes.append(f"expected exactly one attempt, retry_operation made {attempts} (operation ran {calls['n']} times)")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=1, tool_calls_invalid=1,
        retries_attempted=attempts - 1, retries_unnecessary=max(attempts - 1, 0),
    )


def test_permission_failure_is_rejected_and_never_retried():
    outcome = run_case()
    assert outcome.passed, outcome.notes
