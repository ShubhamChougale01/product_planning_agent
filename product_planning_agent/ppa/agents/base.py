"""Agent protocol: grant, prompt, invoke, recover (T20, DESIGN.md §2.4,
§2.11, §2.14, S6.1).

Every agent — the Orchestrator itself, Discovery, the Planning/Delivery
stubs, and the Guidance/Research subagents — implements the same small
`Agent` protocol so the Orchestrator's own dispatch code (T21's outer loop)
never needs to special-case which concrete class it's holding.

**One spelling of each agent id, used as the grant-table key.** `ppa/agents/
registry.py::GRANTS` (T14, already shipped and tested) uses lowercase ids —
`"discovery"`, not `"DiscoveryAgent"`. This task's own pseudocode quoted
`id: str # "DiscoveryAgent"` — a stale mismatch with the already-built
grant table, corrected here rather than kept, so `grant_for(agent.id)` and
`agent.grant()` always agree. See decision #27, `blockers.md`.

`AgentResult` is the "structured `AgentResult`" §2.11's outer loop (step 8)
receives and classifies into the seven outcomes step 9 names — that
classification is `AgentResultStatus`, defined here since nothing else in
the codebase owns it yet. `RecoveryDecision` is what `Agent.recover()`
returns: §2.14's "local recovery first" — the agent's own attempt to
handle an error before the Orchestrator gets involved.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ppa.results.envelope import ErrorInfo

if TYPE_CHECKING:
    # Deferred: ppa.tools.dispatch itself imports ppa.agents.registry
    # (for grant_for), and ppa.agents.registry imports every concrete
    # Agent module, each of which imports this module — a real import
    # here (rather than a TYPE_CHECKING-only one) would be circular
    # whenever ppa.tools.dispatch happens to be the first of the two
    # modules imported in a process. `from __future__ import annotations`
    # (above) already makes every annotation in this file a lazy string,
    # so this import only ever runs for a type checker, never at runtime.
    from ppa.tools.dispatch import InvocationContext


class AgentResultStatus(str, Enum):
    """The seven outcomes DESIGN.md §2.11 (step 9) classifies every
    `AgentResult` into."""

    OK = "OK"
    PARTIAL = "PARTIAL"
    RECOVERABLE = "RECOVERABLE"
    NON_RECOVERABLE = "NON_RECOVERABLE"
    HUMAN_INPUT_REQUIRED = "HUMAN_INPUT_REQUIRED"
    WORKFLOW_TRANSITION = "WORKFLOW_TRANSITION"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class AgentResult(BaseModel):
    """What `Agent.invoke()` returns. `attempted`/`successful`/`failed`/
    `partial_results`/`next_action` exist for `status=PARTIAL`, matching
    §2.14's own worked `PARTIAL_FAILURE` JSON shape — `None` when not
    applicable, never a meaningless `0`."""

    model_config = ConfigDict(extra="forbid")

    status: AgentResultStatus
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: ErrorInfo | None = None
    attempted: int | None = None
    successful: int | None = None
    failed: int | None = None
    partial_results: list[Any] = Field(default_factory=list)
    next_action: str | None = None


class RecoveryActionKind(str, Enum):
    """What an agent's own local recovery attempt decided to do —
    distinct from `ppa.results.categories.RecoveryAction`, which is a
    *tool call's* recommended next step, not an agent's."""

    RETRY = "RETRY"
    ESCALATE = "ESCALATE"
    ABORT = "ABORT"


class RecoveryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: RecoveryActionKind
    reason: str


@runtime_checkable
class Agent(Protocol):
    """Structural protocol — any object with these three methods and an
    `id`/`system_prompt` pair satisfies it, no inheritance required."""

    id: str
    system_prompt: str

    def grant(self) -> frozenset[str]: ...

    def invoke(self, ctx: InvocationContext) -> AgentResult: ...

    def recover(self, err: ErrorInfo) -> RecoveryDecision: ...


class BaseAgent:
    """Concrete base every real agent below inherits. `grant()` reads
    straight from the one already-shipped source of truth
    (`ppa.agents.registry.GRANTS`) — never a second, hand-maintained copy
    that could drift from it."""

    id: str = ""
    system_prompt: str = ""

    def grant(self) -> frozenset[str]:
        # Deferred import: ppa.agents.registry imports every concrete Agent
        # subclass of this class, so a module-level import here would be
        # circular whenever ppa.agents.base happens to be the first of the
        # two modules imported in a process. By the time grant() is
        # actually *called* (never at import time), both modules are fully
        # loaded regardless of which one a caller imported first.
        from ppa.agents.registry import grant_for

        return grant_for(self.id)

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        raise NotImplementedError(f"{type(self).__name__}.invoke is not implemented yet")

    def recover(self, err: ErrorInfo) -> RecoveryDecision:
        return RecoveryDecision(
            action=RecoveryActionKind.ESCALATE,
            reason=f"no local recovery defined for {self.id!r}: {err.description}",
        )
