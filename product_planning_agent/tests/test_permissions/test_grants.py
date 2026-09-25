"""Permission gate and dispatcher tests (T14). Every Done-when box in
tasks/t14_permission_gate_and_dispatcher.md maps to at least one test here.

Tests call `asyncio.run(dispatch(...))` directly rather than declaring
`async def test_...` functions — no async pytest plugin (pytest-asyncio /
pytest-anyio's marker mode) is configured in this project yet, and an
unmarked `async def` test silently never runs its body under plain pytest,
which would be a dangerous way to test a permission boundary.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ppa.agents.registry import GRANTS, grant_for
from ppa.ledger.audit import read_audit_records
from ppa.results.categories import ErrorCategory
from ppa.tools.dispatch import InvocationContext, dispatch
from ppa.tools.registry import clear_registry, register
from ppa.tools.spec import ToolSpec


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


def _spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        purpose="test tool",
        inputs={"a": "str, a field"},
        required=["a"],
        optional=[],
        formats={},
        returns="{ok: bool}",
        examples=[f"{name}(a='x')", f"{name}(a='y')"],
        edge_cases=["a is empty"],
        limitations=["test only"],
        use_when=["condition one", "condition two"],
        do_not_use_when=["condition three", "condition four"],
        related_tools={"other": "does something else"},
    )


def _ctx(agent_id: str, audit_path, **overrides) -> InvocationContext:
    base = dict(agent_id=agent_id, workflow_state="DISCOVERY", session_id="sess-001", audit_path=audit_path)
    base.update(overrides)
    return InvocationContext(**base)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Done when: a test enumerates every (agent, tool) pair against the grant
# table.
# ---------------------------------------------------------------------------


_EXPECTED_GRANTS = {
    "orchestrator": {
        "read_workflow_state", "invoke_discovery", "invoke_planning",
        "invoke_delivery", "review_subagent_result",
    },
    "discovery": {
        "read_planning_state", "manage_requirement", "manage_assumption",
        "manage_decision", "manage_unknown", "ask_user", "request_guidance",
    },
    "guidance": {"read_planning_state", "manage_research"},
    "research": {"read_planning_state", "manage_research"},
    "planning": {
        "read_planning_state", "manage_plan", "manage_milestone",
        "manage_timeline", "analyze_plan_impact",
    },
    "delivery": {
        "read_approved_plan", "generate_story", "validate_story",
        "manage_linear_issue", "read_planning_state",
    },
}


def test_grant_table_matches_the_task_exactly():
    assert {agent: set(tools) for agent, tools in GRANTS.items()} == _EXPECTED_GRANTS


@pytest.mark.parametrize(
    "agent_id,tool_name,expected",
    [
        (agent, tool, tool in tools)
        for agent, tools in _EXPECTED_GRANTS.items()
        for tool in sorted({t for row in _EXPECTED_GRANTS.values() for t in row})
    ],
)
def test_every_agent_tool_pair_matches_the_grant_table(agent_id, tool_name, expected):
    assert (tool_name in grant_for(agent_id)) is expected


def test_unknown_agent_id_has_no_grants():
    assert grant_for("nonexistent_agent") == frozenset()


# ---------------------------------------------------------------------------
# Done when: Discovery calling manage_linear_issue returns PERMISSION and
# the handler body never runs — assert with a spy.
# ---------------------------------------------------------------------------


def test_discovery_calling_manage_linear_issue_returns_permission_without_running_handler(tmp_path):
    spy_calls = []

    async def spy_handler(args):
        spy_calls.append(args)
        return {"content": []}

    register(_spec("manage_linear_issue"), spy_handler, owner_agents=["delivery"])

    ctx = _ctx("discovery", tmp_path / "audit.ndjson")
    result = _run(dispatch("manage_linear_issue", {"a": "x"}, ctx))

    assert result.success is False
    assert result.error.category == ErrorCategory.PERMISSION
    assert spy_calls == []


# ---------------------------------------------------------------------------
# Done when: Delivery calling manage_requirement returns PERMISSION.
# ---------------------------------------------------------------------------


def test_delivery_calling_manage_requirement_returns_permission(tmp_path):
    ctx = _ctx("delivery", tmp_path / "audit.ndjson")
    result = _run(dispatch("manage_requirement", {"a": "x"}, ctx))

    assert result.success is False
    assert result.error.category == ErrorCategory.PERMISSION


# ---------------------------------------------------------------------------
# Done when: caller identity cannot be influenced by tool arguments — test
# with a hostile agent_id in args.
# ---------------------------------------------------------------------------


def test_hostile_agent_id_in_args_does_not_grant_extra_permission(tmp_path):
    ctx = _ctx("discovery", tmp_path / "audit.ndjson")
    hostile_args = {"agent_id": "orchestrator", "a": "x"}

    result = _run(dispatch("manage_linear_issue", hostile_args, ctx))

    assert result.success is False
    assert result.error.category == ErrorCategory.PERMISSION


# ---------------------------------------------------------------------------
# Done when: permission is checked before schema validation — a malformed
# call from an ungranted agent yields PERMISSION, not VALIDATION.
# ---------------------------------------------------------------------------


def test_malformed_call_from_ungranted_agent_still_yields_permission(tmp_path):
    ctx = _ctx("discovery", tmp_path / "audit.ndjson")
    malformed_args = {"totally": "wrong", "shape": [1, 2, 3], "nested": {"a": {"b": None}}}

    result = _run(dispatch("manage_linear_issue", malformed_args, ctx))

    assert result.success is False
    assert result.error.category == ErrorCategory.PERMISSION
    assert result.error.category != ErrorCategory.VALIDATION


# ---------------------------------------------------------------------------
# Done when: every rejection appears in the audit log.
# ---------------------------------------------------------------------------


def test_every_rejection_appears_in_the_audit_log(tmp_path):
    audit_path = tmp_path / "audit.ndjson"
    ctx = _ctx("discovery", audit_path)

    _run(dispatch("manage_linear_issue", {"a": "x"}, ctx))

    records = read_audit_records(audit_path)
    assert len(records) == 1
    assert records[0].tool == "manage_linear_issue"
    assert records[0].agent == "discovery"
    assert records[0].operation == "reject"
    assert records[0].result.success is False
    assert records[0].result.category == ErrorCategory.PERMISSION

    raw_text = audit_path.read_text(encoding="utf-8")
    assert "manage_linear_issue" in raw_text


def test_granted_but_unregistered_tool_returns_not_implemented_not_permission(tmp_path):
    ctx = _ctx("discovery", tmp_path / "audit.ndjson")
    # "ask_user" is granted to discovery in the table but no handler is
    # registered in this test's clean registry.
    result = _run(dispatch("ask_user", {"a": "x"}, ctx))

    assert result.success is False
    assert result.error.category == ErrorCategory.NOT_IMPLEMENTED


def test_granted_and_registered_tool_executes_and_is_audited(tmp_path):
    calls = []

    async def handler(args):
        calls.append(args)
        return {"content": [{"type": "text", "text": "ok"}]}

    register(_spec("ask_user"), handler, owner_agents=["discovery"])

    audit_path = tmp_path / "audit.ndjson"
    ctx = _ctx("discovery", audit_path)
    result = _run(dispatch("ask_user", {"a": "x"}, ctx))

    assert result.success is True
    assert calls == [{"a": "x"}]

    records = read_audit_records(audit_path)
    assert len(records) == 1
    assert records[0].result.success is True
    assert records[0].operation == "write"


def test_read_prefixed_tool_is_audited_as_a_read(tmp_path):
    async def handler(args):
        return {"content": []}

    register(_spec("read_planning_state"), handler, owner_agents=["discovery"])

    audit_path = tmp_path / "audit.ndjson"
    ctx = _ctx("discovery", audit_path)
    _run(dispatch("read_planning_state", {"a": "x"}, ctx))

    records = read_audit_records(audit_path)
    assert records[0].operation == "read"
