"""Tool registry tests (T13). Every Done-when box in
tasks/t13_toolspec_contract_and_registry.md that concerns
`ppa/tools/registry.py` maps to at least one test here.
"""

from __future__ import annotations

import pytest

from ppa.tools.registry import clear_registry, get, register, tools_for_agent
from ppa.tools.spec import ToolSpec


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


async def _noop_handler(args: dict) -> dict:
    return {"content": [{"type": "text", "text": "ok"}]}


def _full_spec(**overrides) -> ToolSpec:
    base = dict(
        name="do_thing",
        purpose="Does the thing.",
        inputs={"a": "str, a field"},
        required=["a"],
        optional=[],
        formats={},
        returns="{ok: bool}",
        examples=["do_thing(a='x')", "do_thing(a='y')"],
        edge_cases=["a is empty"],
        limitations=["cannot undo"],
        use_when=["condition one", "condition two"],
        do_not_use_when=["condition three", "condition four"],
        related_tools={"other_thing": "does something else entirely"},
    )
    base.update(overrides)
    return ToolSpec(**base)


# ---------------------------------------------------------------------------
# Done when: a test asserts every registered tool populates all thirteen
# fields (use_when/do_not_use_when/examples each >= 2).
# ---------------------------------------------------------------------------


def test_full_spec_registers_successfully():
    registered = register(_full_spec(), _noop_handler, owner_agents=["discovery"])
    assert get("do_thing") is registered


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"purpose": ""},
        {"returns": ""},
        {"examples": ["only one"]},
        {"use_when": ["only one"]},
        {"do_not_use_when": ["only one"]},
        {"edge_cases": []},
        {"limitations": []},
        {"related_tools": {}},
        {"required": [], "optional": []},  # "a" is an input but neither required nor optional
        {"formats": {"unknown_field": "^x$"}},
    ],
)
def test_incomplete_spec_raises_at_registration(overrides):
    with pytest.raises(ValueError):
        register(_full_spec(**overrides), _noop_handler, owner_agents=["discovery"])


def test_required_and_optional_cannot_overlap():
    with pytest.raises(ValueError):
        register(
            _full_spec(required=["a"], optional=["a"]),
            _noop_handler,
            owner_agents=["discovery"],
        )


def test_owner_agents_must_be_non_empty():
    with pytest.raises(ValueError):
        register(_full_spec(), _noop_handler, owner_agents=[])


def test_duplicate_name_raises():
    register(_full_spec(), _noop_handler, owner_agents=["discovery"])
    with pytest.raises(ValueError):
        register(_full_spec(), _noop_handler, owner_agents=["planning"])


# ---------------------------------------------------------------------------
# Done when: related_tools names how each competing tool differs, not just
# that it exists (structurally, related_tools is dict[str, str], so an
# entry without a distinction string is impossible to construct at all).
# ---------------------------------------------------------------------------


def test_related_tools_values_are_the_distinction_text():
    register(_full_spec(), _noop_handler, owner_agents=["discovery"])
    registered = get("do_thing")
    assert registered.spec.related_tools["other_thing"] == "does something else entirely"


# ---------------------------------------------------------------------------
# `allowed_tools` is derived from the grant table (Done-when, checked again
# in test_server.py via server_for/allowed_tool_names).
# ---------------------------------------------------------------------------


def test_tools_for_agent_returns_only_granted_tools():
    register(_full_spec(name="discovery_only"), _noop_handler, owner_agents=["discovery"])
    register(_full_spec(name="shared_tool"), _noop_handler, owner_agents=["discovery", "planning"])

    discovery_tools = {t.spec.name for t in tools_for_agent("discovery")}
    planning_tools = {t.spec.name for t in tools_for_agent("planning")}

    assert discovery_tools == {"discovery_only", "shared_tool"}
    assert planning_tools == {"shared_tool"}
