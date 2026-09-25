"""Discovery Agent — the v1 intelligence layer.

Registered here as a real `Agent` (T20) so the protocol, the grant table
and the workflow machine are all provable before a single agent prompt
exists — T23 builds the real system prompt and turn behavior; `invoke()`
below is a placeholder that says exactly that, not a silent `pass`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

SYSTEM_PROMPT_PLACEHOLDER = "Discovery Agent — real system prompt built in T23."


class DiscoveryAgent(BaseAgent):
    id = "discovery"
    system_prompt = SYSTEM_PROMPT_PLACEHOLDER

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        return AgentResult(
            status=AgentResultStatus.NOT_IMPLEMENTED,
            summary="Discovery Agent's real turn behavior is built in T23 — the protocol and grants are live now.",
        )
