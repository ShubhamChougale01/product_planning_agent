"""The outer loop (T21, DESIGN.md §2.2, §2.11).

**There are two loops.** The inner loop belongs to the SDK — model emits
`tool_use`, the runtime executes it, results return to context, the model
reasons again, until `end_turn`. We never reimplement it (this task's own
stated trap). **This module is the outer loop** — driven by workflow state
and the readiness gate, never by anything the model says. Task completion is
decided by `check_readiness()` (T10) alone; an agent that says "I'm done"
with blocking items still open simply gets classified and routed like any
other turn.

One call to `run_turn` is one outer-loop iteration — DESIGN.md §2.11's
eleven numbered steps, 1 through 10 (step 11, "loop," is `run_session`'s
job: call `run_turn` again). Each iteration opens exactly one transaction
(`txn.begin`/`txn.commit`/`txn.abort`), and that transaction's `txn_id` is
also what `ppa.orchestrator.context` groups history into "rounds" by — the
outer loop and the context it assembles agree on what a round is by
construction, not by convention.

**Iteration caps are runaway guards only.** `run_session` stops at
`iteration_cap` and writes `anomaly.loop_cap_reached` — that is never
recorded as completion, only as an anomaly to investigate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ppa.agents.base import Agent, AgentResult, AgentResultStatus
from ppa.config.profiles import UserProfile
from ppa.engines.readiness import Blocker, check_readiness
from ppa.ledger.events import EventType
from ppa.ledger.gitops import commit as git_commit
from ppa.ledger.gitops import commit_turn
from ppa.ledger.materialize import current_entities, rebuild_all
from ppa.ledger.project import Project
from ppa.ledger.store import (
    allocate_id,
    append_event,
    ledger_version,
    path_lock,
    read_project_meta,
    write_project_meta,
)
from ppa.orchestrator.context import (
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_RECENT_ROUNDS,
    assemble_context,
    events_for_txn,
)
from ppa.orchestrator.dispatch import invoke_agent, select_agent
from ppa.orchestrator.preconditions import validate_discovery_state
from ppa.tools.dispatch import InvocationContext
from ppa.workflow import machine as workflow_machine

logger = logging.getLogger(__name__)

TERMINAL_STATE = "COMPLETE"
DEFAULT_ITERATION_CAP = 25
"""A runaway guard, not a design target — DESIGN.md §2.11: "reaching the cap
writes an anomaly event and escalates. It never counts as completion.\""""

DEFAULT_RETRY_BUDGET = 3
"""DESIGN.md §2.14's own number for bounded retry ("budget of 3 for
TRANSIENT with exponential backoff"), reused here for `RECOVERABLE` at the
orchestrator level. The actual backoff policy is T32's job
(`ppa/recovery/retry.py`) — this is only the attempt count, so `RECOVERABLE`
cannot spin forever inside a single `run_turn` call."""

_ORCHESTRATOR_ACTOR = "agent:orchestrator"


class StepOutcome(str, Enum):
    """What one `run_turn` call decided. Distinct from `AgentResultStatus`
    (T20) — that classifies the *agent's* result; this classifies what the
    *outer loop* did about it."""

    COMPLETE = "COMPLETE"
    ROUTED_BACK = "ROUTED_BACK"
    ADVANCED = "ADVANCED"
    TRANSITIONED = "TRANSITIONED"
    SUSPENDED = "SUSPENDED"
    ESCALATED = "ESCALATED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class StepResult(BaseModel):
    """One `run_turn` call's outcome."""

    model_config = ConfigDict(extra="forbid")

    outcome: StepOutcome
    workflow_state: str
    """Workflow state *after* this step — what the next `run_turn` call
    should be given."""
    summary: str
    blockers: list[Blocker] = Field(default_factory=list)
    agent_result: AgentResult | None = None
    committed: bool = False
    commit_message: str | None = None
    txn_id: str | None = None
    context_tokens: int | None = None
    attempts: int = 1


class SessionResult(BaseModel):
    """What `run_session` returns — the full record of a bounded run of
    `run_turn` calls."""

    model_config = ConfigDict(extra="forbid")

    complete: bool
    stopped_reason: str
    """One of `"complete"`, `"suspended"`, `"escalated"`, `"not_implemented"`,
    `"loop_cap_reached"`."""
    steps: list[StepResult] = Field(default_factory=list)
    iterations: int = 0


