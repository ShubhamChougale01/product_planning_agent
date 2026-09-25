"""PreToolUse — layers 1-3, in order (T19, DESIGN.md §2.13, §2.18).

```
1  Permission   ppa.validation.permission.check   — dispatcher, pre-body
2  Schema       ppa.validation.schema.check       — PreToolUse hook (Pydantic)
3  Workflow     ppa.validation.workflow.check     — orchestrator + tool guard
```

`pre_tool_use` runs exactly these three, in exactly this order, and returns
the **first** failure — permission is cheapest and must never leak schema
details about a tool the caller isn't granted, and workflow runs after
schema because schema is itself cheaper than a workflow-state table lookup
that may reference the current agent's mode.

Layers 4 (semantic, `ppa/validation/semantic.py`) and 5 (consistency,
`ppa/validation/consistency.py`) are **not** run here. §2.13 states why
directly: "workflow before semantic because workflow is a table lookup
while semantic validation may need to load related entities" — semantic
and consistency checks need a loaded, materialized ledger and often the
specific entity being changed, which is exactly the tool body's own
territory (`ppa.tools.discovery_tools._generic_transition` already calls
`ppa.validation.consistency.check_transition` directly, and registers its
one semantic rule into `ppa.validation.semantic`). `pre_tool_use` is the
part of the five-layer chain that can run *before* a tool body without
loading anything.

**Not wired into `ppa/tools/dispatch.py` in this task.** `ppa/tools/
dispatch.py` is not in T19's own "Files touched" list, and its dispatcher
already has passing T14 tests built against today's behavior (`ppa/tools/
dispatch.py`'s own docstring marks the exact insertion point for a later
task to use). `pre_tool_use` is complete, real, and independently tested
here — wiring it into the dispatcher's actual call path is deliberately
left to whichever task next touches `dispatch.py`'s "T19 inserts layers
2-5 exactly here" marker, matching this codebase's repeated
infrastructure-then-integration pattern (T13 built the tool registry
before T15 built the first real tool against it). See decision #26 in
`blockers.md`.

**"PostToolUse" — event append, materialize, digest, audit — is not a
separate hook function either.** Every write tool built so far (T16, T17,
T18's `manage_linear_issue`) already does exactly that sequence inline, in
its own body, self-audited (decision #24) — the same "pure, directly-
testable function" pattern this codebase has used since T15's `read_
planning_state`, not an SDK-hook indirection. Nothing here duplicates that.
"""

from __future__ import annotations

from typing import Any

from ppa.results.envelope import ToolResult
from ppa.tools.spec import ToolSpec
from ppa.validation import permission, schema, workflow
from ppa.validation import infer_validation_layer


def pre_tool_use(tool_name: str, args: dict[str, Any], spec: ToolSpec, agent_id: str, workflow_state: str) -> ToolResult | None:
    """`None` if `tool_name` clears permission, schema and workflow, in
    that order; otherwise the first layer's own `ToolResult`, already
    tagged with `validation_layer_failed` in `error.context`."""

    result = permission.check(tool_name, agent_id)
    if result is not None:
        return result

    result = schema.check(spec, args)
    if result is not None:
        return result

    result = workflow.check(tool_name, workflow_state)
    if result is not None:
        return result

    return None


__all__ = ["pre_tool_use", "infer_validation_layer"]
