"""Case 2 (S12.2) — wrong-tool attempt: PERMISSION or BUSINESS, body never
runs.

Proven directly against `ppa.tools.dispatch.dispatch` — permission is layer
1, checked before the registered handler is ever called (`ppa/tools/
dispatch.py`'s own docstring: "Permission runs first... a permission
failure should not leak schema details"). No model call: which tool a real
turn *tries* to call is case 1's claim, not this one's — this case proves
the gate itself, given an attempt that already happened.
"""

from __future__ import annotations

import anyio

from ppa.ledger.materialize import current_entities
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.tools.dispatch import InvocationContext, dispatch
from tests.eval.cases._helpers import make_project
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_02"
CASE_NAME = "wrong-tool attempt"


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path)
    entities_before = current_entities(project.events_path)

    ctx = InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="eval-case-02",
        audit_path=project.audit_path,
    )
    result = anyio.run(dispatch, "manage_linear_issue", {"operation": "create"}, ctx)

    entities_after = current_entities(project.events_path)
    notes: list[str] = []
    passed = True

    if result.success:
        passed = False
        notes.append("manage_linear_issue succeeded for the discovery agent — no grant should allow this")
    if result.error is not None and result.error.category not in (ErrorCategory.PERMISSION, ErrorCategory.BUSINESS):
        passed = False
        notes.append(f"expected PERMISSION or BUSINESS, got {result.error.category}")
    if result.error is not None and result.error.recommended_action not in (
        RecoveryAction.ABORT_AND_ROUTE, RecoveryAction.CHANGE_WORKFLOW,
    ):
        passed = False
        notes.append(f"unexpected recommended_action {result.error.recommended_action}")
    if entities_after != entities_before:
        passed = False
        notes.append("the ledger changed — the tool body ran despite the rejected attempt")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_selection_correct=None,
        tool_calls_attempted=1, tool_calls_invalid=1,
        workflow_violation=not passed,
    )


def test_wrong_tool_attempt_is_rejected_and_never_runs(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
