"""Case 10 (S12.2) — retry exhaustion: bounded, escalates with structure.

Proven directly against `ppa.recovery.retry.retry_operation` (an operation
that always fails `TRANSIENT`, exhausting the budget-of-3 rather than
looping forever) and `ppa.orchestrator.escalation.Escalation` — the
resulting `REPEATED_TOOL_FAILURE` escalation must construct at all (its own
required, non-empty fields are enforced by validator, not convention) and
`render_escalation` must end in a concrete question. No model call.
"""

from __future__ import annotations

from ppa.orchestrator.escalation import Escalation, EscalationTrigger, render_escalation
from ppa.recovery.retry import DEFAULT_RETRY_BUDGET, retry_operation
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_10"
CASE_NAME = "retry exhaustion, bounded and escalated with structure"


def _always_transient() -> ToolResult:
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.TRANSIENT, code="LEDGER_WRITE_TIMEOUT", is_retryable=True,
            recommended_action=RecoveryAction.RETRY_SAME, description="storage did not complete",
        ),
    )


def run_case(tmp_path=None) -> CaseOutcome:
    result, attempts = retry_operation(_always_transient, sleep=lambda _seconds: None)

    notes: list[str] = []
    passed = True
    if result.success:
        passed = False
        notes.append("an always-failing operation reported success")
    if attempts != DEFAULT_RETRY_BUDGET:
        passed = False
        notes.append(f"expected exactly the budget ({DEFAULT_RETRY_BUDGET}) attempts, got {attempts}")

    escalated = False
    try:
        escalation = Escalation(
            trigger=EscalationTrigger.REPEATED_TOOL_FAILURE,
            what_happened=f"a ledger write timed out {attempts} times in a row",
            what_is_missing="a successful write, or confirmation the operation should be abandoned",
            what_was_attempted=f"retried {attempts} times with backoff, exhausting the retry budget",
            options=["retry manually later", "abandon this write and continue without it"],
            question="Should I keep retrying this write, or move on without it for now?",
        )
        rendered = render_escalation(escalation)
        escalated = rendered.strip().endswith(escalation.question)
    except Exception as exc:  # pragma: no cover - the assertion below reports it
        notes.append(f"Escalation failed to construct: {exc!r}")

    if not escalated:
        passed = False
        notes.append("escalation did not construct into a rendering ending in a concrete question")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        recovery_applicable=True, recovered=False,
        tool_calls_attempted=attempts, retries_attempted=attempts - 1,
        escalation_applicable=True, escalated_correctly=escalated,
    )


def test_retry_exhaustion_is_bounded_and_escalates_with_structure():
    outcome = run_case()
    assert outcome.passed, outcome.notes
