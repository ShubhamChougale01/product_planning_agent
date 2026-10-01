"""Change handling — `CHANGE_REQUESTED` is reachable from every state, and
a contradiction in round 4 must never silently corrupt round 1 (T30,
DESIGN.md §1.10, §3.7, S10.1-S10.2).

Six steps, DESIGN.md's own numbering:

```
1 detect      ppa.engines.conflicts.find_conflict_candidates (deterministic, T11)
2 adjudicate  the model decides: real contradiction, refinement, or unrelated?
3 surface     manage_conflict(adjudicate) — recorded, never silently skipped
4 supersede   manage_requirement/assumption/decision(supersede) + create the new version
5 impact      ppa.engines.impact.analyze_impact (deterministic, T11)
6 recompute   readiness gate; rewind the global workflow state
```

Steps 1, 5 and the readiness recompute are pure engine calls, already built
(T10/T11) — nothing here re-derives them. Step 2 (real contradiction vs.
refinement vs. unrelated) is inherently qualitative, the model's own job,
guided by an inline system prompt (no separate `.md` file — short enough to
belong directly in this module, unlike Discovery's own multi-mode prompt
set). Step 3 is `manage_conflict`, T30's one new tool (`ppa/tools/
discovery_tools.py`, decision #38) — a verdict is *recorded* the instant
it's reached, never left as something only the model's own prose claims to
have noticed.

**Not a `DiscoveryMode`.** `CHANGE_REQUESTED` is the *global* workflow
state (`ppa.workflow.machine`), a different level from Discovery's own
internal mode machine (T20's own "two levels of state" distinction,
`ppa/agents/discovery.py`'s module docstring) — change handling runs its
own turn against `agent_id="discovery"`'s **full** grant, un-scoped by any
`DiscoveryMode` subset, the same "not a mode" shape T28/T29's subagents
already established for a different reason (isolation there; a different
state *level* here).

**The v1 rewind target is always `DISCOVERY`.** `ppa/workflow/transitions.
yaml`'s own comment says picking the rewind target is "impact analysis's
call (T30), not this table's" — but decision #28 (T21) already established
that v1 only ever wires `DISCOVERY`/`DISCOVERY_VALIDATED`; `PLANNING`,
`PLAN_REVIEW` etc. are declared in the transition table for provable
reachability but nothing in this build can actually be *in* one of them
yet. Until Planning/Delivery exist, "the earliest affected state" and
"`DISCOVERY`" are the same fact.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import anyio
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, create_sdk_mcp_server
from pydantic import BaseModel, ConfigDict

from ppa.agents.base import AgentResult, AgentResultStatus
from ppa.engines.conflicts import Candidate, find_conflict_candidates
from ppa.engines.impact import ImpactReport, analyze_impact
from ppa.ledger.events import EventType
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import BaseEntity, EntityType, QuestionAnswer
from ppa.ledger.project import Project
from ppa.providers.model import DEFAULT_CONFIG_PATH, ModelProvider
from ppa.results.categories import ErrorCategory, RecoveryAction
from ppa.results.envelope import ErrorInfo
from ppa.tools.approval import _read_all_events  # reused directly — same as ppa.agents.modes.review
from ppa.tools.interaction import ask_user
from ppa.tools.server import granted_sdk_tools

REWIND_TARGET = "DISCOVERY"
"""See this module's own docstring — the only real rewind target while
Planning/Delivery stay unwired (decision #28)."""

LLM_SURFACE = frozenset({"interpretation"})
"""DESIGN.md §2.17: adjudicating a conflict candidate (real contradiction,
refinement, or unrelated?) is turning new free text against existing
CONFIRMED state into a structured verdict — interpretation, nothing else.
Checked against `ppa.providers.model.LLM_SURFACES` by
`tests/eval/test_llm_surface_invariant.py`."""

_SYSTEM_PROMPT = """## Change handling — a change came in, do not lose or silently corrupt anything

Something new was just said — a scope addition, a correction, a change of mind. Your job has two
halves, and you must do both:

1. **For every conflict candidate listed below**, decide: is this a real contradiction (the new
   information genuinely can't be true at the same time as what's already CONFIRMED), a refinement
   (narrows or clarifies without actually contradicting), or unrelated (the signal that flagged it
   was a false positive)? Call `manage_conflict(operation="adjudicate", subject_id=..., candidate_id=...,
   verdict=..., resolved=..., explanation=...)` for **every** candidate listed, even one you decide
   is unrelated — an unrecorded verdict is a silently-dropped conflict, never acceptable. If it's a
   real contradiction, set `resolved=True` on this same call only once you have *also* superseded
   the old entity in this same turn (see step 2) — otherwise leave `resolved=False` and surface it
   in your reply instead of deciding for the person.

2. **Record what actually changed.** A genuinely new scope item becomes a new `manage_requirement
   (create, ...)`. A real contradiction means: supersede the old entity
   (`manage_requirement`/`manage_assumption`/`manage_decision`(`operation="supersede"`,
   `change_reason=...`)) and create its replacement — never edit the old one in place, never delete
   it, it stays SUPERSEDED with its own full history intact.

Never silently append a contradiction next to what it contradicts. If you decide something is a
real contradiction, say so plainly in your reply, in the terms DESIGN.md's own example uses: name
the old entity, what it said, when it was confirmed, and what the new information changes.

Do not narrate what you would record instead of actually calling the tools.
"""


def _record_change_as_answer(project: Project, *, change_text: str, actor_id: str, session_id: str, workflow_state: str, now: datetime | None) -> QuestionAnswer:
    result = ask_user(
        [{
            "text": "Has anything about scope or an earlier answer changed?",
            "why_asked": "a change request needs to be compared against everything already CONFIRMED",
            "answer": {"answer_kind": "answered", "answer_text": change_text},
        }],
        project, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state, actor_role="user", now=now,
    )
    if not result.success:
        raise RuntimeError(f"failed to record the change request itself: {result.error}")
    answer_id = result.data[0]["answer_id"]
    entities = current_entities(project.events_path)
    answer = entities[answer_id]
    assert isinstance(answer, QuestionAnswer)
    return answer


def unresolved_conflicts_from_events(events_path: Path | str) -> list[dict[str, Any]]:
    """Readiness gate condition 6's own input (decision #19): every
    adjudication still `verdict="contradiction"` and `resolved=False`,
    latest write per `(subject_id, candidate_id)` pair wins — the same
    "latest write wins" fold every other system/meta event in this build
    already uses (`current_approval`, `ppa.agents.modes.review.current_
    review_approval`)."""

    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for event in _read_all_events(Path(events_path)):
        if event.type == EventType.CONFLICT_ADJUDICATED:
            key = (event.after["subject_id"], event.after["candidate_id"])
            latest[key] = event.after
    return [v for v in latest.values() if v["verdict"] == "contradiction" and not v["resolved"]]


def _guidance_style_server(project: Project) -> tuple[Any, list[str]]:
    from ppa.agents.turn import _bind_project, _tool_discovery_hint  # deferred — see ppa.agents.subagents.guidance

    scoped = [_bind_project(t, project) for t in granted_sdk_tools("discovery")]
    server = create_sdk_mcp_server(name="change-tools", tools=scoped)
    allowed = [f"mcp__change-tools__{t.name}" for t in scoped]
    return server, allowed, _tool_discovery_hint(allowed)


async def _run_one_change_turn(*, system_prompt: str, server: Any, allowed_tools: list[str], user_message: str) -> tuple[str, float | None]:
    provider = ModelProvider.from_config(DEFAULT_CONFIG_PATH)
    client = provider.client(system_prompt=system_prompt, allowed_tools=allowed_tools, mcp_servers={"change-tools": server}, tools=["ToolSearch"])
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


def _rewind_workflow(project: Project, *, workflow_state: str) -> str:
    # Deferred import — ppa.orchestrator.loop sits downstream of
    # ppa.agents.registry's own import chain, same reasoning every other
    # deferred import in this module already gives.
    from ppa.orchestrator import loop as orchestrator_loop
    from ppa.workflow import machine as workflow_machine

    workflow_machine.validate_transition(workflow_state, "CHANGE_REQUESTED")
    orchestrator_loop._set_workflow_state(project, "CHANGE_REQUESTED")
    workflow_machine.validate_transition("CHANGE_REQUESTED", REWIND_TARGET)
    orchestrator_loop._set_workflow_state(project, REWIND_TARGET)
    return REWIND_TARGET


def _non_recoverable(description: str) -> AgentResult:
    return AgentResult(
        status=AgentResultStatus.NON_RECOVERABLE, summary=description,
        error=ErrorInfo(category=ErrorCategory.TRANSIENT, code="CHANGE_TURN_FAILED", is_retryable=True, recommended_action=RecoveryAction.RETRY_SAME, description=description),
    )


def run_change_session(
    project: Project, *, change_text: str, actor_id: str, session_id: str, workflow_state: str = "DISCOVERY",
    now: datetime | None = None,
) -> AgentResult:
    """One full change-handling session: record the change, detect
    candidates, run one real turn (adjudicate + record), analyze impact on
    whatever was superseded, and rewind the global workflow state."""

    answer = _record_change_as_answer(project, change_text=change_text, actor_id=actor_id, session_id=session_id, workflow_state=workflow_state, now=now)
    entities_before = current_entities(project.events_path)
    candidates = find_conflict_candidates(answer, entities_before)

    server, allowed_tools, hint = _guidance_style_server(project)
    system_prompt = hint + "\n\n" + _SYSTEM_PROMPT
    candidate_lines = "\n".join(
        f"- subject_id={c.subject_id}, candidate_id={c.candidate_id}: {c.description}" for c in candidates
    ) or "(no conflict candidates were detected against any CONFIRMED entity)"
    user_message = (
        f"Change request: {change_text!r}\n\nConflict candidates found against CONFIRMED entities:\n{candidate_lines}"
    )

    try:
        text, cost = anyio.run(
            functools.partial(_run_one_change_turn, system_prompt=system_prompt, server=server, allowed_tools=allowed_tools, user_message=user_message)
        )
    except Exception as exc:  # pragma: no cover - network/auth failures
        return _non_recoverable(f"Change turn failed to complete: {exc!r}")

    entities_after = current_entities(project.events_path)

    impact_reports: list[ImpactReport] = []
    for event in _read_all_events(project.events_path):
        if event.type == EventType.CONFLICT_ADJUDICATED and event.after["resolved"]:
            subject_id = event.after["subject_id"]
            if subject_id in entities_after:
                impact_reports.append(analyze_impact(subject_id, entities_after))

    rewound_to = _rewind_workflow(project, workflow_state=workflow_state)

    return AgentResult(
        status=AgentResultStatus.OK,
        summary=text or "change handled.",
        data={
            "answer_id": answer.id,
            "candidate_count": len(candidates),
            "impact_reports": [r.model_dump(mode="json") for r in impact_reports],
            "rewound_to": rewound_to,
            "cost_usd": cost,
        },
    )


class ChangeHandlingReport(BaseModel):
    """One completed change-handling round, checked against `tasks/t30_
    review_and_change_handling.md`'s own Done-when boxes."""

    model_config = ConfigDict(extra="forbid")

    new_or_changed_requirement_count: int
    superseded_count: int
    conflict_surfaced: bool
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def _new_or_changed_ids(before: Mapping[str, BaseEntity], after: Mapping[str, BaseEntity], entity_type: EntityType) -> list[str]:
    return [
        eid for eid, entity in after.items()
        if entity_type_for(eid) is entity_type and (eid not in before or before[eid] != entity)
    ]


def evaluate_change_handling(
    entities_before: Mapping[str, BaseEntity],
    entities_after: Mapping[str, BaseEntity],
    events_path: Path | str,
    *,
    watched_candidate: Candidate | None = None,
) -> ChangeHandlingReport:
    """Diffs `entities_before`/`entities_after` (both `ppa.ledger.
    materialize.current_entities`'s own shape) and, separately, reads
    `conflict.adjudicated` events straight from `events_path` — a
    conflict's own verdict lives in the event log, never in an entity
    field. `watched_candidate`, when given, is the specific conflict this
    round must not silently swallow — a `contradicts_self`-shaped fixture
    passes its own known candidate so the check is exact, not a generic
    "some conflict was adjudicated somewhere" pass."""

    violations: list[str] = []

    new_requirements = _new_or_changed_ids(entities_before, entities_after, EntityType.REQUIREMENT)
    if not new_requirements:
        violations.append("no Requirement was created or changed — a change request must produce a new requirement version")

    superseded = [eid for eid in new_requirements if entities_after[eid].status == "SUPERSEDED"]
    # Presence alone (this loop only ever runs over ids drawn from entities_
    # after, so a superseded id trivially still resolves) is the real
    # guarantee event-sourcing already gives for free — T07's own
    # never-delete, byte-identical-rebuild property. Nothing here re-proves
    # that; it only counts how many of this round's own changes were
    # supersessions, for the report's own record.

    adjudications = [e.after for e in _read_all_events(Path(events_path)) if e.type == EventType.CONFLICT_ADJUDICATED]

    conflict_surfaced = True
    if watched_candidate is not None:
        conflict_surfaced = any(
            a["subject_id"] == watched_candidate.subject_id and a["candidate_id"] == watched_candidate.candidate_id
            for a in adjudications
        )
        if not conflict_surfaced:
            violations.append(
                f"{watched_candidate.subject_id}/{watched_candidate.candidate_id}: conflict was never "
                "adjudicated — silently dropped rather than surfaced"
            )

    return ChangeHandlingReport(
        new_or_changed_requirement_count=len(new_requirements),
        superseded_count=len(superseded),
        conflict_surfaced=conflict_surfaced,
        violations=violations,
    )
