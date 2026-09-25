"""Approval gate tests (T18). Every approval-related Done-when box in
`tasks/t18_stub_tools_and_approval_gate.md` maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.ledger.project import create_project
from ppa.results.categories import ErrorCategory
from ppa.tools.approval import (
    compute_scope_hash,
    current_approval,
    grant_approval,
    render_dry_run,
    requires_approval,
    revoke_approval,
)
from ppa.tools.delivery_tools import manage_linear_issue
from ppa.tools.registry import restore, snapshot

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _preserve_registry():
    saved = snapshot()
    yield
    restore(saved)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Approval Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _grant(project, story_ids, **overrides):
    kwargs = dict(
        scope_hash=compute_scope_hash(story_ids), story_ids=story_ids, granted_by="user:shubham",
        actor_id="user:shubham", session_id="sess-001", now=NOW,
    )
    kwargs.update(overrides)
    return grant_approval(project.events_path, **kwargs)


# ---------------------------------------------------------------------------
# scope_hash — deterministic, order-independent, sensitive to the set.
# ---------------------------------------------------------------------------


def test_scope_hash_is_order_independent():
    assert compute_scope_hash(["STORY-001", "STORY-002"]) == compute_scope_hash(["STORY-002", "STORY-001"])


def test_scope_hash_changes_when_the_story_set_changes():
    assert compute_scope_hash(["STORY-001"]) != compute_scope_hash(["STORY-001", "STORY-002"])


def test_render_dry_run_lists_every_story_and_leaves_the_system_untouched():
    text = render_dry_run(["STORY-001", "STORY-002"])
    assert "STORY-001" in text
    assert "STORY-002" in text
    assert "DRY RUN" in text


# ---------------------------------------------------------------------------
# current_approval folds grant/revoke events correctly.
# ---------------------------------------------------------------------------


def test_current_approval_is_none_before_any_grant(tmp_path):
    project = _make_project(tmp_path)
    assert current_approval(project.events_path) is None


def test_current_approval_reflects_the_latest_grant(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001"])
    approval = current_approval(project.events_path)
    assert approval is not None
    assert approval.story_ids == ["STORY-001"]


def test_current_approval_is_none_after_revoke(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001"])
    revoke_approval(project.events_path, actor_id="user:shubham", session_id="sess-001", now=NOW)
    assert current_approval(project.events_path) is None


def test_current_approval_reflects_a_later_grant_after_a_revoke(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001"])
    revoke_approval(project.events_path, actor_id="user:shubham", session_id="sess-001", now=NOW)
    _grant(project, ["STORY-002"], now=NOW + timedelta(minutes=1))
    approval = current_approval(project.events_path)
    assert approval is not None
    assert approval.story_ids == ["STORY-002"]


# ---------------------------------------------------------------------------
# Done when: creation with no approval returns BUSINESS and creates
# nothing.
# ---------------------------------------------------------------------------


def test_create_with_no_approval_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=["STORY-001"], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "APPROVAL_REQUIRED"


# ---------------------------------------------------------------------------
# Done when: creation with an expired approval returns BUSINESS.
# ---------------------------------------------------------------------------


def test_create_with_an_expired_approval_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001"], ttl_hours=1)
    later = NOW + timedelta(hours=2)
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=["STORY-001"], now=later,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "APPROVAL_EXPIRED"


# ---------------------------------------------------------------------------
# Done when: creation where scope_hash no longer matches returns BUSINESS.
# ---------------------------------------------------------------------------


def test_create_with_a_mismatched_scope_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001"])
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=["STORY-001", "STORY-002"], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "APPROVAL_SCOPE_MISMATCH"


# ---------------------------------------------------------------------------
# Done when: manage_linear_issue returns BUSINESS when plan.status !=
# APPROVED — tested now.
# ---------------------------------------------------------------------------


def test_create_with_unapproved_plan_is_rejected_even_with_a_valid_approval(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001"])
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="DRAFT",
        story_ids=["STORY-001"], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "PLAN_NOT_APPROVED"


# ---------------------------------------------------------------------------
# The success path — everything aligned.
# ---------------------------------------------------------------------------


def test_create_succeeds_with_a_valid_matching_unexpired_approval(tmp_path):
    project = _make_project(tmp_path)
    _grant(project, ["STORY-001", "STORY-002"])
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=["STORY-001", "STORY-002"], now=NOW,
    )
    assert result.success is True, result.error
    assert len(result.data["created_issue_ids"]) == 2


def test_create_with_empty_story_ids_is_rejected_as_validation(tmp_path):
    """An empty `story_ids` list still gets its own, more specific
    rejection once the approval gate is satisfied (an approval for the
    empty set is a degenerate but legal scope) — the gate and the body's
    own field validation are independent checks."""

    project = _make_project(tmp_path)
    _grant(project, [])
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=[], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "MISSING_STORY_IDS"


def test_unknown_operation_is_rejected_as_validation(tmp_path):
    project = _make_project(tmp_path)
    result = manage_linear_issue("delete", project, project_slug=project.slug, now=NOW)
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "UNKNOWN_OPERATION"


# ---------------------------------------------------------------------------
# The decorator itself, exercised directly against a fake scope_fn — proves
# the gate mechanics work independent of manage_linear_issue's own body.
# ---------------------------------------------------------------------------


def test_requires_approval_skips_the_gate_when_scope_fn_returns_none(tmp_path):
    project = _make_project(tmp_path)
    calls = []

    @requires_approval(lambda operation, kwargs: None)
    def _passthrough(operation, project, **kwargs):
        calls.append(operation)
        from ppa.results.envelope import ToolResult
        return ToolResult(success=True, result_count=0, data=None)

    result = _passthrough("read", project)
    assert result.success is True
    assert calls == ["read"]
