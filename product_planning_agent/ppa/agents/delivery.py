"""Delivery Agent — declared for v3, stubbed in v1 (T20, DESIGN.md §2.1,
§2.5, S6.1).

Same shape as `ppa/agents/planning.py` — real grants
(`ppa/agents/registry.py::GRANTS["delivery"]`, T14), real `Agent`
implementation, `invoke()` always returns a structured `NOT_IMPLEMENTED`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

STUB_MESSAGE = "Delivery is v3. Planning must be approved before delivery tools do anything."


class DeliveryAgent(BaseAgent):
    id = "delivery"
    system_prompt = STUB_MESSAGE

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        return AgentResult(status=AgentResultStatus.NOT_IMPLEMENTED, summary=STUB_MESSAGE)
