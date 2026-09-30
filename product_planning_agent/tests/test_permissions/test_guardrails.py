"""T22 — the guardrail suite. One test per row in the task's own table
(`tasks/t22_guardrail_suite.md`), each named after the rule it proves, so
this file reads as a direct trace against DESIGN.md §2.13/§2.19 rather than
requiring a reader to reconstruct which mechanism covers which rule.

Several of these rules already have their own thorough mechanism-level
tests elsewhere (`tests/test_permissions/test_approval.py` for the approval
gate, `tests/test_agents/test_loop.py` for routing back to Discovery,
`tests/test_engines/test_readiness.py` for the readiness conditions) — this
file is deliberately not a substitute for those, it is the single place a
reader can check "does every guardrail in the design doc have proof" without
already knowing which module owns which rule. No model calls anywhere in
this file; the whole suite is plain Python against already-built engines.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.engines.readiness import check_readiness
from ppa.ledger.models import Assumption, Requirement, Unknown
from ppa.ledger.project import Project
from ppa.orchestrator.preconditions import validate_discovery_state
from ppa.results.categories import ErrorCategory
from ppa.tools.approval import compute_scope_hash, grant_approval
from ppa.tools.delivery_tools import manage_linear_issue
from ppa.tools.registry import restore, snapshot
from ppa.validation import permission, workflow

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


def _make_project(tmp_path, name="Guardrail Test") -> Project:
    """A bare `Project` handle, no `git` repo — `create_project`'s own git
    init/commit dance (`ppa.ledger.gitops`) is real overhead this suite has
    no reason to pay: nothing exercised here (`manage_linear_issue`,
    `grant_approval`, `append_event`) ever touches git. DESIGN.md's own
    "under 5 seconds, no model calls" budget for this task is a plain-
    Python-only budget — subprocess-spawning `git init`/`git commit` for
    every one of this file's fixture projects would blow well past it for
    reasons that have nothing to do with what this file is actually
    proving."""

    project_dir = tmp_path / "projects" / "guardrail-test"
    return Project(
        slug="guardrail-test",
        name=name,
        profile=_profile(),
        workflow_state="DISCOVERY",
        created_at=NOW,
        path=project_dir,
    )


def _requirement(entity_id: str, *, status="CONFIRMED", covers_areas=(), **overrides) -> Requirement:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="user:shubham", updated_by="user:shubham",
        confidence="HIGH", confidence_basis="user said it directly", status=status,
        statement=f"statement for {entity_id}", type="functional", covers_areas=list(covers_areas), priority="must",
    )
    base.update(overrides)
    return Requirement(**base)


def _assumption(entity_id: str, *, status="PROPOSED", impact="HIGH", **overrides) -> Assumption:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="MEDIUM", confidence_basis="strongly implied", status=status,
        statement=f"assumption for {entity_id}", reason="inferred", impact=impact,
    )
    base.update(overrides)
    return Assumption(**base)


def _unknown(entity_id: str, *, status="OPEN", blocking=True, owner_type="user", **overrides) -> Unknown:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status=status, question=f"question for {entity_id}", area="platform", why_it_matters="it matters",
        blocking=blocking, route="USER_DECISION", owner_type=owner_type,
    )
    base.update(overrides)
    return Unknown(**base)


def _assert_names_the_rule(description: str, *expected_fragments: str) -> None:
    """"Each rejection names the rule that blocked it, not a generic
    message" — every test below calls this rather than only checking
    `success is False`, so a rejection that regressed to something generic
    like "error" or "rejected" fails here, not just silently loses detail."""

    for fragment in expected_fragments:
        assert fragment in description, f"expected {fragment!r} in rejection description: {description!r}"


# ---------------------------------------------------------------------------
# plan.status != APPROVED -> manage_linear_issue REJECT (BUSINESS)
# ---------------------------------------------------------------------------


def test_plan_not_approved_rejects_manage_linear_issue(tmp_path):
    project = _make_project(tmp_path)
    grant_approval(
        project.events_path, scope_hash=compute_scope_hash(["STORY-001"]), story_ids=["STORY-001"],
        granted_by="user:shubham", actor_id="user:shubham", session_id="sess-1", now=NOW,
    )
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="DRAFT", story_ids=["STORY-001"], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    _assert_names_the_rule(result.error.description, "plan.status", "APPROVED")


# ---------------------------------------------------------------------------
# any blocking Unknown still OPEN -> advance to PLANNING REJECT, route to
# Discovery.
# ---------------------------------------------------------------------------


def test_blocking_unknown_open_rejects_advancing_past_discovery():
    profile = _profile()
    entities = {"UNK-001": _unknown("UNK-001", status="OPEN", blocking=True, owner_type="user")}
    result = validate_discovery_state(entities, profile)
    assert result.ok is False
    assert any(b.condition == "blocking_unknown" for b in result.blockers)
    blocker = next(b for b in result.blockers if b.condition == "blocking_unknown")
    _assert_names_the_rule(blocker.description, "UNK-001", "blocking", "OPEN")


# ---------------------------------------------------------------------------
# critical assumption unconfirmed -> plan approval BLOCK.
#
# "Plan approval" is T30's own feature (not yet buildable — decision #19);
# what is real and tested today is the readiness-gate condition that will
# ultimately block it: an unconfirmed HIGH-impact assumption keeps
# check_readiness() from ever reporting READY, and READY is the gate
# review/plan-approval is built on top of.
# ---------------------------------------------------------------------------


def test_unconfirmed_high_impact_assumption_blocks_readiness():
    profile = _profile()
    entities = {"ASM-001": _assumption("ASM-001", status="PROPOSED", impact="HIGH")}
    ready, blockers = check_readiness(entities, profile, review_approved=True)
    assert ready is False
    assert any(b.condition == "unconfirmed_high_assumption" for b in blockers)
    blocker = next(b for b in blockers if b.condition == "unconfirmed_high_assumption")
    _assert_names_the_rule(blocker.description, "ASM-001", "HIGH")


# ---------------------------------------------------------------------------
# caller == DiscoveryAgent -> manage_linear_issue REJECT (PERMISSION)
# caller == DeliveryAgent  -> manage_requirement   REJECT (PERMISSION)
# caller == PlanningAgent  -> manage_linear_issue  REJECT (PERMISSION)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_id, tool_name",
    [
        ("discovery", "manage_linear_issue"),
        ("delivery", "manage_requirement"),
        ("planning", "manage_linear_issue"),
    ],
)
def test_caller_without_a_grant_is_rejected_with_permission(agent_id, tool_name):
    result = permission.check(tool_name, agent_id)
    assert result is not None
    assert result.error.category == ErrorCategory.PERMISSION
    _assert_names_the_rule(result.error.description, repr(agent_id), repr(tool_name))


# ---------------------------------------------------------------------------
# no approval / expired / stale hash -> manage_linear_issue REJECT
# (BUSINESS).
# ---------------------------------------------------------------------------


def test_no_approval_on_record_rejects_manage_linear_issue(tmp_path):
    project = _make_project(tmp_path)
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED", story_ids=["STORY-001"], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    _assert_names_the_rule(result.error.description, "no approval on record")


def test_expired_approval_rejects_manage_linear_issue(tmp_path):
    project = _make_project(tmp_path)
    grant_approval(
        project.events_path, scope_hash=compute_scope_hash(["STORY-001"]), story_ids=["STORY-001"],
        granted_by="user:shubham", actor_id="user:shubham", session_id="sess-1", now=NOW, ttl_hours=1,
    )
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED", story_ids=["STORY-001"],
        now=NOW + timedelta(hours=2),
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    _assert_names_the_rule(result.error.description, "expired")


def test_stale_scope_hash_rejects_manage_linear_issue(tmp_path):
    project = _make_project(tmp_path)
    grant_approval(
        project.events_path, scope_hash=compute_scope_hash(["STORY-001"]), story_ids=["STORY-001"],
        granted_by="user:shubham", actor_id="user:shubham", session_id="sess-1", now=NOW,
    )
    result = manage_linear_issue(
        "create", project, project_slug=project.slug, plan_status="APPROVED",
        story_ids=["STORY-001", "STORY-002"], now=NOW,
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.BUSINESS
    _assert_names_the_rule(result.error.description, "scope_hash")


# ---------------------------------------------------------------------------
# DISCOVERY state -> generate_story REJECT
# ---------------------------------------------------------------------------


def test_generate_story_is_rejected_in_discovery_state():
    result = workflow.check("generate_story", "DISCOVERY")
    assert result is not None
    assert result.error.category == ErrorCategory.BUSINESS
    _assert_names_the_rule(result.error.description, repr("generate_story"), repr("DISCOVERY"))
