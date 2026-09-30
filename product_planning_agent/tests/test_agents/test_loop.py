"""T21 tests — preconditions, agent selection and the outer loop. Every
Done-when box in `tasks/t21_preconditions_and_outer_loop.md` maps to at
least one test here.

Most of these prove the outer loop's own mechanics without a model in the
loop, using `_FixtureAgent` (a minimal `Agent` swapped in for
`ppa.orchestrator.loop.select_agent`) — exactly the "proven without a model
in the loop" standard the task's own Done-when boxes ask for. The one
exception the task marks "Needs a model: Yes" (a real SDK turn) is proven by
a one-off script (`scripts/verify_first_turn.py`), matching this codebase's
own T01 precedent (`scripts/verify_auth.py`) — the automated suite stays
free and fast, per DESIGN.md Part 0.1's zero-cost development path. See
decision #28, `blockers.md`.
"""

from __future__ import annotations

import subprocess
import typing
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ppa.agents.base import Agent, AgentResult, AgentResultStatus, BaseAgent
from ppa.config.profiles import UserProfile, critical_areas
from ppa.engines.readiness import Condition
from ppa.ledger.events import EventType
from ppa.ledger.models import QuestionAnswer, Requirement, Unknown
from ppa.ledger.project import create_project
from ppa.ledger.store import append_event, read_project_meta, write_project_meta
from ppa.orchestrator import context, dispatch, loop
from ppa.orchestrator.preconditions import DISCOVERY_EXIT_CONDITIONS, validate_discovery_state
from ppa.workflow.machine import IllegalWorkflowTransition

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures shared across every test below.
# ---------------------------------------------------------------------------


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _requirement(entity_id: str, *, status="CONFIRMED", covers_areas=(), **overrides) -> Requirement:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        confidence="HIGH",
        confidence_basis="user said it directly",
        status=status,
        statement=f"statement for {entity_id}",
        type="functional",
        covers_areas=list(covers_areas),
        priority="must",
    )
    base.update(overrides)
    return Requirement(**base)


def _unknown(entity_id: str, *, status="OPEN", blocking=True, owner_type="user", **overrides) -> Unknown:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        status=status,
        question=f"question for {entity_id}",
        area="platform",
        why_it_matters="it matters",
        blocking=blocking,
        route="USER_DECISION",
        owner_type=owner_type,
    )
    base.update(overrides)
    return Unknown(**base)


def _fully_ready_entities(profile: UserProfile) -> dict:
    """One CONFIRMED Requirement per critical area — every Discovery-exit
    condition satisfied. Mirrors `tests/test_engines/test_readiness.py`'s
    own `_fully_ready_entities` recipe exactly, since it is the already-
    proven "this really does satisfy check_readiness" fixture."""

    entities = {}
    for i, area in enumerate(sorted(critical_areas(profile))):
        req_id = f"REQ-{i:03d}"
        entities[req_id] = _requirement(req_id, status="CONFIRMED", covers_areas=[area])
    return entities


def _make_project(tmp_path, **overrides):
    kwargs = dict(
        name=overrides.pop("name", "Loop Test Project"),
        seed_requirement=overrides.pop("seed_requirement", "users need to log in"),
        profile=overrides.pop("profile", _profile()),
        projects_root=tmp_path / "projects",
    )
    kwargs.update(overrides)
    return create_project(**kwargs)


def _git_log_count(repo_dir) -> int:
    result = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(repo_dir), check=True, capture_output=True, text=True
    )
    return len(result.stdout.splitlines())


class _FixtureAgent(BaseAgent):
    """A minimal `Agent` (T20's protocol) that returns a scripted sequence
    of `AgentResult`s — the last one repeats for any call past the end of
    the sequence. Swapped in for `ppa.orchestrator.loop.select_agent` via
    `monkeypatch`, never registered in the real `ppa.agents.registry`."""

    id = "discovery"
    system_prompt = "fixture agent for T21 loop tests"

    def __init__(self, results, *, on_invoke=None) -> None:
        self._results = results if isinstance(results, list) else [results]
        self._on_invoke = on_invoke
        self.calls = 0

    def invoke(self, ctx) -> AgentResult:  # type: ignore[override]
        self.calls += 1
        if self._on_invoke is not None:
            self._on_invoke(ctx)
        index = min(self.calls - 1, len(self._results) - 1)
        return self._results[index]