# ---------------------------------------------------------------------------
# Transaction bookkeeping — DESIGN.md §2.14. `txn.begin`/`txn.commit`/
# `txn.abort` are the whole rollback mechanism: an aborted transaction's
# events are excluded from materialization by `ppa.ledger.materialize`
# (nothing invalid is ever committed, so nothing ever needs undoing).
# ---------------------------------------------------------------------------


def _write_txn_event(
    project: Project,
    event_type: EventType,
    txn_id: str,
    *,
    workflow_state: str,
    session_id: str,
    actor_id: str,
    now: datetime,
    reason: str,
) -> str:
    return append_event(
        dict(
            ts=now,
            type=event_type,
            entity_id=None,
            actor_id=actor_id,
            actor_role="agent",
            agent_name="orchestrator",
            workflow_state=workflow_state,
            txn_id=txn_id,
            source="orchestrator_loop",
            reason=reason,
            before=None,
            after=None,
            session_id=session_id,
        ),
        project.events_path,
    )


def _open_txn(
    project: Project, *, workflow_state: str, session_id: str, actor_id: str, now: datetime
) -> str:
    txn_id = allocate_id("TXN", project.events_path)
    _write_txn_event(
        project,
        EventType.TXN_BEGIN,
        txn_id,
        workflow_state=workflow_state,
        session_id=session_id,
        actor_id=actor_id,
        now=now,
        reason="turn started",
    )
    return txn_id


def _abort_txn(
    project: Project,
    txn_id: str,
    *,
    workflow_state: str,
    session_id: str,
    actor_id: str,
    now: datetime,
    reason: str,
) -> None:
    _write_txn_event(
        project,
        EventType.TXN_ABORT,
        txn_id,
        workflow_state=workflow_state,
        session_id=session_id,
        actor_id=actor_id,
        now=now,
        reason=reason,
    )


def _commit_txn(
    project: Project, txn_id: str, *, workflow_state: str, session_id: str, actor_id: str, now: datetime
) -> None:
    _write_txn_event(
        project,
        EventType.TXN_COMMIT,
        txn_id,
        workflow_state=workflow_state,
        session_id=session_id,
        actor_id=actor_id,
        now=now,
        reason="turn committed",
    )


def _set_workflow_state(project: Project, new_state: str) -> None:
    """`workflow_state` lives only in `project.json` (no dedicated event
    type exists for a pure state change — `ppa.ledger.project.create_project`
    already sets it the same direct way, with no accompanying event beyond
    `project.created`), under the same per-path lock every other
    `project.json` writer uses."""

    with path_lock(project.events_path):
        meta = read_project_meta(project.events_path)
        meta["workflow_state"] = new_state
        write_project_meta(project.events_path, meta)


def _read_workflow_state(project: Project) -> str:
    meta = read_project_meta(project.events_path)
    return meta.get("workflow_state", project.workflow_state)


def _finalize_turn(
    project: Project,
    result: AgentResult,
    *,
    event_workflow_state: str,
    result_workflow_state: str,
    txn_id: str,
    session_id: str,
    actor_id: str,
    now: datetime,
    attempts: int,
    outcome: StepOutcome,
) -> StepResult:
    """Step 10's OK/PARTIAL branch: commit the transaction, regenerate the
    materialized entity snapshot, and produce one git commit summarizing
    exactly this round's events — `ppa.ledger.gitops.commit_turn` derives
    the message from the events themselves, never a caller-supplied string."""

    _commit_txn(
        project,
        txn_id,
        workflow_state=event_workflow_state,
        session_id=session_id,
        actor_id=actor_id,
        now=now,
    )
    rebuild_all(project.events_path)
    events_this_round = events_for_txn(project.events_path, txn_id)
    message = commit_turn(project.path, events_this_round)

    return StepResult(
        outcome=outcome,
        workflow_state=result_workflow_state,
        summary=result.summary,
        agent_result=result,
        committed=message is not None,
        commit_message=message,
        txn_id=txn_id,
        attempts=attempts,
    )


