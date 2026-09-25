"""Research Mode subagent — isolated context (T20 registers it; T29 builds
its real behavior).

A registered agent with its own grant (`read_planning_state`,
`manage_research` plus web search — `ppa/agents/registry.py::GRANTS
["research"]`, T14), not a prompt persona.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

SYSTEM_PROMPT_PLACEHOLDER = "Research Mode subagent — real behavior built in T29."


class ResearchAgent(BaseAgent):
    id = "research"
    system_prompt = SYSTEM_PROMPT_PLACEHOLDER

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        return AgentResult(
            status=AgentResultStatus.NOT_IMPLEMENTED,
            summary="Research subagent's real behavior is built in T29 — the protocol and grants are live now.",
        )
