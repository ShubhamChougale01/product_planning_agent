"""Layer 3 — workflow state (DESIGN.md §2.5, §2.13: "orchestrator + tool
guard").

A table lookup, deliberately — this is what makes it cheaper than layer 4
(semantic), which may need to load related entities. Legality here is about
the **global** workflow state (§2.5), not any one entity's own status —
that distinction is what separates this layer from layer 5 (consistency,
which does check a specific entity's legal status transitions, via
`ppa.ledger.transitions`).

v1 only ever runs the global machine from `DISCOVERY` to
`DISCOVERY_VALIDATED` (§2.5) — the table below reflects exactly that and no
more. `PLANNING`/`PLAN_REVIEW`/`PLAN_APPROVED`/`DELIVERY`/`COMPLETE` appear
so Planning/Delivery tools (T18) have a real (if currently unreachable in
v1) home in the table rather than an implicit "everything else is legal"
gap.
"""

from __future__ import annotations

from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult

LAYER = "workflow"

# tool-name-prefix -> the set of global workflow states that tool may run in.
# Checked in the order below; the first matching prefix wins.
_LEGAL_STATES: dict[str, frozenset[str]] = {
    "read_": frozenset({"DISCOVERY", "DISCOVERY_VALIDATED", "PLANNING", "PLAN_REVIEW", "PLAN_APPROVED", "DELIVERY", "COMPLETE"}),
    "manage_requirement": frozenset({"DISCOVERY"}),
    "manage_assumption": frozenset({"DISCOVERY"}),
    "manage_decision": frozenset({"DISCOVERY"}),
    "manage_unknown": frozenset({"DISCOVERY"}),
    "ask_user": frozenset({"DISCOVERY"}),
    "request_guidance": frozenset({"DISCOVERY"}),
    "manage_research": frozenset({"DISCOVERY"}),
    "manage_plan": frozenset({"PLANNING"}),
    "manage_milestone": frozenset({"PLANNING"}),
    "manage_timeline": frozenset({"PLANNING"}),
    "analyze_plan_impact": frozenset({"PLANNING", "PLAN_REVIEW"}),
    "generate_story": frozenset({"PLAN_APPROVED", "DELIVERY"}),
    "validate_story": frozenset({"PLAN_APPROVED", "DELIVERY"}),
    "read_approved_plan": frozenset({"PLAN_APPROVED", "DELIVERY"}),
    "manage_linear_issue": frozenset({"PLAN_APPROVED", "DELIVERY"}),
}
"""Every write tool a real agent is granted today (`ppa/agents/registry.py`
`GRANTS`) has a row. A tool with no row is legal in every state — that is
the safe default for orchestrator-only tools (`invoke_*`,
`review_subagent_result`, `read_workflow_state`), which this table does not
gate at all; their legality is the Orchestrator's own state-machine
concern (T20), not a per-tool-call check."""


def check(tool_name: str, workflow_state: str) -> ToolResult | None:
    """`None` if `tool_name` is legal in `workflow_state`, including for
    any tool this table does not mention at all (the safe default — see
    the table's own docstring); otherwise a `BUSINESS` `ToolResult`."""

    legal_states = _LEGAL_STATES.get(tool_name)
    if legal_states is None:
        for prefix, states in _LEGAL_STATES.items():
            if prefix.endswith("_") and tool_name.startswith(prefix):
                legal_states = states
                break
    if legal_states is None or workflow_state in legal_states:
        return None

    rule = CATEGORY_RULES[ErrorCategory.BUSINESS]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.BUSINESS,
            code="ILLEGAL_WORKFLOW_STATE",
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=(
                f"{tool_name!r} is not legal in workflow_state {workflow_state!r} "
                f"— must be one of {sorted(legal_states)}"
            ),
            context={"validation_layer_failed": LAYER},
        ),
    )
