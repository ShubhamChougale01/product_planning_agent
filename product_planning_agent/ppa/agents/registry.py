"""Agent -> tool grant table (DESIGN.md §2.8, §2.10, S5.2).

Static, declared data — deliberately **not** derived from
`ppa/tools/registry.py`'s dynamic tool registrations. A tool can be
*granted* here before it is ever *registered* (implemented) there: the
dispatcher (`ppa/tools/dispatch.py`) treats a granted-but-unregistered tool
as `NOT_IMPLEMENTED`, distinct from `PERMISSION` — the caller was allowed to
ask, the tool just doesn't exist yet.

Agent ids here are lowercase and match `ppa/agents/`'s own module names
(`discovery.py`, `planning.py`, `delivery.py`, `subagents/guidance.py`,
`subagents/research.py`) plus `"orchestrator"` — a convention this module
establishes since nothing else in the codebase had fixed one yet.

T14 is the first task to fill this file in. An earlier scaffold comment
(T01) said T20 would — T20 only *extends* it once the full Agent protocol
lands (see its own task file's "Files touched": `ppa/agents/registry.py
(extend)`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

GRANTS: dict[str, frozenset[str]] = {
    "orchestrator": frozenset(
        {
            "read_workflow_state",
            "invoke_discovery",
            "invoke_planning",
            "invoke_delivery",
            "review_subagent_result",
        }
    ),
    "discovery": frozenset(
        {
            "read_planning_state",
            "manage_requirement",
            "manage_assumption",
            "manage_decision",
            "manage_unknown",
            "ask_user",
            "request_guidance",
        }
    ),
    "guidance": frozenset({"read_planning_state", "manage_research"}),
    "research": frozenset({"read_planning_state", "manage_research"}),
    "planning": frozenset(
        {
            "read_planning_state",
            "manage_plan",
            "manage_milestone",
            "manage_timeline",
            "analyze_plan_impact",
        }
    ),
    "delivery": frozenset(
        {
            "read_approved_plan",
            "generate_story",
            "validate_story",
            "manage_linear_issue",
            "read_planning_state",
        }
    ),
}
"""The Research subagent's row in the task's own grant table also names
"(+ web search)" — that is `ResearchProvider` capability (T29), not a
dispatcher-gated tool, so it has no entry here."""


def grant_for(agent_id: str) -> frozenset[str]:
    """Every tool `agent_id` may call. An unknown `agent_id` gets an empty
    grant — fail closed, never fail open on a typo."""

    return GRANTS.get(agent_id, frozenset())


# ---------------------------------------------------------------------------
# Agent instances (T20, DESIGN.md §2.4, S6.1) — extends this module rather
# than adding a new file, since the six ids below are exactly this file's
# own GRANTS keys and belong right next to them.
#
# Imported at the bottom, after GRANTS/grant_for are already defined: each
# concrete agent module imports `ppa.agents.base.BaseAgent`, whose own
# `grant()` calls back into `grant_for` here. Importing the concrete agent
# classes only after this module's own names exist keeps that circular
# import resolvable — Python hands back this (by-then-partially-loaded)
# module, and `grant_for` is already on it.
# ---------------------------------------------------------------------------

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent  # noqa: E402
from ppa.agents.delivery import DeliveryAgent  # noqa: E402
from ppa.agents.discovery import DiscoveryAgent  # noqa: E402
from ppa.agents.planning import PlanningAgent  # noqa: E402
from ppa.agents.subagents.guidance import GuidanceAgent  # noqa: E402
from ppa.agents.subagents.research import ResearchAgent  # noqa: E402

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext


class OrchestratorAgent(BaseAgent):
    """No dedicated file — the Orchestrator is the thing that invokes the
    other five agents (T21's outer loop), not itself invoked the same way.
    Registered here purely so it has an `id`/`grant()` like everything
    else in `AGENTS`, for the "all six agents/subagents register and
    declare grants" guarantee this task requires."""

    id = "orchestrator"
    system_prompt = "Orchestrator — coordinates the other five agents; built out in T21."

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        return AgentResult(
            status=AgentResultStatus.NOT_IMPLEMENTED,
            summary="The Orchestrator's own outer loop is built in T21 — the protocol and grants are live now.",
        )


AGENTS: dict[str, BaseAgent] = {
    "orchestrator": OrchestratorAgent(),
    "discovery": DiscoveryAgent(),
    "planning": PlanningAgent(),
    "delivery": DeliveryAgent(),
    "guidance": GuidanceAgent(),
    "research": ResearchAgent(),
}
"""One instance per id in `GRANTS` — `set(AGENTS) == set(GRANTS)` is a
tested invariant (`tests/test_agents/test_registry.py`), the concrete
"one spelling of each agent id everywhere" proof this task requires."""


def agent_for(agent_id: str) -> BaseAgent:
    """The registered `Agent` for `agent_id`. Raises `KeyError` for an
    unknown id — unlike `grant_for`'s fail-closed empty set, there is no
    sensible "default agent," so a typo here is a bug to surface loudly,
    not to paper over."""

    return AGENTS[agent_id]
