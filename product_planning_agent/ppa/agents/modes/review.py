"""REVIEW mode — walking assumptions and the readiness gate's own missing
approval fact (T30, DESIGN.md §1.10, §3.7, S10.1-S10.2).

Two things this module owns:

1. **`run_review_session`** — one real turn, REVIEW's own widened grant
   (`read_planning_state` + `manage_assumption`, `ppa/agents/discovery.py`),
   walking every HIGH-impact `PROPOSED` `Assumption` individually and
   presenting the rest of the ledger's own open state, guided by `mode_
   review.md`.
2. **`grant_review_approval`/`current_review_approval`** — decision #19's
   own `review_approved` gap, finally wired. **Deliberately not an MCP
   tool** — `ppa/tools/approval.py`'s own module docstring already states
   the rule this follows: *"No agent is ever granted a tool to call
   `grant_approval` itself... approval is the user's decision, not
   something an agent can manufacture for itself by calling a tool."*
   `review.approved` is a system/meta event, no `entity_id`, folded the
   same "latest write wins" way `current_approval` already folds `approval.
   granted`/`revoked` — except REVIEW approval has no revoke counterpart
   (nothing in this build's scope ever needs to un-approve a review).

Like every other mode's shape contract in this package, `evaluate_review_
round` checks the *ledger state* a round actually wrote, never the model's
own claimed text.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import anyio
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from pydantic import BaseModel, ConfigDict

from ppa.agents.base import AgentResult, AgentResultStatus
from ppa.agents.discovery import DiscoveryMode, render_system_prompt
from ppa.ledger.events import EventType
from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType
from ppa.ledger.project import Project
from ppa.ledger.store import append_event
from ppa.providers.model import ModelProvider
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo
from ppa.tools.approval import _read_all_events  # reused directly — see this module's own docstring


class ReviewApproval(BaseModel):
    """The currently active review approval, or `None` — folded from the
    event log, never cached, same freshness guarantee `current_approval`
    already gives T18's Linear-issue gate."""

    model_config = ConfigDict(extra="forbid")

    approved_by: str
    approved_at: datetime
    approved_areas: list[str]


def grant_review_approval(
    events_path: Path | str, *, approved_areas: list[str], approved_by: str,
    actor_id: str, session_id: str, workflow_state: str = "DISCOVERY",
    reason: str = "review approved", now: datetime | None = None,
) -> str:
    """The user's own act, never the model's — see this module's own
    docstring. `approved_areas` folds straight into readiness gate
    condition 1's `confirmed_areas` (decision #19); one write covers both
    facts DESIGN.md's own gate needs."""

    ts = now or datetime.now(timezone.utc)
    after = dict(approved_by=approved_by, approved_at=ts.isoformat(), approved_areas=list(approved_areas))
    return append_event(
        dict(
            ts=ts, type=EventType.REVIEW_APPROVED, entity_id=None, actor_id=actor_id, actor_role="user",
            agent_name=None, workflow_state=workflow_state, txn_id=None, source="review_gate",
            reason=reason, before=None, after=after, session_id=session_id,
        ),
        events_path,
    )


def current_review_approval(events_path: Path | str) -> ReviewApproval | None:
    events = _read_all_events(Path(events_path))
    latest: ReviewApproval | None = None
    for event in events:
        if event.type == EventType.REVIEW_APPROVED:
            latest = ReviewApproval.model_validate(event.after)
    return latest


def readiness_gate_inputs(events_path: Path | str) -> tuple[bool, set[str]]:
    """`(review_approved, confirmed_areas)` — exactly `check_readiness`'s
    own two REVIEW-owned keyword arguments (decision #19), read straight
    from the event log so a caller never has to know this module's own
    folding logic."""

    approval = current_review_approval(events_path)
    if approval is None:
        return False, set()
    return True, set(approval.approved_areas)


class ReviewRoundReport(BaseModel):
    """One completed REVIEW turn, checked against `tasks/t30_review_and_
    change_handling.md`'s own per-round Done-when boxes."""

    model_config = ConfigDict(extra="forbid")

    assumptions_walked_individually: int
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def evaluate_review_round(
    high_impact_proposed_before: Mapping[str, BaseEntity],
    entities_after: Mapping[str, BaseEntity],
) -> ReviewRoundReport:
    """`high_impact_proposed_before` is every HIGH-impact, still-`PROPOSED`
    `Assumption` id the round started with — every one of them must be
    `CONFIRMED`/`REJECTED`/`SUPERSEDED` (never still `PROPOSED`) by the time
    `entities_after` is checked, each via its own `manage_assumption` call
    (structurally guaranteed one-`entity_id`-at-a-time, since the tool
    itself never accepts more than one)."""

    violations: list[str] = []
    walked = 0
    for eid in high_impact_proposed_before:
        after_entity = entities_after.get(eid)
        if after_entity is None or entity_type_for(eid) is not EntityType.ASSUMPTION:
            violations.append(f"{eid}: no longer present or not an Assumption after the round")
            continue
        if after_entity.status == "PROPOSED":
            violations.append(f"{eid}: still PROPOSED — was never walked this round")
            continue
        walked += 1

    return ReviewRoundReport(assumptions_walked_individually=walked, violations=violations)


async def _run_one_review_turn(*, system_prompt: str, server: Any, allowed_tools: list[str], user_message: str) -> tuple[str, float | None]:
    provider = ModelProvider()
    client = provider.client(
        system_prompt=system_prompt, allowed_tools=allowed_tools,
        mcp_servers={_server_name(allowed_tools): server}, tools=["ToolSearch"],
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


def _server_name(allowed_tools: list[str]) -> str:
    return allowed_tools[0].split("__")[1] if allowed_tools else "discovery-review-tools"


def _non_recoverable(description: str) -> AgentResult:
    return AgentResult(
        status=AgentResultStatus.NON_RECOVERABLE, summary=description,
        error=ErrorInfo(category=ErrorCategory.TRANSIENT, code="REVIEW_TURN_FAILED", is_retryable=True, recommended_action=RecoveryAction.RETRY_SAME, description=description),
    )


def run_review_session(project: Project, *, user_message: str) -> AgentResult:
    """One REVIEW turn. `user_message` is the caller's own framing of "walk
    the review now" — deliberately a parameter rather than derived from
    ledger state alone, since a real session may want to hand the model
    context about *why* review started now (e.g. "readiness just passed
    for the first time")."""

    # Deferred import, matching every other mode/subagent module's own
    # precedent in this build (ppa.agents.turn sits downstream of
    # ppa.agents.registry's own import chain).
    from ppa.agents.turn import _mode_scoped_server_and_allowed_tools, _tool_discovery_hint

    server, allowed_tools = _mode_scoped_server_and_allowed_tools(DiscoveryMode.REVIEW, project)
    system_prompt = _tool_discovery_hint(allowed_tools) + "\n\n" + render_system_prompt(DiscoveryMode.REVIEW, project.profile)

    try:
        text, cost = anyio.run(
            functools.partial(_run_one_review_turn, system_prompt=system_prompt, server=server, allowed_tools=allowed_tools, user_message=user_message)
        )
    except Exception as exc:  # pragma: no cover - network/auth failures
        return _non_recoverable(f"Review turn failed to complete: {exc!r}")

    return AgentResult(status=AgentResultStatus.OK, summary=text or "review turn completed.", data={"cost_usd": cost})
