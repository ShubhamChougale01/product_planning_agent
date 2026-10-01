"""Guidance Mode subagent — the real thing (T28, DESIGN.md §1.7, §1.13,
§3.5, S9.1-S9.3).

**A subagent, not a tool — a conversation with a different posture** (§1.7's
own reasoning): it explores, may research the web, compares options and
lands on a recommendation, none of which fits "return data in response to
arguments." It runs its *own* SDK turn — a fresh `ClaudeSDKClient`, its own
system prompt, its own grant (`ppa/agents/registry.py::GRANTS["guidance"]`:
`read_planning_state` + `manage_research`, nothing Discovery has) — which is
what makes context isolation structural rather than a policy this module
has to enforce itself: a long research detour lives entirely inside this
turn's own conversation, never Discovery's.

**What triggers a session.** Every `Unknown` with `route == "GUIDANCE"` and
`status == "OPEN"` needs Guidance — both `unexplored` (T26's own route for
it) and the anti-loop guard's forced escalation (`ppa.engines.dont_know_
classifier.FORCED_ESCALATION_ROUTE == "unexplored"`) land on the exact same
route, so `dont_know_kind` in the brief below is always `"unexplored"` —
there is no second kind that reaches this subagent. `run_guidance_session`
picks the lowest-id such `Unknown` (deterministic, never "whichever the
model feels like").

**What this subagent does NOT do: land the decision.** Steps 1-6 of
DESIGN.md §3.5's sequence (restate, explain stakes, narrow, research,
present options, recommend) are this module's job. Step 7 ("land it — user
picks, or defers") needs `manage_decision`/`manage_assumption`, neither of
which is in this subagent's grant — that always happens back in Discovery's
own turn, with the brief this module returns already in hand. `RES-nnn`'s
own `feeds_decision` is therefore unknown at record time (the Decision
doesn't exist yet) and filled in afterward via `manage_research(operation=
"link_decision")`, once Discovery has actually landed it (decision #36,
`blockers.md`).

**The brief is schema-valid, not free text.** `GuidanceBrief` is a real
Pydantic model, not "however the model felt like formatting JSON that day" —
`options` is enforced at ≥2 by the model itself, the same "make the
contract impossible to violate silently" discipline every ledger entity in
this codebase already gets. The model's own final turn text is expected to
be *only* this JSON — never rendered directly at a person; `ppa.render.
guidance_card.render_guidance_brief` is what turns it into prose.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import anyio
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, create_sdk_mcp_server
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import EntityType
from ppa.ledger.project import Project
from ppa.providers.model import DEFAULT_CONFIG_PATH, ModelProvider
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo
from ppa.tools.server import granted_sdk_tools

if TYPE_CHECKING:
    from ppa.tools.dispatch import InvocationContext

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "subagent_guidance.md"

LLM_SURFACE = frozenset({"guidance"})
"""DESIGN.md §2.17 surface 3, verbatim: "explaining a decision, generating
and comparing options." Checked against `ppa.providers.model.LLM_SURFACES`
by `tests/eval/test_llm_surface_invariant.py`."""

MIN_OPTIONS = 2
"""S9.1: "returns a schema-valid brief with >=2 options" — enforced on the
model, not left to a caller's own review."""


class GuidanceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    best_when: str


class GuidanceRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option: str
    because: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class GuidanceBrief(BaseModel):
    """The task's own JSON shape, validated. `dont_know_kind` is always
    `"unexplored"` — see this module's own docstring for why no other kind
    ever reaches Guidance."""

    model_config = ConfigDict(extra="forbid")

    dont_know_kind: Literal["unexplored"] = "unexplored"
    restated_plainly: str
    why_it_matters: str
    what_it_affects: list[str] = Field(default_factory=list)
    options: list[GuidanceOption]
    recommendation: GuidanceRecommendation
    what_would_settle_it: str
    safe_default_if_deferred: str
    researched: bool
    sources: list[str] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def _at_least_two_options(cls, value: list[GuidanceOption]) -> list[GuidanceOption]:
        if len(value) < MIN_OPTIONS:
            raise ValueError(f"a GuidanceBrief needs >= {MIN_OPTIONS} options, got {len(value)}")
        return value


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_guidance_brief(text: str) -> GuidanceBrief:
    """The model's own final turn text, expected to be *only* the brief's
    JSON — defensively strips a markdown code fence if the model added one
    anyway, the same forgiving-parse discipline bug #10's `_coerce_mcp_
    value` already applies to a real model's raw output elsewhere."""

    stripped = _JSON_FENCE.sub("", text.strip()).strip()
    return GuidanceBrief.model_validate(json.loads(stripped))