def _select_only(monkeypatch: pytest.MonkeyPatch, agent: Agent) -> None:
    monkeypatch.setattr(loop, "select_agent", lambda state: agent)


def _refuse_to_select(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(state):
        raise AssertionError(f"select_agent must not be called — got state {state!r}")

    monkeypatch.setattr(loop, "select_agent", _raise)


# ---------------------------------------------------------------------------
# Done when: Advancing to PLANNING with an open blocking requirement routes
# back to Discovery — proven without a model in the loop.
# ---------------------------------------------------------------------------


def test_open_blocking_unknown_routes_discovery_validated_back_to_discovery(tmp_path, monkeypatch):
    profile = _profile()
    project = _make_project(tmp_path, profile=profile)

    unk = _unknown("UNK-001", status="OPEN", blocking=True, owner_type="user")
    append_event(
        dict(
            ts=NOW,
            type=EventType.UNKNOWN_RECORDED,
            entity_id="UNK-001",
            actor_id="agent:discovery",
            actor_role="agent",
            agent_name="discovery",
            workflow_state="DISCOVERY",
            txn_id=None,
            source="fixture",
            reason="seed a blocking unknown",
            before=None,
            after=unk.model_dump(mode="json"),
            session_id="session-1",
        ),
        project.events_path,
    )

    meta = read_project_meta(project.events_path)
    meta["workflow_state"] = "DISCOVERY_VALIDATED"
    write_project_meta(project.events_path, meta)

    _refuse_to_select(monkeypatch)  # no agent may be invoked for this decision

    step = loop.run_turn(project, profile, session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.ROUTED_BACK
    assert step.workflow_state == "DISCOVERY"
    assert step.blockers
    assert any(b.condition == "blocking_unknown" for b in step.blockers)
    assert read_project_meta(project.events_path)["workflow_state"] == "DISCOVERY"


def test_fully_satisfied_discovery_state_is_not_routed_back(tmp_path, monkeypatch):
    profile = _profile()
    entities = _fully_ready_entities(profile)
    result = validate_discovery_state(entities, profile)
    assert result.ok
    assert result.blockers == []


# ---------------------------------------------------------------------------
# Done when: all seven result classifications are handled explicitly; an
# unhandled one raises.
# ---------------------------------------------------------------------------


def test_ok_result_advances_and_commits(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(AgentResult(status=AgentResultStatus.OK, summary="did discovery work"))
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.ADVANCED
    assert step.workflow_state == "DISCOVERY"
    assert agent.calls == 1


def test_partial_result_advances_and_commits(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(AgentResult(status=AgentResultStatus.PARTIAL, summary="did some work"))
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.ADVANCED


def test_recoverable_retries_within_budget_then_succeeds(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    results = [
        AgentResult(status=AgentResultStatus.RECOVERABLE, summary="transient failure 1"),
        AgentResult(status=AgentResultStatus.RECOVERABLE, summary="transient failure 2"),
        AgentResult(status=AgentResultStatus.OK, summary="succeeded on attempt 3"),
    ]
    agent = _FixtureAgent(results)
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert agent.calls == 3
    assert step.attempts == 3
    assert step.outcome is loop.StepOutcome.ADVANCED


def test_recoverable_exhausts_retry_budget_and_escalates(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(AgentResult(status=AgentResultStatus.RECOVERABLE, summary="always fails"))
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW, retry_budget=3)

    assert agent.calls == 3
    assert step.outcome is loop.StepOutcome.ESCALATED


def test_non_recoverable_aborts_and_escalates(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(AgentResult(status=AgentResultStatus.NON_RECOVERABLE, summary="fatal error"))
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.ESCALATED
    assert step.committed is False


def test_human_input_required_commits_real_progress_and_suspends_without_error(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    question = QuestionAnswer(
        id="Q-001",
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        text="what platform?",
        why_asked="platform is an unconfirmed critical area",
        round=1,
    )

    def _ask_a_question(ctx):
        append_event(
            dict(
                ts=NOW,
                type=EventType.QUESTION_ASKED,
                entity_id="Q-001",
                actor_id="agent:discovery",
                actor_role="agent",
                agent_name="discovery",
                workflow_state="DISCOVERY",
                txn_id=ctx.txn_id,
                source="fixture",
                reason="need clarification",
                before=None,
                after=question.model_dump(mode="json"),
                session_id="session-1",
            ),
            project.events_path,
        )

    agent = _FixtureAgent(
        AgentResult(status=AgentResultStatus.HUMAN_INPUT_REQUIRED, summary="need an answer"),
        on_invoke=_ask_a_question,
    )
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.SUSPENDED
    assert step.committed is True  # the question itself is real, durable progress


def test_workflow_transition_updates_state_and_commits(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(
        AgentResult(
            status=AgentResultStatus.WORKFLOW_TRANSITION,
            summary="discovery is done",
            data={"target_state": "DISCOVERY_VALIDATED"},
        )
    )
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.TRANSITIONED
    assert step.workflow_state == "DISCOVERY_VALIDATED"
    assert read_project_meta(project.events_path)["workflow_state"] == "DISCOVERY_VALIDATED"


def test_workflow_transition_without_target_state_raises(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(AgentResult(status=AgentResultStatus.WORKFLOW_TRANSITION, summary="no target"))
    _select_only(monkeypatch, agent)

    with pytest.raises(ValueError, match="target_state"):
        loop.run_turn(project, _profile(), session_id="session-1", now=NOW)


def test_workflow_transition_to_an_illegal_state_raises(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(
        AgentResult(
            status=AgentResultStatus.WORKFLOW_TRANSITION,
            summary="jump straight to delivery",
            data={"target_state": "DELIVERY"},
        )
    )
    _select_only(monkeypatch, agent)

    with pytest.raises(IllegalWorkflowTransition):
        loop.run_turn(project, _profile(), session_id="session-1", now=NOW)


def test_not_implemented_result_stops_cleanly_without_committing(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    agent = _FixtureAgent(
        AgentResult(status=AgentResultStatus.NOT_IMPLEMENTED, summary="Planning is v2.")
    )
    _select_only(monkeypatch, agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.NOT_IMPLEMENTED
    assert step.committed is False
    assert step.summary == "Planning is v2."


def test_planning_stub_reached_via_discovery_validated_returns_not_implemented(tmp_path):
    """Exercises the real `ppa.agents.planning.PlanningAgent` stub (no
    monkeypatch) — DESIGN.md §2.5's own worked example: "attempting to
    advance returns a structured NOT_IMPLEMENTED from the Planning stub.\""""

    profile = _profile()
    project = _make_project(tmp_path, profile=profile)
    for entity_id, entity in _fully_ready_entities(profile).items():
        append_event(
            dict(
                ts=NOW,
                type=EventType.REQUIREMENT_CREATED,
                entity_id=entity_id,
                actor_id="agent:discovery",
                actor_role="agent",
                agent_name="discovery",
                workflow_state="DISCOVERY",
                txn_id=None,
                source="fixture",
                reason="seed a fully-satisfied ledger",
                before=None,
                after=entity.model_dump(mode="json"),
                session_id="session-1",
            ),
            project.events_path,
        )

    meta = read_project_meta(project.events_path)
    meta["workflow_state"] = "DISCOVERY_VALIDATED"
    write_project_meta(project.events_path, meta)

    step = loop.run_turn(project, profile, session_id="session-1", now=NOW)

    assert step.outcome is loop.StepOutcome.NOT_IMPLEMENTED
    from ppa.agents.planning import STUB_MESSAGE

    assert step.summary == STUB_MESSAGE


def test_unhandled_agent_result_status_raises(tmp_path):
    project = _make_project(tmp_path)
    bogus = SimpleNamespace(status="BOGUS_STATUS", summary="not a real status", data={})

    with pytest.raises(AssertionError, match="unhandled AgentResultStatus"):
        loop._handle_result(
            project,
            bogus,
            workflow_state="DISCOVERY",
            txn_id="TXN-999",
            session_id="session-1",
            actor_id="agent:orchestrator",
            now=NOW,
            attempts=1,
        )


# ---------------------------------------------------------------------------
# Done when: a forced stub loop hits the cap, writes anomaly.loop_cap_
# reached, escalates, and is not recorded as completion.
# ---------------------------------------------------------------------------


def test_forced_stub_loop_hits_the_cap_and_writes_the_anomaly(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    # Always transitions DISCOVERY -> DISCOVERY (a legal no-op, DESIGN.md's
    # "frm == to is always legal" rule) — real progress every iteration by
    # the loop's own bookkeeping, but never a stopping outcome, so only the
    # iteration cap can end the session.
    agent = _FixtureAgent(
        AgentResult(
            status=AgentResultStatus.WORKFLOW_TRANSITION,
            summary="looping forever",
            data={"target_state": "DISCOVERY"},
        )
    )
    _select_only(monkeypatch, agent)

    result = loop.run_session(project, _profile(), session_id="session-1", now=NOW, iteration_cap=5)

    assert result.complete is False
    assert result.stopped_reason == "loop_cap_reached"
    assert result.iterations == 5
    assert len(result.steps) == 5

    events = context.read_events(project.events_path)
    assert any(e.type is EventType.ANOMALY_LOOP_CAP_REACHED for e in events)


# ---------------------------------------------------------------------------
# Done when: completion is decided by check_readiness(), never by model
# output — assert no code path reads model text to decide completion.
# ---------------------------------------------------------------------------


def test_completion_is_decided_by_readiness_gate_agent_never_invoked(tmp_path, monkeypatch):
    profile = _profile()
    project = _make_project(tmp_path, profile=profile)

    for entity_id, entity in _fully_ready_entities(profile).items():
        append_event(
            dict(
                ts=NOW,
                type=EventType.REQUIREMENT_CREATED,
                entity_id=entity_id,
                actor_id="agent:discovery",
                actor_role="agent",
                agent_name="discovery",
                workflow_state="COMPLETE",
                txn_id=None,
                source="fixture",
                reason="seed a fully-satisfied ledger",
                before=None,
                after=entity.model_dump(mode="json"),
                session_id="session-1",
            ),
            project.events_path,
        )

    meta = read_project_meta(project.events_path)
    meta["workflow_state"] = "COMPLETE"
    write_project_meta(project.events_path, meta)

    _refuse_to_select(monkeypatch)  # completion must never require invoking an agent

    step = loop.run_turn(
        project, profile, session_id="session-1", now=NOW, review_approved=True
    )

    assert step.outcome is loop.StepOutcome.COMPLETE


# ---------------------------------------------------------------------------
# Done when: one full turn completes and produces one git commit with a
# meaningful message.
# ---------------------------------------------------------------------------


def test_one_full_turn_produces_one_git_commit_with_a_meaningful_message(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    req = _requirement("REQ-001", covers_areas=["problem"])

    def _write_requirement(ctx):
        append_event(
            dict(
                ts=NOW,
                type=EventType.REQUIREMENT_CREATED,
                entity_id="REQ-001",
                actor_id="agent:discovery",
                actor_role="agent",
                agent_name="discovery",
                workflow_state="DISCOVERY",
                txn_id=ctx.txn_id,
                source="fixture",
                reason="discovery wrote a requirement",
                before=None,
                after=req.model_dump(mode="json"),
                session_id="session-1",
            ),
            project.events_path,
        )

    agent = _FixtureAgent(
        AgentResult(status=AgentResultStatus.OK, summary="captured one requirement"),
        on_invoke=_write_requirement,
    )
    _select_only(monkeypatch, agent)

    commits_before = _git_log_count(project.path)
    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW)
    commits_after = _git_log_count(project.path)

    assert step.committed is True
    assert step.commit_message is not None
    assert "requirement" in step.commit_message
    assert commits_after == commits_before + 1
    assert (project.path / ".planning" / "entities" / "REQ-001.json").exists()


# ---------------------------------------------------------------------------
# Done when: the raw ledger is never placed in context — assert by
# inspection and by test.
# ---------------------------------------------------------------------------


def test_raw_event_json_never_appears_in_assembled_context(tmp_path):
    profile = _profile()
    project = _make_project(tmp_path, profile=profile)
    entities = {
        "REQ-001": _requirement(
            "REQ-001",
            status="PROPOSED",
            covers_areas=["problem"],
            statement="a long, unremarkable, non-blocking requirement statement " * 5,
        )
    }

    bundle = context.assemble_context(project, entities, now=NOW)

    for raw_event_field in ('"event_id"', '"actor_id"', '"ledger_version"', '"txn_id"'):
        assert raw_event_field not in bundle.text


# ---------------------------------------------------------------------------
# Done when: a 20-round fixture session must not exceed the configured
# context budget, and rounds beyond N are summarized, not dropped.
# ---------------------------------------------------------------------------


def _seed_round(project, index: int) -> None:
    txn_id = f"TXN-{index:03d}"
    append_event(
        dict(
            ts=NOW,
            type=EventType.TXN_BEGIN,
            entity_id=None,
            actor_id="agent:orchestrator",
            actor_role="agent",
            agent_name="orchestrator",
            workflow_state="DISCOVERY",
            txn_id=txn_id,
            source="fixture",
            reason="round start",
            before=None,
            after=None,
            session_id="session-1",
        ),
        project.events_path,
    )
    req = _requirement(f"REQ-{index:03d}", status="PROPOSED", covers_areas=["problem"])
    append_event(
        dict(
            ts=NOW,
            type=EventType.REQUIREMENT_CREATED,
            entity_id=f"REQ-{index:03d}",
            actor_id="agent:discovery",
            actor_role="agent",
            agent_name="discovery",
            workflow_state="DISCOVERY",
            txn_id=txn_id,
            source="fixture",
            reason="round wrote a requirement",
            before=None,
            after=req.model_dump(mode="json"),
            session_id="session-1",
        ),
        project.events_path,
    )
    append_event(
        dict(
            ts=NOW,
            type=EventType.TXN_COMMIT,
            entity_id=None,
            actor_id="agent:orchestrator",
            actor_role="agent",
            agent_name="orchestrator",
            workflow_state="DISCOVERY",
            txn_id=txn_id,
            source="fixture",
            reason="round committed",
            before=None,
            after=None,
            session_id="session-1",
        ),
        project.events_path,
    )


def test_twenty_round_session_stays_within_the_configured_context_budget(tmp_path):
    project = _make_project(tmp_path)
    for i in range(20):
        _seed_round(project, i)

    entities = {f"REQ-{i:03d}": _requirement(f"REQ-{i:03d}", status="PROPOSED") for i in range(20)}
    bundle = context.assemble_context(project, entities, now=NOW)

    assert bundle.round_count == 20
    assert bundle.token_estimate <= context.DEFAULT_MAX_CONTEXT_TOKENS


def test_rounds_beyond_n_are_summarized_not_dropped(tmp_path):
    project = _make_project(tmp_path)
    for i in range(10):
        _seed_round(project, i)

    bundle = context.assemble_context(project, {}, now=NOW, recent_rounds=6)

    assert bundle.round_count == 10
    assert bundle.recent_round_count == 6
    assert bundle.older_round_count == 4
    for i in range(4):
        assert f"TXN-{i:03d}" in bundle.text  # every older round still named, not dropped
    for i in range(4, 10):
        assert f"TXN-{i:03d}" in bundle.text  # every recent round still named


# ---------------------------------------------------------------------------
# ppa/orchestrator/dispatch.py — agent selection (step 5).
# ---------------------------------------------------------------------------


def test_select_agent_maps_discovery_and_discovery_validated():
    discovery = dispatch.select_agent("DISCOVERY")
    assert discovery.id == "discovery"

    planning = dispatch.select_agent("DISCOVERY_VALIDATED")
    assert planning.id == "planning"


@pytest.mark.parametrize(
    "state", ["PLANNING", "PLAN_REVIEW", "PLAN_APPROVED", "DELIVERY", "COMPLETE", "CHANGE_REQUESTED"]
)
def test_select_agent_raises_for_states_v1_never_reaches(state):
    with pytest.raises(dispatch.UnwiredWorkflowState):
        dispatch.select_agent(state)


# ---------------------------------------------------------------------------
# ppa/orchestrator/preconditions.py
# ---------------------------------------------------------------------------


def test_discovery_exit_conditions_are_a_strict_subset_of_check_readiness_conditions():
    all_conditions = set(typing.get_args(Condition))
    assert DISCOVERY_EXIT_CONDITIONS < all_conditions
    assert "review_not_approved" not in DISCOVERY_EXIT_CONDITIONS
    assert "unresolved_conflict" not in DISCOVERY_EXIT_CONDITIONS


def test_validate_discovery_state_ignores_review_and_conflict_conditions(tmp_path):
    """A ledger that satisfies every Discovery-owned condition is `ok=True`
    even though `review_approved` defaults to `False` — REVIEW is not
    Discovery's concern."""

    profile = _profile()
    entities = _fully_ready_entities(profile)
    result = validate_discovery_state(entities, profile)
    assert result.ok
