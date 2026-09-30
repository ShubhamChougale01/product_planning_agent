"""Case 8 (S12.2) — empty successful result: `success=True, result_count=0`,
the agent continues.

Proven directly against `ppa.tools.discovery_tools.read_planning_state`
(scope="entity", filtered on a status nothing matches on a fresh project) —
`ppa/results/envelope.py`'s own module docstring names this as one of three
legal states ("a query that ran and found nothing is not a failure").
Fed through `retry_operation` to prove the second half of the case's own
claim: a success, even an empty one, is never retried. No model call.
"""

from __future__ import annotations

from ppa.recovery.retry import retry_operation
from ppa.tools.discovery_tools import read_planning_state
from tests.eval.cases._helpers import make_project
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_08"
CASE_NAME = "empty successful result, agent continues"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path)
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        return read_planning_state("entity", project, status="REJECTED")

    result, attempts = retry_operation(operation, budget=3, sleep=lambda _seconds: None)

    notes: list[str] = []
    passed = True
    if not result.success:
        passed = False
        notes.append(f"expected success=True, got an error: {result.error}")
    if result.result_count != 0:
        passed = False
        notes.append(f"expected result_count=0 on a fresh project, got {result.result_count}")
    if result.error is not None:
        passed = False
        notes.append("a successful, empty result carried an error object")
    if attempts != 1 or calls["n"] != 1:
        passed = False
        notes.append(f"an empty success was retried ({attempts} attempts) — it must never be treated as failure")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=1, retries_attempted=attempts - 1, retries_unnecessary=max(attempts - 1, 0),
    )


def test_empty_successful_result_is_never_retried(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
