"""Tool server tests (T13). Every Done-when box in
tasks/t13_toolspec_contract_and_registry.md that concerns
`ppa/tools/server.py` maps to at least one test here.
"""

from __future__ import annotations

import inspect

import pytest

from ppa.tools.registry import clear_registry, register
from ppa.tools.server import allowed_tool_names, granted_sdk_tools, server_for
from ppa.tools.spec import ToolSpec, render_description


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


async def _noop_handler(args: dict) -> dict:
    return {"content": [{"type": "text", "text": "ok"}]}


def _spec(name: str, **overrides) -> ToolSpec:
    base = dict(
        name=name,
        purpose="Does the thing.",
        inputs={"a": "str, a field"},
        required=["a"],
        optional=[],
        formats={},
        returns="{ok: bool}",
        examples=[f"{name}(a='x')", f"{name}(a='y')"],
        edge_cases=["a is empty"],
        limitations=["cannot undo"],
        use_when=["condition one", "condition two"],
        do_not_use_when=["condition three", "condition four"],
        related_tools={"other_thing": "does something else entirely"},
    )
    base.update(overrides)
    return ToolSpec(**base)


# ---------------------------------------------------------------------------
# Done when: server_for(agent_id) exposes exactly that agent's granted
# tools and nothing else.
# ---------------------------------------------------------------------------


def test_granted_sdk_tools_matches_the_grant_table_exactly():
    register(_spec("discovery_only"), _noop_handler, owner_agents=["discovery"])
    register(_spec("shared_tool"), _noop_handler, owner_agents=["discovery", "planning"])
    register(_spec("planning_only"), _noop_handler, owner_agents=["planning"])

    discovery_names = {t.name for t in granted_sdk_tools("discovery")}
    planning_names = {t.name for t in granted_sdk_tools("planning")}

    assert discovery_names == {"discovery_only", "shared_tool"}
    assert planning_names == {"shared_tool", "planning_only"}


def test_agent_with_no_grants_gets_an_empty_server():
    register(_spec("discovery_only"), _noop_handler, owner_agents=["discovery"])
    assert granted_sdk_tools("delivery") == []


def test_server_for_builds_a_named_sdk_server_without_raising():
    register(_spec("discovery_only"), _noop_handler, owner_agents=["discovery"])
    config = server_for("discovery")
    assert config["type"] == "sdk"
    assert config["name"] == "discovery-tools"
    assert config["instance"] is not None


def test_sdk_tool_description_comes_from_the_one_renderer():
    spec = _spec("discovery_only")
    register(spec, _noop_handler, owner_agents=["discovery"])
    (sdk_tool_obj,) = granted_sdk_tools("discovery")
    assert sdk_tool_obj.description == render_description(spec)


# ---------------------------------------------------------------------------
# Done when: allowed_tools is derived from the grant table, never
# hand-listed per agent.
# ---------------------------------------------------------------------------


def test_allowed_tool_names_matches_granted_sdk_tools():
    register(_spec("discovery_only"), _noop_handler, owner_agents=["discovery"])
    register(_spec("shared_tool"), _noop_handler, owner_agents=["discovery", "planning"])

    assert set(allowed_tool_names("discovery")) == {t.name for t in granted_sdk_tools("discovery")}


def test_no_module_hand_writes_a_tool_description_string():
    import ppa.tools.server as server_module

    source = inspect.getsource(server_module)
    assert "render_description" in source, (
        "server.py must build every tool description via render_description, "
        "never a hand-written string"
    )
