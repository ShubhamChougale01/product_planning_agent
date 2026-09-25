"""Agent selection and invocation (T21, DESIGN.md §2.4, §2.11 steps 5-8).

Step 5 of the outer loop ("select agent from workflow state — table lookup")
and step 7 ("invoke agent — inner loop, SDK-managed") live here, kept
separate from `ppa/orchestrator/loop.py`'s own step 1-4/9-11 bookkeeping so
the "which agent handles this state" table reads as data, the same
"no workflow rule is ever encoded as an if/elif chain" discipline
`ppa/workflow/machine.py` already applies to state *transitions*.

**Only the two states v1 actually walks are wired** (DESIGN.md §2.5: "v1
runs the global machine from DISCOVERY to DISCOVERY_VALIDATED and stops
there"). `PLAN_REVIEW`/`PLAN_APPROVED`/`DELIVERY`/`COMPLETE`/
`CHANGE_REQUESTED` are real states in `ppa/workflow/transitions.yaml` (so the
machine itself is provably correct end to end), but no task before T30
produces the events that would ever move a session into them — inventing an
agent mapping for states nothing can reach yet is unrequested design, not
diligence. `select_agent` raises plainly for any of them, naming exactly
that, rather than silently guessing a mapping. See decision #28,
`blockers.md`.
"""

from __future__ import annotations

from ppa.agents.base import Agent, AgentResult
from ppa.agents.registry import agent_for
from ppa.tools.dispatch import InvocationContext

STATE_AGENT: dict[str, str] = {
    "DISCOVERY": "discovery",
    "DISCOVERY_VALIDATED": "planning",
}
"""`DISCOVERY_VALIDATED`'s own entry is Planning, not Discovery again —
DESIGN.md §2.5's `advance_to_planning` gate invokes the Planning Agent once
Discovery's preconditions clear (today, always `NOT_IMPLEMENTED`, since
Planning is a v2 stub); the *retreat* back to `DISCOVERY` on a failed
precondition is `ppa/orchestrator/loop.py`'s own job, not another agent
invocation."""


class UnwiredWorkflowState(Exception):
    """Raised by `select_agent` for a state real v1 sessions cannot reach."""

    def __init__(self, workflow_state: str) -> None:
        self.workflow_state = workflow_state
        super().__init__(
            f"no agent is wired for workflow_state {workflow_state!r} — v1 only runs "
            "DISCOVERY and DISCOVERY_VALIDATED (DESIGN.md §2.5); later phases are v2/v3."
        )


def select_agent(workflow_state: str) -> Agent:
    """Table lookup — step 5. Raises `UnwiredWorkflowState` for any state
    outside `STATE_AGENT`, rather than falling through to a default agent."""

    agent_id = STATE_AGENT.get(workflow_state)
    if agent_id is None:
        raise UnwiredWorkflowState(workflow_state)
    return agent_for(agent_id)


def invoke_agent(agent: Agent, ctx: InvocationContext) -> AgentResult:
    """Step 7 — hand off to the inner loop. `Agent.invoke()` (T20) already
    owns everything the inner loop needs to know (system prompt, tool
    grant); this is deliberately a thin call, not a reimplementation of the
    SDK's own turn loop — "do not try to reimplement the inner loop" is this
    task's own stated trap."""

    return agent.invoke(ctx)
