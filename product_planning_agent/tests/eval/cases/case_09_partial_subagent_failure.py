"""Case 9 (S12.2) — partial subagent failure: partials preserved and
propagated.

Proven directly against `ppa.recovery.retry.retry_batch` — a batch of five
independent operations where two never recover; `RetryBatchResult` must
report `PARTIAL_FAILURE` with `attempted == successful + failed` and every
operation's own final result still present in `partial_results`, never
collapsed into a single undifferentiated failure. No model call.
"""

from __future__ import annotations

from ppa.recovery.retry import retry_batch
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_09"
CASE_NAME = "partial subagent failure, partials preserved"

_BATCH_SIZE = 5
_PERMANENTLY_FAILING = {1, 3}  # indices that never recover


def _make_operations():
    def make(index: int):
        def operation() -> ToolResult:
            if index in _PERMANENTLY_FAILING:
                return ToolResult(
                    success=False,
                    error=ErrorInfo(
                        category=ErrorCategory.PERMISSION, code="TOOL_NOT_GRANTED", is_retryable=False,
                        recommended_action=RecoveryAction.ABORT_AND_ROUTE,
                        description=f"operation {index} is not granted",
                    ),
                )
            return ToolResult(success=True, result_count=1, data={"index": index})

        return operation

    return [make(i) for i in range(_BATCH_SIZE)]


def run_case(tmp_path=None) -> CaseOutcome:
    batch = retry_batch(_make_operations(), sleep=lambda _seconds: None)

    notes: list[str] = []
    passed = True
    if batch.status != "PARTIAL_FAILURE":
        passed = False
        notes.append(f"expected PARTIAL_FAILURE, got {batch.status}")
    if batch.attempted != _BATCH_SIZE:
        passed = False
        notes.append(f"expected attempted={_BATCH_SIZE}, got {batch.attempted}")
    if batch.successful != _BATCH_SIZE - len(_PERMANENTLY_FAILING):
        passed = False
        notes.append(f"expected {_BATCH_SIZE - len(_PERMANENTLY_FAILING)} successes, got {batch.successful}")
    if batch.failed != len(_PERMANENTLY_FAILING):
        passed = False
        notes.append(f"expected {len(_PERMANENTLY_FAILING)} failures, got {batch.failed}")
    if len(batch.partial_results) != _BATCH_SIZE:
        passed = False
        notes.append("partial_results does not carry one entry per operation — some result was dropped")
    if batch.next_action != "ESCALATE_TO_ORCHESTRATOR":
        passed = False
        notes.append(f"expected next_action=ESCALATE_TO_ORCHESTRATOR, got {batch.next_action}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        recovery_applicable=True, recovered=(batch.status == "OK"),
        tool_calls_attempted=_BATCH_SIZE, tool_calls_invalid=len(_PERMANENTLY_FAILING),
        escalation_applicable=True, escalated_correctly=(batch.next_action == "ESCALATE_TO_ORCHESTRATOR"),
    )


def test_partial_subagent_failure_preserves_and_propagates_partials():
    outcome = run_case()
    assert outcome.passed, outcome.notes
