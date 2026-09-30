"""Case 5 (S12.2) — transient failure: retried within budget, succeeds.

Proven directly against `ppa.recovery.retry.retry_operation` — a stub
operation that fails `TRANSIENT` twice, then succeeds on the third
(budget-of-3) attempt. No model call: retry policy is deterministic code
(`ppa/recovery/retry.py`), not a claim about model behavior.
"""

from __future__ import annotations

from ppa.recovery.retry import DEFAULT_RETRY_BUDGET, retry_operation
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_05"
CASE_NAME = "transient failure, retried within budget"


def _flaky_operation():
    calls = {"n": 0}

    def operation() -> ToolResult:
        calls["n"] += 1
        if calls["n"] < DEFAULT_RETRY_BUDGET:
            return ToolResult(
                success=False,
                error=ErrorInfo(
                    category=ErrorCategory.TRANSIENT, code="LEDGER_WRITE_TIMEOUT", is_retryable=True,
                    recommended_action=RecoveryAction.RETRY_SAME, description="timed out",
                ),
            )
        return ToolResult(success=True, result_count=1, data={"ok": True})

    return operation, calls


def run_case(tmp_path=None) -> CaseOutcome:
    """`tmp_path` is accepted (and unused) purely so the scorecard runner
    can call every case's `run_case` uniformly — this case needs no real
    project, only the retry policy itself."""

    operation, calls = _flaky_operation()
    result, attempts = retry_operation(operation, sleep=lambda _seconds: None)

    notes: list[str] = []
    passed = True
    if not result.success:
        passed = False
        notes.append(f"final result was not a success: {result.error}")
    if attempts != DEFAULT_RETRY_BUDGET:
        passed = False
        notes.append(f"expected exactly {DEFAULT_RETRY_BUDGET} attempts, got {attempts}")
    if calls["n"] != attempts:
        passed = False
        notes.append("attempts reported did not match calls actually made")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        recovery_applicable=True, recovered=result.success,
        tool_calls_attempted=attempts, retries_attempted=attempts - 1,
    )


def test_transient_failure_is_retried_within_budget_and_succeeds():
    outcome = run_case()
    assert outcome.passed, outcome.notes
