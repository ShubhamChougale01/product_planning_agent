"""Research Mode subagent — the real thing (T29, DESIGN.md §6.5, §2.12,
S9.4-S9.5).

**Batches the whole `RESEARCH_REQUIRED` queue in one turn** — every
`Unknown(route="RESEARCH", status="OPEN")` at once, not one subagent
invocation per question (S9.4's own "batch the queue" framing) — the same
shape CLARIFY already uses for a batch of questions per round. Same
grant-isolation shape as `ppa.agents.subagents.guidance` (T28): its own
`ClaudeSDKClient`, its own system prompt, its own grant-scoped in-process
MCP server (`read_planning_state` + `manage_research`, identical grant to
Guidance's).

**Degradation is the actual point of this task**, not an afterthought:
`ResearchProvider.available()` is checked *before* any model call is
attempted — `UNAVAILABLE` never spends a turn at all. A real attempt that
raises is retried exactly once; a second failure degrades every queued
item with a message distinct from the no-capability case (§6.5's own
"these are different situations for the user").

Every degraded item is `classify`-d, never silently left alone: `why_it_
matters` gains the honest explanation, `owner_type` flips to `"user"` (the
person, not the agent, now owns getting this answered), and it stays
`route="RESEARCH"`, `status="OPEN"` — still visible in open items, per
§6.5's own "appears in open items" requirement. `blocked_reason` (the
task's own pseudocode field) is folded into `why_it_matters`'s free text
rather than a new schema field — decision #37, `blockers.md`: nothing in
`Unknown` (T02) has such a field, and the honest-explanation Done-when box
does not require it to be structured, only readable.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import anyio
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, create_sdk_mcp_server

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType, ResearchFinding, Unknown
from ppa.ledger.project import Project
from ppa.providers.model import ModelProvider
from ppa.providers.research import ResearchProvider, SdkWebSearchResearchProvider, failed_result
from ppa.tools.discovery_tools import manage_unknown
from ppa.tools.server import granted_sdk_tools

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

STALE_UNDERPINNING_STATUSES = ("OPEN", "DECIDE_LATER")
"""A `Decision` still in either status is "still open" for staleness
purposes (§6.5) — `DECIDED`/`SUPERSEDED` decisions don't need their own
research re-verified, the call is already made."""

_SYSTEM_PROMPT = """## Research Mode — batch the queue, cite real sources

You have been handed every open, non-blocking factual question this project has queued for
research. Your tools come back deferred — load each one with its own literal `ToolSearch` call
below before you touch anything else.

For **every** question in this batch: use `WebSearch` to actually research it — never answer from
memory alone when a real search is available to you. Then call `manage_research(operation="create",
...)` to persist what you found: `question` (restate plainly), `method` ("web search"), `summary`
(the actual finding, 1-3 sentences), `options_found` (if the question compares options),
`sources` (real URLs — never a fabricated citation), `confidence`, `confidence_basis`.

If a search genuinely turns up nothing conclusive, that is still a successful result — record it
honestly (`summary` says so plainly) rather than inventing something to fill the field. Do not skip
a question in the batch; every one needs its own `manage_research` call.

