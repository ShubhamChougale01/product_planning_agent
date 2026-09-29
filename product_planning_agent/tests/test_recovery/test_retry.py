"""T32 tests — bounded retry (`ppa/recovery/retry.py`). Every Done-when box
in `tasks/t32_transactions_retry_recovery.md` that concerns retry maps to at
least one test here.
"""

from __future__ import annotations

from ppa.recovery.retry import DEFAULT_RETRY_BUDGET, retry_batch, retry_operation
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult


def _ok(data="done") -> ToolResult:
    return ToolResult(success=True, result_count=1, data=data)


def _transient(**overrides) -> ToolResult:
    base = dict(
        category=ErrorCategory.TRANSIENT, code="LEDGER_WRITE_TIMEOUT", is_retryable=True,
        retry_after_ms=1, description="timed out, try again", recommended_action=RecoveryAction.RETRY_SAME,
    )
    base.update(overrides)
    return ToolResult(success=False, error=ErrorInfo(**base))


def _validation(**overrides) -> ToolResult:
    base = dict(
        category=ErrorCategory.VALIDATION, code="BAD_INPUT", is_retryable=False,
        description="malformed input", recommended_action=RecoveryAction.CORRECT_AND_RETRY,
    )
    base.update(overrides)
    return ToolResult(success=False, error=ErrorInfo(**base))


def _no_sleep(_seconds: float) -> None:
    pass  # tests never actually wait on backoff


# ---------------------------------------------------------------------------
# Done when: a flapping tool succeeds within the budget of 3.
# ---------------------------------------------------------------------------


def test_a_flapping_tool_succeeds_within_the_budget_of_three():
    calls = []

    def flapping() -> ToolResult:
        calls.append(1)
        if len(calls) < 3:
            return _transient()
        return _ok("succeeded on the third attempt")

    result, attempts = retry_operation(flapping, sleep=_no_sleep)

    assert result.success
    assert result.data == "succeeded on the third attempt"
    assert attempts == 3
    assert attempts <= DEFAULT_RETRY_BUDGET


def test_a_tool_that_succeeds_first_try_is_never_retried():
    calls = []

    def always_ok() -> ToolResult:
        calls.append(1)
        return _ok()

    result, attempts = retry_operation(always_ok, sleep=_no_sleep)

    assert result.success
    assert attempts == 1
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Done when: an always-failing tool exhausts and returns PARTIAL_FAILURE
# with attempt counts and partial results.
# ---------------------------------------------------------------------------


def test_an_always_failing_tool_exhausts_within_budget():
    calls = []

    def always_fails() -> ToolResult:
        calls.append(1)
        return _transient()

    result, attempts = retry_operation(always_fails, sleep=_no_sleep)

    assert not result.success
    assert attempts == DEFAULT_RETRY_BUDGET
    assert len(calls) == DEFAULT_RETRY_BUDGET


def test_retry_batch_reports_partial_failure_with_attempt_counts_and_partial_results():
    def ok_op() -> ToolResult:
        return _ok()

    def failing_op() -> ToolResult:
        return _transient()

    operations = [ok_op, ok_op, ok_op, failing_op, failing_op]
    result = retry_batch(operations, sleep=_no_sleep)

    assert result.status == "PARTIAL_FAILURE"
    assert result.attempted == 5
    assert result.successful == 3
    assert result.failed == 2
    assert result.error_category is ErrorCategory.TRANSIENT
    assert result.next_action == "ESCALATE_TO_ORCHESTRATOR"
    assert len(result.partial_results) == 5
    assert result.attempted == result.successful + result.failed


def test_retry_batch_reports_ok_when_every_operation_eventually_succeeds():
    def ok_op() -> ToolResult:
        return _ok()

    result = retry_batch([ok_op, ok_op], sleep=_no_sleep)

    assert result.status == "OK"
    assert result.attempted == 2
    assert result.successful == 2
    assert result.failed == 0
    assert result.error_category is None
    assert result.next_action is None


# ---------------------------------------------------------------------------
# Done when: only TRANSIENT errors are retried — VALIDATION is never
# resent identically.
# ---------------------------------------------------------------------------


def test_validation_failure_is_never_retried():
    calls = []

    def invalid() -> ToolResult:
        calls.append(1)
        return _validation()

    result, attempts = retry_operation(invalid, sleep=_no_sleep)

    assert not result.success
    assert attempts == 1
    assert len(calls) == 1  # never resent


def test_retry_after_ms_governs_the_backoff_delay():
    slept = []

    def flapping() -> ToolResult:
        if not slept:
            return _transient(retry_after_ms=250)
        return _ok()

    def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    result, attempts = retry_operation(flapping, sleep=_record_sleep)

    assert result.success
    assert attempts == 2
    assert slept == [0.25]
