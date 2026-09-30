"""Case 12 (S12.2) — Linear creation before approval: `BUSINESS` reject —
passes in v1 against stubs.

Proven directly against `ppa.validation.workflow.check` (layer 3) —
`manage_linear_issue` is legal only in `PLAN_APPROVED`/`DELIVERY`
(`ppa/validation/workflow.py`'s own `_LEGAL_STATES`); a v1 project never
leaves `DISCOVERY`, so this rejection is real today even though Delivery's
own Linear integration is still a stub (`ppa/tools/delivery_tools.py`,
`NOT_IMPLEMENTED` beyond this gate) — exactly the case's own "passes in v1
against stubs" framing: the gate is real, the thing behind it isn't yet.
No model call.
"""

from __future__ import annotations

from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.validation import workflow
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_12"
CASE_NAME = "Linear creation before approval, BUSINESS reject"


def run_case(tmp_path=None) -> CaseOutcome:
    result = workflow.check("manage_linear_issue", "DISCOVERY")

    notes: list[str] = []
    passed = True
    if result is None:
        passed = False
        notes.append("manage_linear_issue was accepted as legal in DISCOVERY — it must not be")
    else:
        if result.success:
            passed = False
            notes.append("workflow.check reported success for a pre-approval Linear creation attempt")
        if result.error is not None and result.error.category is not ErrorCategory.BUSINESS:
            passed = False
            notes.append(f"expected BUSINESS, got {result.error.category}")
        if result.error is not None and result.error.recommended_action is not RecoveryAction.CHANGE_WORKFLOW:
            passed = False
            notes.append(f"expected CHANGE_WORKFLOW, got {result.error.recommended_action}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=1, tool_calls_invalid=1,
    )


def test_linear_creation_before_approval_is_rejected():
    outcome = run_case()
    assert outcome.passed, outcome.notes
