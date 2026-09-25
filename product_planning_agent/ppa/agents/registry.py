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
