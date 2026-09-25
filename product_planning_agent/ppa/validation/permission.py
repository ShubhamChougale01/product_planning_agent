"""Layer 1 — permission. Runs first (DESIGN.md §2.10, §2.13).

The cheapest check, and the one that must never leak schema details about a
tool the caller isn't even allowed to name. `ppa/tools/dispatch.py` (T14)
already enforces this inline at the dispatcher boundary — this module gives
that same check a name and a home in the five-layer package, so
`ppa/tools/hooks.py` (T19) and any future caller can run it standalone,
independent of the dispatcher's own wiring.

Caller identity always comes from the invocation context the Orchestrator
sets, never from `args` — this module takes `agent_id` as a plain
parameter for exactly that reason, so nothing here can be tempted to read
it from a dict a model could have shaped.
"""

from __future__ import annotations

from ppa.agents.registry import grant_for
from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult

LAYER = "permission"


def check(tool_name: str, agent_id: str) -> ToolResult | None:
    """`None` if `agent_id` is granted `tool_name`; otherwise a `PERMISSION`
    `ToolResult`, tagged `validation_layer_failed="permission"` in its
    `error.context` so an auditor never has to re-derive which layer this
    came from."""

    if tool_name in grant_for(agent_id):
        return None

    rule = CATEGORY_RULES[ErrorCategory.PERMISSION]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.PERMISSION,
            code="TOOL_NOT_GRANTED",
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=f"{agent_id!r} is not granted {tool_name!r}",
            context={"validation_layer_failed": LAYER},
        ),
    )
