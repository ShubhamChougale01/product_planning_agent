"""Tool dispatcher — the permission gate (DESIGN.md §2.10, §2.13, S5.2).

Least privilege only means something if it is enforced in code. A prompt
saying "you must not create Linear issues" is a suggestion; a dispatcher
that refuses to run the handler is a boundary.

Permission runs **first**, before anything else, for two reasons: it is the
cheapest check, and a permission failure should not leak schema details
about a tool the caller may not use. `ctx.agent_id` is set by the
Orchestrator when it invokes an agent and is the *only* source of caller
identity — never read from model output, never from `args`. A model
claiming to be the Delivery Agent, or passing `{"agent_id": "delivery"}` in
its own call arguments, changes nothing.

The remaining four validation layers (schema, workflow, semantic,
consistency) are wired in T19, at the point this module marks below —
`dispatch` does not stub them out as no-ops; they are simply not inserted
yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ppa.agents.registry import grant_for
from ppa.ledger.audit import AuditOperation, AuditResult, record_audit
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo, ToolResult
from ppa.tools import registry as tool_registry


@dataclass(frozen=True)
class InvocationContext:
    """Everything the dispatcher needs about *who* is calling and *where*
    to record it — set entirely by the Orchestrator, never by the model."""

    agent_id: str
    workflow_state: str
    session_id: str
    audit_path: Path | str
    ledger_version: int = 0
    txn_id: str | None = None


def _operation_for(tool_name: str) -> AuditOperation:
    """A granted call is audited as `"read"` if the tool name starts with
    `read_` (matching this build's own naming: `read_planning_state`,
    `read_workflow_state`, `read_approved_plan`), `"write"` otherwise.
    `ToolSpec` carries nothing more precise to key on yet."""

    return "read" if tool_name.startswith("read_") else "write"


def permission_error(tool_name: str, agent_id: str) -> ToolResult:
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.PERMISSION,
            code="TOOL_NOT_GRANTED",
            is_retryable=False,
            description=f"{agent_id!r} is not granted {tool_name!r}",
            recommended_action=RecoveryAction.ABORT_AND_ROUTE,
        ),
    )


def _not_implemented_error(tool_name: str) -> ToolResult:
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=ErrorCategory.NOT_IMPLEMENTED,
            code="TOOL_NOT_REGISTERED",
            is_retryable=False,
            description=f"{tool_name!r} is granted but not yet registered",
            recommended_action=RecoveryAction.INFORM_USER,
        ),
    )


def _audit(
    ctx: InvocationContext,
    *,
    tool_name: str,
    args: dict[str, Any],
    operation: AuditOperation,
    reason: str,
    result: ToolResult,
    ledger_version_after: int | None = None,
) -> None:
    error = result.error
    record_audit(
        agent=ctx.agent_id,
        tool=tool_name,
        operation=operation,
        workflow_state=ctx.workflow_state,
        inputs=args,
        reason=reason,
        result=AuditResult(
            success=result.success,
            category=error.category if error else None,
            code=error.code if error else None,
        ),
        path=ctx.audit_path,
        ledger_version_before=ctx.ledger_version,
        ledger_version_after=ledger_version_after if ledger_version_after is not None else ctx.ledger_version,
        txn_id=ctx.txn_id,
    )


async def dispatch(tool_name: str, args: dict[str, Any], ctx: InvocationContext) -> ToolResult:
    """1. PERMISSION — first, always, checked against `ctx.agent_id` alone.
    2-5. Schema / workflow / semantic / consistency — **not yet wired; T19
         inserts them exactly here.**
    6. Execute the registered handler, if one exists.

    A tool granted to `ctx.agent_id` but not yet registered in
    `ppa/tools/registry.py` (most tools, before T15-T18 build them) returns
    `NOT_IMPLEMENTED` rather than raising — the caller was allowed to ask.
    """

    if tool_name not in grant_for(ctx.agent_id):
        result = permission_error(tool_name, ctx.agent_id)
        _audit(
            ctx,
            tool_name=tool_name,
            args=args,
            operation="reject",
            reason=f"{ctx.agent_id!r} attempted {tool_name!r} without a grant",
            result=result,
        )
        return result

    try:
        registered = tool_registry.get(tool_name)
    except KeyError:
        result = _not_implemented_error(tool_name)
        _audit(
            ctx,
            tool_name=tool_name,
            args=args,
            operation="reject",
            reason=f"{tool_name!r} is granted to {ctx.agent_id!r} but has no registered handler",
            result=result,
        )
        return result

    # --- T19 inserts layers 2-5 (schema, workflow, semantic, consistency) here. ---

    raw = await registered.handler(args)
    result = ToolResult(success=True, result_count=1, data=raw)
    _audit(
        ctx,
        tool_name=tool_name,
        args=args,
        operation=_operation_for(tool_name),
        reason=f"{ctx.agent_id!r} called {tool_name!r}",
        result=result,
    )
    return result
