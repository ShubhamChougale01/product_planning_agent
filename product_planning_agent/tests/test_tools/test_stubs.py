"""Planning/Delivery stub tool tests (T18). Every Done-when box in
`tasks/t18_stub_tools_and_approval_gate.md` maps to at least one test here
(the approval-gate boxes live in `tests/test_permissions/test_approval.py`).
"""

from __future__ import annotations

import pytest

import ppa.tools.discovery_tools  # noqa: F401 -- registers read_planning_state, shared by planning/delivery
from ppa.agents.registry import GRANTS
from ppa.config.profiles import UserProfile
from ppa.ledger.project import create_project
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.tools.delivery_tools import generate_story, read_approved_plan, validate_story
from ppa.tools.planning_tools import analyze_plan_impact, manage_milestone, manage_plan, manage_timeline
from ppa.tools.registry import get, restore, snapshot


@pytest.fixture(autouse=True)
def _preserve_registry():
    saved = snapshot()
    yield
    restore(saved)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Stub Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


# ---------------------------------------------------------------------------
# Done when: all ten stub tools are registered with complete ToolSpecs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_id", ["planning", "delivery"])
def test_every_granted_tool_is_registered_with_a_complete_spec(agent_id):
    for tool_name in GRANTS[agent_id]:
        registered = get(tool_name)
        assert registered.spec.name == tool_name
        assert registered.spec.purpose.strip()
        assert registered.spec.returns.strip()
        assert len(registered.spec.examples) >= 2
        assert len(registered.spec.use_when) >= 2
        assert len(registered.spec.do_not_use_when) >= 2
        assert registered.spec.edge_cases
        assert registered.spec.limitations
        assert registered.spec.related_tools
        assert agent_id in registered.owner_agents


def test_grant_tables_name_exactly_ten_tool_slots():
    assert len(GRANTS["planning"]) == 5
    assert len(GRANTS["delivery"]) == 5


# ---------------------------------------------------------------------------
# Done when: stubs return NOT_IMPLEMENTED with INFORM_USER, not an
# exception.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func",
    [manage_plan, manage_milestone, manage_timeline],
)
def test_planning_operation_stubs_return_not_implemented(tmp_path, func):
    project = _make_project(tmp_path)
    result = func("create", project, project_slug=project.slug)
    assert result.success is False
    assert result.error.category == ErrorCategory.NOT_IMPLEMENTED
    assert result.error.recommended_action == RecoveryAction.INFORM_USER
    assert "Planning is v2" in result.error.description


def test_analyze_plan_impact_stub_returns_not_implemented(tmp_path):
    project = _make_project(tmp_path)
    result = analyze_plan_impact(project, project_slug=project.slug)
    assert result.success is False
    assert result.error.category == ErrorCategory.NOT_IMPLEMENTED
    assert result.error.recommended_action == RecoveryAction.INFORM_USER


@pytest.mark.parametrize(
    "func",
    [read_approved_plan, generate_story, validate_story],
)
def test_delivery_stubs_return_not_implemented(tmp_path, func):
    project = _make_project(tmp_path)
    result = func(project, project_slug=project.slug)
    assert result.success is False
    assert result.error.category == ErrorCategory.NOT_IMPLEMENTED
    assert result.error.recommended_action == RecoveryAction.INFORM_USER
    assert "Delivery is v3" in result.error.description


def test_stub_never_raises_regardless_of_garbage_input(tmp_path):
    project = _make_project(tmp_path)
    result = manage_plan("anything_at_all", project, whatever=123, nested={"a": [1, 2, 3]})
    assert result.success is False
    assert result.error.category == ErrorCategory.NOT_IMPLEMENTED