def _route_back_to_discovery(
    project: Project,
    blockers: Sequence[Blocker],
    *,
    session_id: str,
    actor_id: str,
    now: datetime,
) -> StepResult:
    """`advance_to_planning`'s own failure branch, per this task's worked
    pseudocode: preconditions failed, so workflow state moves back to
    `DISCOVERY` — no agent is ever invoked for this decision."""

    current_state = _read_workflow_state(project)
    workflow_machine.validate_transition(current_state, "DISCOVERY")
    _set_workflow_state(project, "DISCOVERY")

    message = "routed back to DISCOVERY: " + "; ".join(b.description for b in blockers)
    git_commit(project.path, message, paths=[".planning/project.json"])

    return StepResult(
        outcome=StepOutcome.ROUTED_BACK,
        workflow_state="DISCOVERY",
        summary=message,
        blockers=list(blockers),
    )


def _handle_workflow_transition(
    project: Project,
    result: AgentResult,
    *,
    workflow_state: str,
    txn_id: str,
    session_id: str,
    actor_id: str,
    now: datetime,
    attempts: int,
) -> StepResult:
    """`WORKFLOW_TRANSITION -> update state, loop` (DESIGN.md §2.11 step
    10). `result.data["target_state"]` names where to; legality is still
    checked against `ppa/workflow/transitions.yaml`, never trusted from the
    agent alone. Mandatory validation is not bypassed by requesting
    `DISCOVERY_VALIDATED` this way either — the very next `run_turn` call,
    now sitting at `DISCOVERY_VALIDATED`, re-runs `validate_discovery_state`
    before it will invoke Planning (step 4), so a transition an agent
    requested without real justification simply bounces back on the
    following iteration."""

    target = result.data.get("target_state") if isinstance(result.data, dict) else None
    if not target:
        _abort_txn(
            project,
            txn_id,
            workflow_state=workflow_state,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            reason="WORKFLOW_TRANSITION with no target_state in AgentResult.data",
        )
        raise ValueError(
            "AgentResultStatus.WORKFLOW_TRANSITION requires result.data['target_state']"
        )

    workflow_machine.validate_transition(workflow_state, target)
    _set_workflow_state(project, target)

    return _finalize_turn(
        project,
        result,
        event_workflow_state=workflow_state,
        result_workflow_state=target,
        txn_id=txn_id,
        session_id=session_id,
        actor_id=actor_id,
        now=now,
        attempts=attempts,
        outcome=StepOutcome.TRANSITIONED,
    )


def _handle_result(
    project: Project,
    result: AgentResult,
    *,
    workflow_state: str,
    txn_id: str,
    session_id: str,
    actor_id: str,
    now: datetime,
    attempts: int,
) -> StepResult:
    """Step 9/10 — classify the seven `AgentResultStatus` outcomes and act.
    Every member is handled explicitly; anything else raises rather than
    falling through silently."""

    status = result.status

    if status in (AgentResultStatus.OK, AgentResultStatus.PARTIAL):
        return _finalize_turn(
            project,
            result,
            event_workflow_state=workflow_state,
            result_workflow_state=workflow_state,
            txn_id=txn_id,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            attempts=attempts,
            outcome=StepOutcome.ADVANCED,
        )

    if status is AgentResultStatus.HUMAN_INPUT_REQUIRED:
        # Real progress this turn (e.g. the question itself, already an
        # event) must persist — commit, then suspend. Not an error.
        step = _finalize_turn(
            project,
            result,
            event_workflow_state=workflow_state,
            result_workflow_state=workflow_state,
            txn_id=txn_id,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            attempts=attempts,
            outcome=StepOutcome.SUSPENDED,
        )
        return step

    if status is AgentResultStatus.WORKFLOW_TRANSITION:
        return _handle_workflow_transition(
            project,
            result,
            workflow_state=workflow_state,
            txn_id=txn_id,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            attempts=attempts,
        )

    if status is AgentResultStatus.RECOVERABLE:
        # `run_turn`'s own retry loop only reaches here once the budget is
        # exhausted — a still-retryable RECOVERABLE never gets this far.
        _abort_txn(
            project,
            txn_id,
            workflow_state=workflow_state,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            reason=f"retry budget exhausted after {attempts} attempts: {result.summary}",
        )
        return StepResult(
            outcome=StepOutcome.ESCALATED,
            workflow_state=workflow_state,
            summary=f"retry budget exhausted: {result.summary}",
            agent_result=result,
            txn_id=txn_id,
            attempts=attempts,
        )

    if status is AgentResultStatus.NON_RECOVERABLE:
        _abort_txn(
            project,
            txn_id,
            workflow_state=workflow_state,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            reason=f"NON_RECOVERABLE: {result.summary}",
        )
        return StepResult(
            outcome=StepOutcome.ESCALATED,
            workflow_state=workflow_state,
            summary=result.summary,
            agent_result=result,
            txn_id=txn_id,
            attempts=attempts,
        )

    if status is AgentResultStatus.NOT_IMPLEMENTED:
        _abort_txn(
            project,
            txn_id,
            workflow_state=workflow_state,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            reason="agent responded NOT_IMPLEMENTED — nothing to commit",
        )
        return StepResult(
            outcome=StepOutcome.NOT_IMPLEMENTED,
            workflow_state=workflow_state,
            summary=result.summary,
            agent_result=result,
            txn_id=txn_id,
            attempts=attempts,
        )

    raise AssertionError(f"unhandled AgentResultStatus: {status!r}")  # pragma: no cover


