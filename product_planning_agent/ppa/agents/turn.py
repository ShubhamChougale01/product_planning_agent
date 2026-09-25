"""Turn integration — one real Discovery turn, wired to the outer loop
built in T21 (DESIGN.md S7.3).

```
read digest (T09)
  -> inject current date, current mode, user profile
  -> run the agent
  -> process tool calls
  -> evaluate the readiness gate (T10)
  -> return a structured AgentResult to the Orchestrator
```

**Discovery never decides completion.** This module reports what happened
during the turn — never whether the task is "done." `AgentResultStatus` is
classified from what the *ledger* shows after the turn (a new `PENDING`
question means `HUMAN_INPUT_REQUIRED`), never from parsing the model's own
prose. The readiness gate is evaluated here only to attach as informational
data; `ppa.orchestrator.loop` is the only place completion is ever decided
(T21), by calling `check_readiness()` itself at the top of the next turn.

**`InvocationContext` (T20/T21) carries no `Project` reference** — only
`agent_id`/`workflow_state`/`session_id`/`audit_path`/`ledger_version`/
`txn_id`. Rather than extending that shape (out of this task's own file
scope, and T21's before it), `_project_from_ctx` reconstructs a full
`Project` handle from `ctx.audit_path` alone — `.planning/audit.ndjson`'s
parent is the project's `.planning/` directory, whose sibling
`events.ndjson` already holds everything `read_project_meta` needs.
"""

from __future__ import annotations

import functools
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, create_sdk_mcp_server

from ppa.agents.base import AgentResult, AgentResultStatus
from ppa.agents.discovery import DEFAULT_MODE, DiscoveryMode, allowed_tools_for_mode, render_system_prompt
from ppa.config.profiles import UserProfile
from ppa.engines.readiness import check_readiness
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import Project
from ppa.ledger.store import path_lock, read_project_meta, write_project_meta
from ppa.orchestrator.context import assemble_context
from ppa.providers.model import ModelProvider
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo
from ppa.tools.dispatch import InvocationContext
from ppa.tools.server import granted_sdk_tools

_MODE_META_KEY = "discovery_mode"


def _project_from_ctx(ctx: InvocationContext) -> Project:
    """Reconstruct a `Project` handle purely from `ctx.audit_path` — see
    this module's own docstring for why `InvocationContext` doesn't carry
    one directly."""

    planning_dir = Path(ctx.audit_path).parent
    project_dir = planning_dir.parent
    events_path = planning_dir / "events.ndjson"
    meta = read_project_meta(events_path)
    return Project(
        slug=project_dir.name,
        name=meta.get("name", project_dir.name),
        profile=UserProfile.model_validate(meta["profile"]),
        workflow_state=meta.get("workflow_state", ctx.workflow_state),
        created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else datetime.now(timezone.utc),
        path=project_dir,
    )


def _current_mode(project: Project) -> DiscoveryMode:
    meta = read_project_meta(project.events_path)
    raw = meta.get(_MODE_META_KEY)
    if raw is None:
        return DEFAULT_MODE
    return DiscoveryMode(raw)


def _set_mode(project: Project, mode: DiscoveryMode) -> None:
    with path_lock(project.events_path):
        meta = read_project_meta(project.events_path)
        meta[_MODE_META_KEY] = mode.value
        write_project_meta(project.events_path, meta)


def _bare_tool_name(name: str) -> str:
    return name.rsplit("__", 1)[-1]


def _mode_scoped_server_and_allowed_tools(mode) -> tuple[Any, list[str]]:
    server_name = f"discovery-{mode.value.lower()}-tools"
    subset = allowed_tools_for_mode(mode)
    scoped = [t for t in granted_sdk_tools("discovery") if t.name in subset]
    server = create_sdk_mcp_server(name=server_name, tools=scoped)
    allowed = [f"mcp__{server_name}__{t.name}" for t in scoped]
    return server, allowed


async def _run_one_sdk_turn(*, system_prompt: str, server: Any, allowed_tools: list[str], user_message: str) -> tuple[str, float | None]:
    """The inner loop is the SDK's — this awaits exactly one `query` +
    `receive_response` exchange and collects the assistant's text. Tool
    execution (and therefore every ledger write this turn makes) happens
    inside this exchange, dispatched by the in-process MCP server."""

    provider = ModelProvider()
    client = provider.client(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        mcp_servers={_server_name_from(allowed_tools): server},
    )

    text: list[str] = []
    cost: float | None = None
    async with client:
        await client.query(user_message)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text.append(block.text)
            elif isinstance(msg, ResultMessage):
                cost = getattr(msg, "total_cost_usd", None)

    return "".join(text).strip(), cost


def _server_name_from(allowed_tools: list[str]) -> str:
    # "mcp__<server_name>__<tool_name>" -> "<server_name>"
    if not allowed_tools:
        return "discovery-empty-tools"
    return allowed_tools[0].split("__")[1]


def _non_recoverable(description: str) -> AgentResult:
    return AgentResult(
        status=AgentResultStatus.NON_RECOVERABLE,
        summary=description,
        error=ErrorInfo(
            category=ErrorCategory.TRANSIENT,
            code="DISCOVERY_TURN_FAILED",
            is_retryable=True,
            recommended_action=RecoveryAction.RETRY_SAME,
            description=description,
        ),
    )


def run_discovery_turn(ctx: InvocationContext, *, today: date | None = None) -> AgentResult:
    """`Agent.invoke()` for the real `DiscoveryAgent` — one turn, per this
    module's own docstring diagram."""

    project = _project_from_ctx(ctx)
    profile = project.profile
    mode = _current_mode(project)

    entities_before = current_entities(project.events_path)
    bundle = assemble_context(project, entities_before, now=datetime.now(timezone.utc))

    system_prompt = render_system_prompt(mode, profile, today=today)
    server, allowed_tools = _mode_scoped_server_and_allowed_tools(mode)

    try:
        text, cost = anyio.run(
            functools.partial(
                _run_one_sdk_turn,
                system_prompt=system_prompt,
                server=server,
                allowed_tools=allowed_tools,
                user_message=bundle.text,
            )
        )
    except Exception as exc:  # pragma: no cover - network/auth failures
        return _non_recoverable(f"Discovery turn failed to complete: {exc!r}")

    entities_after = current_entities(project.events_path)
    pending_questions = [
        eid
        for eid, e in entities_after.items()
        if entity_type_for(eid) is EntityType.QUESTION_ANSWER and e.status == "PENDING"
    ]

    ready, blockers = check_readiness(entities_after, profile)

    if mode is DiscoveryMode.INTAKE and not pending_questions:
        # Intake is structurally one turn (DESIGN.md S7.4) — once it
        # completes without leaving a question open, move on to CLARIFY.
        # T25 owns CLARIFY's own real stopping/advancement logic; nothing
        # here decides when CLARIFY itself ends.
        _set_mode(project, DiscoveryMode.CLARIFY)

    status = AgentResultStatus.HUMAN_INPUT_REQUIRED if pending_questions else AgentResultStatus.OK
    summary = text or ("waiting on an answer" if pending_questions else "turn completed")

    return AgentResult(
        status=status,
        summary=summary,
        data={
            "mode": mode.value,
            "pending_questions": pending_questions,
            "ready": ready,
            "blocker_count": len(blockers),
            "cost_usd": cost,
        },
    )
