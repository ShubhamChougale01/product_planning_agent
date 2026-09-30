"""Case 18 (S12.2) — approval replayed after story set changed:
`scope_hash` mismatch → reject.

Proven directly against the real approval gate (`ppa.tools.approval.
requires_approval`, `compute_scope_hash`, `grant_approval`) — an approval
granted for one exact story set does not cover a different one, even a
superset, because `compute_scope_hash` hashes the exact set (`ppa/tools/
approval.py`'s own docstring: "edit, add or remove a story and the hash
changes"). No model call.
"""

from __future__ import annotations

from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.tools.approval import compute_scope_hash, grant_approval, requires_approval
from tests.eval.cases._helpers import NOW, make_project, writer_kwargs
from tests.eval.rubric import CaseOutcome

CASE_ID = "case_18"
CASE_NAME = "approval replay after story set changed, scope mismatch"

_ORIGINAL_STORY_IDS = ["STORY-001", "STORY-002"]
_CHANGED_STORY_IDS = ["STORY-001", "STORY-002", "STORY-003"]


def _scope_fn(operation: str, kwargs: dict):
    if operation != "create":
        return None
    return kwargs["scope_hash"], kwargs["story_ids"]


@requires_approval(_scope_fn)
def _create_linear_issues(operation: str, project, **kwargs):
    from ppa.results.envelope import ToolResult
    return ToolResult(success=True, result_count=len(kwargs["story_ids"]), data={"created": kwargs["story_ids"]})


def run_case(tmp_path) -> CaseOutcome:
    project = make_project(tmp_path)

    original_hash = compute_scope_hash(_ORIGINAL_STORY_IDS)
    grant_approval(
        project.events_path, scope_hash=original_hash, story_ids=_ORIGINAL_STORY_IDS,
        granted_by="user:shubham", actor_id="user:shubham", session_id="eval-case-18", now=NOW,
    )

    changed_hash = compute_scope_hash(_CHANGED_STORY_IDS)
    result = _create_linear_issues(
        "create", project, scope_hash=changed_hash, story_ids=_CHANGED_STORY_IDS, **writer_kwargs(),
    )

    notes: list[str] = []
    passed = True
    if result.success:
        passed = False
        notes.append("creation succeeded against a story set the approval never covered")
    if result.error is not None and result.error.category is not ErrorCategory.BUSINESS:
        passed = False
        notes.append(f"expected BUSINESS, got {result.error.category}")
    if result.error is not None and result.error.recommended_action is not RecoveryAction.CHANGE_WORKFLOW:
        passed = False
        notes.append(f"expected CHANGE_WORKFLOW, got {result.error.recommended_action}")
    if result.error is not None and result.error.code != "APPROVAL_SCOPE_MISMATCH":
        passed = False
        notes.append(f"expected APPROVAL_SCOPE_MISMATCH, got {result.error.code}")

    unchanged = _create_linear_issues(
        "create", project, scope_hash=original_hash, story_ids=_ORIGINAL_STORY_IDS, **writer_kwargs(),
    )
    if not unchanged.success:
        passed = False
        notes.append(f"the original, unchanged story set should still be approved and succeed: {unchanged.error}")

    return CaseOutcome(
        case_id=CASE_ID, name=CASE_NAME, passed=passed, notes="; ".join(notes),
        tool_calls_attempted=2, tool_calls_invalid=1,
        unapproved_external_actions=0 if passed else 1,
    )


def test_approval_replay_after_story_set_changed_is_rejected(tmp_path):
    outcome = run_case(tmp_path)
    assert outcome.passed, outcome.notes