def run_turn(
    project: Project,
    profile: UserProfile,
    *,
    session_id: str,
    actor_id: str = _ORCHESTRATOR_ACTOR,
    now: datetime | None = None,
    recent_rounds: int = DEFAULT_RECENT_ROUNDS,
    retry_budget: int = DEFAULT_RETRY_BUDGET,
    confirmed_areas: set[str] | None = None,
    unresolved_conflicts: Sequence[Any] | None = None,
    review_approved: bool = False,
) -> StepResult:
    """One outer-loop iteration — DESIGN.md §2.11 steps 1-10.

    `confirmed_areas`/`unresolved_conflicts`/`review_approved` are threaded
    straight through to `check_readiness`, unchanged from decision #19's own
    pattern (`ppa/engines/readiness.py`): nothing before T30 produces them
    for real, so they stay caller-supplied, defaulting to the same
    fail-closed direction `check_readiness` itself uses.
    """

    now = now or datetime.now(timezone.utc)

    # --- 1. load ledger -> digest, workflow state, ledger_version ---
    workflow_state = _read_workflow_state(project)
    entities = current_entities(project.events_path)
    ledger_version_before = ledger_version(project.events_path)

    # --- 2/3. evaluate readiness gate; complete only at the terminal state.
    # Decided by check_readiness() alone — no agent has been invoked yet,
    # so nothing here can possibly read model output. ---
    ready, _gate_blockers = check_readiness(
        entities,
        profile,
        confirmed_areas=confirmed_areas,
        unresolved_conflicts=unresolved_conflicts,
        review_approved=review_approved,
    )
    if ready and workflow_state == TERMINAL_STATE:
        return StepResult(
            outcome=StepOutcome.COMPLETE,
            workflow_state=workflow_state,
            summary="readiness gate passed at the terminal state",
        )

    # --- 4. validate preconditions for the next state (deterministic).
    # Only Discovery's own exit is gated in v1 — DESIGN.md §2.5: "v1 runs
    # DISCOVERY -> DISCOVERY_VALIDATED and stops there." ---
    if workflow_state == "DISCOVERY_VALIDATED":
        precondition = validate_discovery_state(entities, profile, confirmed_areas=confirmed_areas)
        if not precondition.ok:
            return _route_back_to_discovery(
                project, precondition.blockers, session_id=session_id, actor_id=actor_id, now=now
            )

    # --- 5. select agent from workflow state (table lookup) ---
    agent: Agent = select_agent(workflow_state)

    # --- context assembly: logged for cost instrumentation (T35), never
    # itself handed to the agent yet — no concrete Agent.invoke() consumes
    # assembled context until a later task gives it a real prompt to put it
    # in. The raw ledger is never part of it either way (see
    # ppa.orchestrator.context's own module docstring). ---
    bundle = assemble_context(project, entities, now=now, recent_rounds=recent_rounds)
    logger.info(
        "turn context assembled: ~%d tokens (%d recent round(s), %d older)",
        bundle.token_estimate,
        bundle.recent_round_count,
        bundle.older_round_count,
    )
    if bundle.token_estimate > DEFAULT_MAX_CONTEXT_TOKENS:
        logger.warning(
            "assembled context (~%d tokens) exceeds the configured budget (%d)",
            bundle.token_estimate,
            DEFAULT_MAX_CONTEXT_TOKENS,
        )

    # --- 6. open transaction; 7/8. invoke agent -> AgentResult, with a
    # bounded local retry for RECOVERABLE (DESIGN.md §2.14's own "budget of
    # 3," applied here at the orchestrator level). ---
    attempts = 1
    txn_id = _open_txn(project, workflow_state=workflow_state, session_id=session_id, actor_id=actor_id, now=now)
    ctx = InvocationContext(
        agent_id=agent.id,
        workflow_state=workflow_state,
        session_id=session_id,
        audit_path=project.audit_path,
        ledger_version=ledger_version_before,
        txn_id=txn_id,
    )
    result = invoke_agent(agent, ctx)

    while result.status is AgentResultStatus.RECOVERABLE and attempts < retry_budget:
        _abort_txn(
            project,
            txn_id,
            workflow_state=workflow_state,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            reason=f"attempt {attempts} RECOVERABLE: {result.summary}",
        )
        attempts += 1
        txn_id = _open_txn(
            project, workflow_state=workflow_state, session_id=session_id, actor_id=actor_id, now=now
        )
        ctx = InvocationContext(
            agent_id=agent.id,
            workflow_state=workflow_state,
            session_id=session_id,
            audit_path=project.audit_path,
            ledger_version=ledger_version_before,
            txn_id=txn_id,
        )
        result = invoke_agent(agent, ctx)

    # --- 9/10. classify and act ---
    step = _handle_result(
        project,
        result,
        workflow_state=workflow_state,
        txn_id=txn_id,
        session_id=session_id,
        actor_id=actor_id,
        now=now,
        attempts=attempts,
    )
    step.context_tokens = bundle.token_estimate
    return step


