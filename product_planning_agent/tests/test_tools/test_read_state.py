"""`read_planning_state` tests (T15). Every Done-when box in
tasks/t15_read_planning_state_tool.md maps to at least one test here.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.ledger.store import append_event_with_id
from ppa.results.categories import ErrorCategory
from ppa.tools.discovery_tools import (
    READ_PLANNING_STATE_SPEC,
    _read_planning_state_handler,
    read_planning_state,
)
from ppa.tools.registry import get, restore, snapshot

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


def _make_project(tmp_path, name="Read State Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _event_fields(**overrides) -> dict:
    base = dict(
        ts=NOW,
        type="requirement.created",
        entity_id=None,
        actor_id="user:shubham",
        actor_role="user",
        agent_name=None,
        workflow_state="DISCOVERY",
        txn_id=None,
        source="intake",
        reason="test fixture event",
        before=None,
        after=None,
        session_id="sess-001",
    )
    base.update(overrides)
    return base


def _requirement_after(**overrides) -> dict:
    base = dict(
        id="PENDING",
        version=1,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        confidence="HIGH",
        confidence_basis="user said it directly",
        status="PROPOSED",
        statement="A requirement",
        type="functional",
        covers_areas=["problem"],
        derived_from_answers=[],
        depends_on_assumptions=[],
        depends_on_decisions=[],
        priority="must",
        needs_user_confirmation=False,
        custom_fields={},
    )
    base.update(overrides)
    return base


def _add_requirement(project, **overrides) -> str:
    result = append_event_with_id(
        _event_fields(after=_requirement_after(**overrides)), project.events_path, id_prefix="REQ"
    )
    return result.entity_id


# ---------------------------------------------------------------------------
# Done when: all seven scopes return well-formed ToolResult objects.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope,kwargs",
    [
        ("digest", {}),
        ("entity", {"entity_type": "requirement"}),
        ("coverage", {}),
        ("open_items", {}),
        ("readiness", {}),
    ],
)
def test_scope_returns_a_well_formed_tool_result(tmp_path, scope, kwargs):
    project = _make_project(tmp_path)
    _add_requirement(project)
    result = read_planning_state(scope, project, **kwargs)
    assert result.success is True
    assert result.data is not None


def test_history_scope_returns_a_well_formed_tool_result(tmp_path):
    project = _make_project(tmp_path)
    req_id = _add_requirement(project)
    result = read_planning_state("history", project, entity_id=req_id)
    assert result.success is True
    assert isinstance(result.data, list)


def test_impact_scope_returns_a_well_formed_tool_result(tmp_path):
    project = _make_project(tmp_path)
    req_id = _add_requirement(project)
    result = read_planning_state("impact", project, entity_id=req_id)
    assert result.success is True
    assert "affected" in result.data


def test_unknown_scope_is_rejected():
    class _FakeProject:
        events_path = None

    # entities aren't even read for an unknown scope, so a None events_path
    # is safe here — this test is purely about the routing guard.
    result = read_planning_state("not_a_real_scope", _FakeProject())
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


# ---------------------------------------------------------------------------
# Done when: scope="entity" without a filter is rejected as VALIDATION.
# ---------------------------------------------------------------------------


def test_entity_scope_without_any_filter_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = read_planning_state("entity", project)
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


def test_entity_scope_with_entity_id_filter_succeeds(tmp_path):
    project = _make_project(tmp_path)
    req_id = _add_requirement(project)
    result = read_planning_state("entity", project, entity_id=req_id)
    assert result.success is True
    assert result.result_count == 1


def test_history_scope_without_entity_id_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = read_planning_state("history", project)
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


def test_impact_scope_without_entity_id_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = read_planning_state("impact", project)
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


# ---------------------------------------------------------------------------
# Done when: no scope can return the entire ledger — verify with a
# 200-entity fixture.
# ---------------------------------------------------------------------------


def test_entity_scope_never_returns_more_than_the_cap_on_a_200_entity_ledger(tmp_path):
    project = _make_project(tmp_path)
    for i in range(200):
        _add_requirement(project, statement=f"Requirement {i}")

    entities = current_entities(project.events_path)
    assert len(entities) == 200

    result = read_planning_state("entity", project, entity_type="requirement")
    assert result.success is True
    assert result.result_count <= 20
    assert result.degraded is True


def test_entity_scope_ignores_a_limit_above_the_cap(tmp_path):
    project = _make_project(tmp_path)
    for i in range(30):
        _add_requirement(project, statement=f"Requirement {i}")

    result = read_planning_state("entity", project, entity_type="requirement", limit=1000)
    assert result.result_count <= 20


def test_digest_scope_stays_small_on_a_200_entity_ledger(tmp_path):
    project = _make_project(tmp_path)
    for i in range(200):
        _add_requirement(project, statement=f"Requirement {i}")

    result = read_planning_state("digest", project)
    assert result.success is True
    # A digest is bounded by design (T09) — it must not just dump 200
    # entities verbatim into `data`.
    assert len(result.data["digest"]) < 20_000


# ---------------------------------------------------------------------------
# Done when: each scope delegates to its engine; the tool body is under 20
# lines per scope.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func_name",
    [
        "_digest_scope", "_entity_scope", "_history_scope", "_coverage_scope",
        "_open_items_scope", "_readiness_scope", "_impact_scope",
    ],
)
def test_each_scope_handler_body_is_under_20_lines(func_name):
    import ppa.tools.discovery_tools as module

    func = getattr(module, func_name)
    source_lines = inspect.getsource(func).splitlines()
    # Exclude the def line itself and the blank/docstring-free body only —
    # a generous, honest count of the actual function body.
    body_lines = [line for line in source_lines[1:] if line.strip()]
    assert len(body_lines) < 20, f"{func_name} has {len(body_lines)} body lines"


# ---------------------------------------------------------------------------
# Done when: readiness returns blockers, not just a boolean.
# ---------------------------------------------------------------------------


def test_readiness_scope_returns_blockers_not_just_a_boolean(tmp_path):
    project = _make_project(tmp_path)
    result = read_planning_state("readiness", project)
    assert result.success is True
    assert "ready" in result.data
    assert "blockers" in result.data
    assert isinstance(result.data["blockers"], list)
    assert len(result.data["blockers"]) > 0  # nothing is confirmed yet in a fresh project


# ---------------------------------------------------------------------------
# Done when: the ToolSpec has all thirteen fields and distinguishes itself
# from the write tools.
# ---------------------------------------------------------------------------


def test_toolspec_is_registered_and_complete():
    registered = get("read_planning_state")
    assert registered.spec is READ_PLANNING_STATE_SPEC
    assert len(registered.spec.examples) >= 2
    assert len(registered.spec.use_when) >= 2
    assert len(registered.spec.do_not_use_when) >= 2


def test_toolspec_related_tools_distinguishes_from_write_tools():
    spec = READ_PLANNING_STATE_SPEC
    assert "manage_requirement" in spec.related_tools
    assert "never writes" in spec.related_tools["manage_requirement"]


# ---------------------------------------------------------------------------
# The SDK-facing handler resolves a project from project_slug and delegates.
# ---------------------------------------------------------------------------


def test_sdk_handler_resolves_project_and_delegates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project = _make_project(tmp_path)
    _add_requirement(project)

    response = asyncio.run(
        _read_planning_state_handler(
            {"scope": "digest", "project_slug": project.slug, "projects_root": tmp_path / "projects"}
        )
    )
    assert response["is_error"] is False
    assert "digest" in response["content"][0]["text"]


def test_sdk_handler_rejects_missing_project_slug():
    response = asyncio.run(_read_planning_state_handler({"scope": "digest"}))
    assert response["is_error"] is True
