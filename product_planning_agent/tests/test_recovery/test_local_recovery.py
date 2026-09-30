"""T32 tests — "local recovery first" (DESIGN.md §2.14's own phrase): a
subagent retries locally, inside its own turn, before ever propagating to
the Orchestrator; what the Orchestrator receives is `AgentResult(status=
PARTIAL, ...)` carrying `retry_batch`'s own attempt counts and partial
results, never a bare failure with nothing to act on.

`AgentResult` (`ppa.agents.base`, T20) already carries exactly `retry_
batch`'s own fields (`attempted`/`successful`/`failed`/`partial_results`/
`next_action`) — this is that shape actually exercised, end to end, for
the first time.
"""

from __future__ import annotations

from ppa.agents.base import AgentResult, AgentResultStatus
from ppa.recovery.retry import retry_batch
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult


def _ok() -> ToolResult:
    return ToolResult(success=True, result_count=1, data="a research finding")


def _transient() -> ToolResult:
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.TRANSIENT, code="RESEARCH_TIMEOUT", is_retryable=True,
            retry_after_ms=1, description="research call timed out", recommended_action=RecoveryAction.RETRY_SAME,
        ),
    )


def _no_sleep(_seconds: float) -> None:
    pass


def _run_local_subagent_turn(operations) -> AgentResult:
    """Stands in for a real subagent's own turn (e.g. `ppa.agents.
    subagents.research.run_research_session` batching `RESEARCH_REQUIRED`)
    — it retries every operation locally via `retry_batch` and only ever
    hands the Orchestrator a structured `AgentResult`, whatever the outcome."""

    outcome = retry_batch(operations, sleep=_no_sleep)
    if outcome.status == "OK":
        return AgentResult(status=AgentResultStatus.OK, summary="all operations succeeded, some after local retry")
    return AgentResult(
        status=AgentResultStatus.PARTIAL,
        summary=f"{outcome.successful}/{outcome.attempted} succeeded after local retry; {outcome.failed} exhausted their budget",
        attempted=outcome.attempted, successful=outcome.successful, failed=outcome.failed,
        partial_results=outcome.partial_results, next_action=outcome.next_action,
    )


def test_a_subagent_retries_locally_and_the_orchestrator_receives_partials_not_a_bare_failure():
    operations = [_ok, _ok, _transient, _transient]

    result = _run_local_subagent_turn(operations)

    assert result.status is AgentResultStatus.PARTIAL
    assert result.attempted == 4
    assert result.successful == 2
    assert result.failed == 2
    assert result.next_action == "ESCALATE_TO_ORCHESTRATOR"
    assert len(result.partial_results) == 4
    assert result.error is None  # PARTIAL is not NON_RECOVERABLE — there is no bare error here


def test_a_subagent_reports_ok_when_local_retry_recovers_everything():
    calls = []

    def flapping_once() -> ToolResult:
        calls.append(1)
        return _transient() if len(calls) == 1 else _ok()

    result = _run_local_subagent_turn([flapping_once])

    assert result.status is AgentResultStatus.OK
    assert len(calls) == 2  # retried locally, inside this same "subagent turn" — never surfaced as a failure
