"""Agent protocol and registry tests (T20). Every Done-when box in
`tasks/t20_agent_protocol_and_workflow.md` maps to at least one test here
(the transition-machine boxes live in `tests/test_agents/test_transitions.py`).
"""

from __future__ import annotations

import pathlib
import re

import ppa.agents
from ppa.agents.base import Agent, AgentResultStatus
from ppa.agents.registry import AGENTS, GRANTS, agent_for, grant_for
from ppa.tools.dispatch import InvocationContext

_ALL_AGENT_IDS = {"orchestrator", "discovery", "planning", "delivery", "guidance", "research"}


def _ctx(agent_id: str, tmp_path) -> InvocationContext:
    return InvocationContext(
        agent_id=agent_id, workflow_state="DISCOVERY", session_id="sess-001",
        audit_path=tmp_path / "audit.ndjson",
    )


# ---------------------------------------------------------------------------
# Done when: all six agents/subagents register and declare grants.
# ---------------------------------------------------------------------------


def test_all_six_agents_are_registered():
    assert set(AGENTS) == _ALL_AGENT_IDS
    assert set(GRANTS) == _ALL_AGENT_IDS


def test_every_registered_agent_declares_the_grant_table_matches():
    for agent_id, agent in AGENTS.items():
        assert agent.grant() == grant_for(agent_id)
        assert agent.grant() == GRANTS[agent_id]


def test_every_registered_agent_satisfies_the_protocol():
    for agent in AGENTS.values():
        assert isinstance(agent, Agent)


def test_agent_for_unknown_id_raises_key_error():
    import pytest

    with pytest.raises(KeyError):
        agent_for("not_a_real_agent")


# ---------------------------------------------------------------------------
# Done when: agent ids use one spelling throughout — grep for variants and
# assert.
# ---------------------------------------------------------------------------


def test_agent_id_attribute_matches_its_own_registry_key():
    for agent_id, agent in AGENTS.items():
        assert agent.id == agent_id


def test_source_files_declare_exactly_the_registry_ids_no_variants():
    """Greps every concrete agent module's own `id = "..."` class attribute
    and checks the set found matches `GRANTS` exactly — catches a stray
    `"DiscoveryAgent"`-shaped id (this task's own original pseudocode
    typo, decision #27) before it ever reaches a grant check at runtime."""

    agents_dir = pathlib.Path(ppa.agents.__file__).parent
    pattern = re.compile(r'^\s*id\s*=\s*"([^"]+)"', re.MULTILINE)
    found: set[str] = set()
    for path in agents_dir.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    assert found == _ALL_AGENT_IDS


# ---------------------------------------------------------------------------
# Done when: Planning and Delivery stubs return structured NOT_IMPLEMENTED.
# ---------------------------------------------------------------------------


def test_planning_agent_invoke_returns_structured_not_implemented(tmp_path):
    result = AGENTS["planning"].invoke(_ctx("planning", tmp_path))
    assert result.status == AgentResultStatus.NOT_IMPLEMENTED
    assert "Planning is v2" in result.summary


def test_delivery_agent_invoke_returns_structured_not_implemented(tmp_path):
    result = AGENTS["delivery"].invoke(_ctx("delivery", tmp_path))
    assert result.status == AgentResultStatus.NOT_IMPLEMENTED
    assert "Delivery is v3" in result.summary


def test_discovery_guidance_research_invoke_also_return_structured_not_implemented(tmp_path):
    """Real turn behavior lands in T23/T28/T29 — until then, every agent
    (not just the v2/v3 stubs) returns a structured result, never raises."""

    for agent_id in ("discovery", "guidance", "research"):
        result = AGENTS[agent_id].invoke(_ctx(agent_id, tmp_path))
        assert result.status == AgentResultStatus.NOT_IMPLEMENTED
        assert result.summary.strip()


def test_orchestrator_invoke_returns_structured_not_implemented(tmp_path):
    result = AGENTS["orchestrator"].invoke(_ctx("orchestrator", tmp_path))
    assert result.status == AgentResultStatus.NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# recover() — the default local-recovery behavior every BaseAgent gets.
# ---------------------------------------------------------------------------


def test_base_agent_recover_escalates_by_default():
    from ppa.agents.base import RecoveryActionKind
    from ppa.results.categories import ErrorCategory, RecoveryAction
    from ppa.results.envelope import ErrorInfo

    err = ErrorInfo(
        category=ErrorCategory.TRANSIENT, code="X", is_retryable=True,
        recommended_action=RecoveryAction.RETRY_SAME, description="something went wrong",
    )
    decision = AGENTS["discovery"].recover(err)
    assert decision.action == RecoveryActionKind.ESCALATE
    assert "discovery" in decision.reason