Do not narrate what you would record instead of actually calling the tool.
"""


def _open_research_unknowns(entities: dict[str, Any]) -> list[tuple[str, Unknown]]:
    return sorted(
        (eid, e) for eid, e in entities.items()
        if entity_type_for(eid) is EntityType.UNKNOWN and e.route == "RESEARCH" and e.status == "OPEN"
    )


def is_stale(finding: ResearchFinding, *, now: datetime | None = None) -> bool:
    """§6.5: "the status board flags findings older than 90 days [`stale_
    after_days`, per-finding] as STALE" — pure arithmetic against the
    finding's own two fields, nothing about the decision it underpins."""

    now = now or datetime.now(timezone.utc)
    age_days = (now - finding.researched_at).total_seconds() / 86400
    return age_days > finding.stale_after_days


def stale_findings_underpinning_open_decisions(
    entities: dict[str, Any], *, now: datetime | None = None
) -> list[str]:
    """Every `ResearchFinding` id that is both stale (`is_stale`) and still
    "underpins an open decision" — `feeds_decision` names a `Decision` whose
    own status is still `OPEN`/`DECIDE_LATER`. A stale finding behind an
    already-`DECIDED` decision is history, not something that needs
    re-flagging."""

    stale: list[str] = []
    for eid, entity in entities.items():
        if entity_type_for(eid) is not EntityType.RESEARCH_FINDING:
            continue
        if not is_stale(entity, now=now):
            continue
        decision = entities.get(entity.feeds_decision) if entity.feeds_decision else None
        if decision is not None and decision.status in STALE_UNDERPINNING_STATUSES:
            stale.append(eid)
    return stale


def _degrade_unknown(
    project: Project, unknown_id: str, unknown: Unknown, result_message: str,
    *, actor_id: str, session_id: str, workflow_state: str,
) -> None:
    honest_why = f"{unknown.why_it_matters} [{result_message}]"
    manage_unknown(
        "classify", project, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state,
        agent_id="research", entity_id=unknown_id, why_it_matters=honest_why, owner_type="user",
    )


def _guidance_style_server(project: Project) -> tuple[Any, list[str]]:
    # Deferred import — see ppa.agents.subagents.guidance's own identical
    # note: ppa.agents.turn -> ppa.tools.dispatch -> ppa.agents.registry ->
    # this module (for ResearchAgent) would otherwise be circular.
    from ppa.agents.turn import _bind_project, _tool_discovery_hint

    scoped = [_bind_project(t, project) for t in granted_sdk_tools("research")]
    server = create_sdk_mcp_server(name="research-tools", tools=scoped)
    allowed = [f"mcp__research-tools__{t.name}" for t in scoped]
    return server, allowed, _tool_discovery_hint(allowed)


async def _run_one_research_turn(*, system_prompt: str, server: Any, allowed_tools: list[str], user_message: str) -> tuple[str, float | None]:
    provider = ModelProvider()
    client = provider.client(
        system_prompt=system_prompt, allowed_tools=allowed_tools,
        mcp_servers={"research-tools": server}, tools=["ToolSearch", "WebSearch"],
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


def _run_batched_research_turn(project: Project, queue: list[tuple[str, Unknown]]) -> tuple[str, float | None]:
    """Separated from `run_research_session` purely so a test can monkeypatch
    this one call to simulate the FAILED path without a real network call."""

    server, allowed_tools, hint = _guidance_style_server(project)
    system_prompt = hint + "\n\n" + _SYSTEM_PROMPT
    user_message = "Research this batch:\n\n" + "\n".join(
        f"- {uid}: {u.question!r} (area: {u.area}, why it matters: {u.why_it_matters!r})" for uid, u in queue
    )
    return anyio.run(
        functools.partial(_run_one_research_turn, system_prompt=system_prompt, server=server, allowed_tools=allowed_tools, user_message=user_message)
    )


def run_research_session(
    project: Project, *, actor_id: str, session_id: str, workflow_state: str = "DISCOVERY",
    provider: ResearchProvider | None = None,
) -> AgentResult:
    """One full Research session against the entire open `RESEARCH_
    REQUIRED` queue. See this module's own docstring for the three
    degradation states and why each is checked in this order."""

    provider = provider or SdkWebSearchResearchProvider()
    entities = current_entities(project.events_path)
    queue = _open_research_unknowns(entities)
    if not queue:
        return AgentResult(status=AgentResultStatus.OK, summary="nothing queued for Research Mode right now.")

    if not provider.available():
        result = provider.research(queue[0][1].question, context="no capability available")
        for unknown_id, unknown in queue:
            _degrade_unknown(project, unknown_id, unknown, result.message, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state)
        return AgentResult(
            status=AgentResultStatus.OK, summary=result.message,
            data={"degraded": True, "outcome": "UNAVAILABLE", "degraded_count": len(queue)},
        )

    try:
        text, cost = _run_batched_research_turn(project, queue)
    except Exception:  # pragma: no cover - exercised via monkeypatch in tests
        try:
            text, cost = _run_batched_research_turn(project, queue)
        except Exception as exc:
            # Never through provider.research() here — the real provider's
            # own .research() is deliberately not the real path (see its
            # own docstring); the FAILED message is built directly instead.
            failed = failed_result(detail=repr(exc), degraded_answer="nothing verified — the search itself failed")
            for unknown_id, unknown in queue:
                _degrade_unknown(project, unknown_id, unknown, failed.message, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state)
            return AgentResult(
                status=AgentResultStatus.OK, summary=failed.message,
                data={"degraded": True, "outcome": "FAILED", "degraded_count": len(queue)},
            )

    return AgentResult(
        status=AgentResultStatus.OK,
        summary=text or f"researched {len(queue)} queued item(s).",
        data={"degraded": False, "outcome": "AVAILABLE", "queued_count": len(queue), "cost_usd": cost},
    )


class ResearchAgent(BaseAgent):
    id = "research"
    system_prompt = "Research Mode subagent — real behavior built in T29."

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        from ppa.agents.turn import _project_from_ctx  # deferred — see _guidance_style_server

        project = _project_from_ctx(ctx)
        return run_research_session(project, actor_id=f"agent:{self.id}", session_id=ctx.session_id, workflow_state=ctx.workflow_state)