_STOPPING_OUTCOMES: dict[StepOutcome, str] = {
    StepOutcome.COMPLETE: "complete",
    StepOutcome.SUSPENDED: "suspended",
    StepOutcome.ESCALATED: "escalated",
    StepOutcome.NOT_IMPLEMENTED: "not_implemented",
}
"""`ROUTED_BACK`, `ADVANCED` and `TRANSITIONED` are not here — all three
mean real progress happened and `run_session` should call `run_turn` again
(step 11, "loop")."""


def _write_loop_cap_anomaly(
    project: Project, *, session_id: str, actor_id: str, now: datetime, iteration_cap: int
) -> str:
    workflow_state = _read_workflow_state(project)
    return append_event(
        dict(
            ts=now,
            type=EventType.ANOMALY_LOOP_CAP_REACHED,
            entity_id=None,
            actor_id=actor_id,
            actor_role="agent",
            agent_name="orchestrator",
            workflow_state=workflow_state,
            txn_id=None,
            source="orchestrator_loop",
            reason=f"session iteration cap ({iteration_cap}) reached — runaway guard, not completion",
            before=None,
            after=None,
            session_id=session_id,
        ),
        project.events_path,
    )


def run_session(
    project: Project,
    profile: UserProfile,
    *,
    session_id: str,
    actor_id: str = _ORCHESTRATOR_ACTOR,
    iteration_cap: int = DEFAULT_ITERATION_CAP,
    now: datetime | None = None,
    recent_rounds: int = DEFAULT_RECENT_ROUNDS,
    retry_budget: int = DEFAULT_RETRY_BUDGET,
    confirmed_areas: set[str] | None = None,
    unresolved_conflicts: Sequence[Any] | None = None,
    review_approved: bool = False,
) -> SessionResult:
    """Step 11: call `run_turn` again, until a stopping outcome or the
    iteration cap. The cap is a runaway guard only — reaching it writes
    `anomaly.loop_cap_reached` and is never `complete=True`."""

    steps: list[StepResult] = []
    current = project

    for iteration in range(1, iteration_cap + 1):
        step = run_turn(
            current,
            profile,
            session_id=session_id,
            actor_id=actor_id,
            now=now,
            recent_rounds=recent_rounds,
            retry_budget=retry_budget,
            confirmed_areas=confirmed_areas,
            unresolved_conflicts=unresolved_conflicts,
            review_approved=review_approved,
        )
        steps.append(step)
        current = current.model_copy(update={"workflow_state": step.workflow_state})

        stopped_reason = _STOPPING_OUTCOMES.get(step.outcome)
        if stopped_reason is not None:
            return SessionResult(
                complete=step.outcome is StepOutcome.COMPLETE,
                stopped_reason=stopped_reason,
                steps=steps,
                iterations=iteration,
            )

    _write_loop_cap_anomaly(
        current, session_id=session_id, actor_id=actor_id, now=now or datetime.now(timezone.utc), iteration_cap=iteration_cap
    )
    return SessionResult(
        complete=False,
        stopped_reason="loop_cap_reached",
        steps=steps,
        iterations=iteration_cap,
    )
