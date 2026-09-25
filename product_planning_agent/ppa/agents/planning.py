"""Planning Agent — declared for v2, stubbed in v1 (T20, DESIGN.md §2.1,
§2.5, S6.1).

Registered with real grants (`ppa/agents/registry.py::GRANTS["planning"]`,
already shipped by T14) and a real `Agent` implementation whose `invoke()`
always returns a structured `NOT_IMPLEMENTED` — the boundary is built now,
the feature lands in v2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

STUB_MESSAGE = "Planning is v2. Discovery is validated and the ledger is ready for it."


class PlanningAgent(BaseAgent):
    id = "planning"
    system_prompt = STUB_MESSAGE

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        return AgentResult(status=AgentResultStatus.NOT_IMPLEMENTED, summary=STUB_MESSAGE)
