"""Guidance Mode subagent — isolated context (T20 registers it; T28 builds
its real behavior).

A registered agent with its own grant (`read_planning_state`,
`manage_research` — `ppa/agents/registry.py::GRANTS["guidance"]`, T14),
not a prompt persona — DESIGN.md §2.8's own explicit reasoning for why
Guidance is a subagent, not a tool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

SYSTEM_PROMPT_PLACEHOLDER = "Guidance Mode subagent — real behavior built in T28."


class GuidanceAgent(BaseAgent):
    id = "guidance"
    system_prompt = SYSTEM_PROMPT_PLACEHOLDER

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        return AgentResult(
            status=AgentResultStatus.NOT_IMPLEMENTED,
            summary="Guidance subagent's real behavior is built in T28 — the protocol and grants are live now.",
        )
