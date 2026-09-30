"""T32 tests — transaction checkpoint/rollback (`ppa/recovery/
transaction.py`) and the outer loop's own `txn.abort` behavior (T21,
reused here). Every Done-when box in `tasks/t32_transactions_retry_
recovery.md` that concerns transactions maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.agents.base import Agent, AgentResult, AgentResultStatus, BaseAgent
from ppa.config.profiles import UserProfile
from ppa.ledger.events import EventType
from ppa.ledger.project import create_project
from ppa.ledger.store import allocate_id, append_event
from ppa.orchestrator import loop
from ppa.orchestrator.context import read_events
from ppa.recovery.transaction import checkpoint, verify_rolled_back

NOW = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)


def _profile() -> UserProfile:
    return UserProfile(role="engineer", technical_depth="medium", domain_familiarity="medium")


def _project(tmp_path):
    return create_project(
        "Recovery Test Project", "a rough seed requirement", _profile(), projects_root=tmp_path / "projects",
    )


# ---------------------------------------------------------------------------
# Done when: a crash injected mid-transaction leaves the ledger at its
# pre-transaction state.
# ---------------------------------------------------------------------------


def test_a_crash_mid_transaction_leaves_the_ledger_at_its_pre_transaction_state(tmp_path):
    project = _project(tmp_path)
    txn_id = allocate_id("TXN", project.events_path)
    before = checkpoint(project.events_path, txn_id=txn_id)

    # A crash mid-transaction: the requirement's own event is written (the
    # log is append-only — nothing is ever un-written), but the matching
    # `txn.commit` never arrives, exactly as if the process died right here.
    requirement_after = dict(
        id="REQ-001", version=1, created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
        created_by="agent:discovery", updated_by="agent:discovery", history=[],
        confidence="HIGH", confidence_basis="user said it directly",
        status="PROPOSED", statement="a requirement written mid-crash", type="functional",
        covers_areas=[], derived_from_answers=[], depends_on_assumptions=[], depends_on_decisions=[],
        priority="must", needs_user_confirmation=False, custom_fields={},
    )
    append_event(
        dict(
            ts=NOW, type=EventType.REQUIREMENT_CREATED, entity_id="REQ-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=txn_id,
            source="manage_requirement", reason="crash test — never committed", before=None,
            after=requirement_after, session_id="session-1",
        ),
        project.events_path,
    )

    assert verify_rolled_back(project.events_path, before) is True


def test_verify_rolled_back_is_false_once_the_transaction_actually_commits(tmp_path):
    project = _project(tmp_path)
    txn_id = allocate_id("TXN", project.events_path)
    before = checkpoint(project.events_path, txn_id=txn_id)

    requirement_after = dict(
        id="REQ-001", version=1, created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
        created_by="agent:discovery", updated_by="agent:discovery", history=[],
        confidence="HIGH", confidence_basis="user said it directly",
        status="PROPOSED", statement="a requirement that really lands", type="functional",
        covers_areas=[], derived_from_answers=[], depends_on_assumptions=[], depends_on_decisions=[],
        priority="must", needs_user_confirmation=False, custom_fields={},
    )
    append_event(
        dict(
            ts=NOW, type=EventType.REQUIREMENT_CREATED, entity_id="REQ-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=txn_id,
            source="manage_requirement", reason="this one commits", before=None,
            after=requirement_after, session_id="session-1",
        ),
        project.events_path,
    )
    append_event(
        dict(
            ts=NOW, type=EventType.TXN_COMMIT, entity_id=None, actor_id="agent:orchestrator",
            actor_role="agent", agent_name="orchestrator", workflow_state="DISCOVERY", txn_id=txn_id,
            source="orchestrator_loop", reason="turn committed", before=None, after=None,
            session_id="session-1",
        ),
        project.events_path,
    )

    assert verify_rolled_back(project.events_path, before) is False


# ---------------------------------------------------------------------------
# Done when: the aborted transaction records what was attempted, via
# txn.abort.
# ---------------------------------------------------------------------------


class _AlwaysRecoverableAgent(BaseAgent):
    """Mirrors `tests/test_agents/test_loop.py::_FixtureAgent` — a scripted
    `Agent` swapped in for `select_agent`, never registered in the real
    registry, proving the outer loop's own `txn.abort` behavior without a
    model."""

    id = "discovery"
    system_prompt = "fixture agent for T32 abort tests"

    def invoke(self, ctx) -> AgentResult:
        return AgentResult(status=AgentResultStatus.RECOVERABLE, summary="flaky tool, always fails")


def test_every_aborted_attempt_records_what_was_attempted(tmp_path, monkeypatch):
    project = _project(tmp_path)
    agent: Agent = _AlwaysRecoverableAgent()
    monkeypatch.setattr(loop, "select_agent", lambda state: agent)

    step = loop.run_turn(project, _profile(), session_id="session-1", now=NOW, retry_budget=3)

    assert step.outcome is loop.StepOutcome.ESCALATED

    aborts = [e for e in read_events(project.events_path) if e.type is EventType.TXN_ABORT]
    assert len(aborts) == 3  # one per exhausted attempt, budget=3
    for abort_event in aborts:
        assert abort_event.reason.strip()
        assert "flaky tool, always fails" in abort_event.reason  # what was attempted, named on every abort