def _open_guidance_unknown(entities: dict[str, Any]) -> tuple[str, Any] | None:
    candidates = sorted(
        (eid, e) for eid, e in entities.items()
        if entity_type_for(eid) is EntityType.UNKNOWN and e.route == "GUIDANCE" and e.status == "OPEN"
    )
    return candidates[0] if candidates else None


def _guidance_server_and_allowed_tools(project: Project) -> tuple[Any, list[str]]:
    # Deferred import: ppa.agents.turn imports ppa.tools.dispatch, which
    # imports ppa.agents.registry, which imports this module (for
    # GuidanceAgent) — a module-level import here would be circular. Same
    # pattern ppa.agents.discovery.allowed_tools_for_mode already uses for
    # exactly this reason.
    from ppa.agents.turn import _bind_project

    scoped = [_bind_project(t, project) for t in granted_sdk_tools("guidance")]
    server = create_sdk_mcp_server(name="guidance-tools", tools=scoped)
    allowed = [f"mcp__guidance-tools__{t.name}" for t in scoped]
    return server, allowed


async def _run_one_guidance_turn(*, system_prompt: str, server: Any, allowed_tools: list[str], user_message: str) -> tuple[str, float | None]:
    """Its own `ClaudeSDKClient`, its own conversation — never appended to
    Discovery's. `tools=["ToolSearch", "WebSearch"]`: `ToolSearch` resolves
    the deferred MCP grant (bug #7); `WebSearch` is the one built-in tool
    this subagent needs back, since `ModelProvider.options()` defaults
    `tools=[]` (bug #6) and web search is genuinely this subagent's job,
    confirmed available under subscription auth (decision #5)."""

    provider = ModelProvider.from_config(DEFAULT_CONFIG_PATH)
    client = provider.client(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        mcp_servers={"guidance-tools": server},
        tools=["ToolSearch", "WebSearch"],
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


def _non_recoverable(description: str) -> AgentResult:
    return AgentResult(
        status=AgentResultStatus.NON_RECOVERABLE,
        summary=description,
        error=ErrorInfo(
            category=ErrorCategory.TRANSIENT, code="GUIDANCE_TURN_FAILED",
            is_retryable=True, recommended_action=RecoveryAction.RETRY_SAME, description=description,
        ),
    )


def run_guidance_session(project: Project, *, actor_id: str, session_id: str, workflow_state: str = "DISCOVERY") -> AgentResult:
    """One full Guidance session against whichever `Unknown(route=GUIDANCE,
    status=OPEN)` is queued — steps 1-6 only, see this module's own
    docstring for why landing (step 7) never happens here."""

    from ppa.agents.turn import _tool_discovery_hint  # deferred — see _guidance_server_and_allowed_tools

    entities = current_entities(project.events_path)
    found = _open_guidance_unknown(entities)
    if found is None:
        return AgentResult(status=AgentResultStatus.OK, summary="nothing queued for Guidance Mode right now.")
    unknown_id, unknown = found

    server, allowed_tools = _guidance_server_and_allowed_tools(project)
    system_prompt = _tool_discovery_hint(allowed_tools) + "\n\n" + _PROMPT_PATH.read_text(encoding="utf-8")
    user_message = (
        f"Run a Guidance session on {unknown_id}: {unknown.question!r} (area: {unknown.area}, "
        f"why it matters: {unknown.why_it_matters!r}). Persist your finding with manage_research(create, "
        "...) before you reply, then reply with *only* the GuidanceBrief JSON — no prose, no markdown "
        "fence, nothing before or after it."
    )

    try:
        text, cost = anyio.run(
            functools.partial(
                _run_one_guidance_turn,
                system_prompt=system_prompt, server=server, allowed_tools=allowed_tools, user_message=user_message,
            )
        )
    except Exception as exc:  # pragma: no cover - network/auth failures
        return _non_recoverable(f"Guidance session failed to complete: {exc!r}")

    try:
        brief = parse_guidance_brief(text)
    except (json.JSONDecodeError, ValidationError) as exc:
        return _non_recoverable(f"Guidance session did not return a schema-valid brief: {exc!r}. Raw text: {text!r}")

    return AgentResult(
        status=AgentResultStatus.OK,
        summary=f"Guidance session complete for {unknown_id}.",
        data={"unknown_id": unknown_id, "brief": brief.model_dump(mode="json"), "cost_usd": cost},
    )


class GuidanceAgent(BaseAgent):
    id = "guidance"
    system_prompt = "Guidance Mode subagent — real behavior built in T28."

    def invoke(self, ctx: InvocationContext) -> AgentResult:
        from ppa.agents.turn import _project_from_ctx  # deferred — see _guidance_server_and_allowed_tools

        project = _project_from_ctx(ctx)
        return run_guidance_session(project, actor_id=f"agent:{self.id}", session_id=ctx.session_id, workflow_state=ctx.workflow_state)
