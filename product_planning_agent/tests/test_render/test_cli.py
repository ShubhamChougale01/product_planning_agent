"""T31 tests — the CLI commands `ppa/cli.py` gained: `status` (with
`--items`), `history`, `why` (now with provenance), `force-ready`, and a
full `chat` session run end-to-end in the terminal, without a model
(`_AsksThenDoneAgent` swaps in for `select_agent`, mirroring
`tests/test_agents/test_loop.py::_FixtureAgent` — proven without a model in
the loop, exactly this task's own "Needs a model: No").
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.agents.base import AgentResult, AgentResultStatus, BaseAgent
from ppa.config.profiles import UserProfile
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.ledger.events import EventType
from ppa.ledger.store import append_event, append_event_with_id
from ppa.orchestrator import loop as orchestrator_loop

NOW = datetime(2026, 9, 21, 14, 32, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _project(tmp_path):
    return create_project(
        "CLI Test Project", "a rough seed requirement", _profile(), projects_root=tmp_path / "projects",
    )


def test_ppa_status_renders_the_board(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["status", project.slug])

    assert result.exit_code == 0, result.output
    assert "PLANNING STATUS" in result.output
    assert "Readiness" in result.output


def test_ppa_status_items_flag_filters_to_the_list(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)

    runner = CliRunner()
    full = runner.invoke(app, ["status", project.slug])
    items = runner.invoke(app, ["status", project.slug, "--items"])

    assert full.exit_code == 0 and items.exit_code == 0
    assert "PLANNING STATUS" in full.output
    assert "PLANNING STATUS" not in items.output
    assert "Readiness" in items.output


def test_ppa_status_cost_flag_shows_the_token_and_cost_breakdown(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)
    append_event(
        dict(
            ts=NOW, type=EventType.TURN_COST_RECORDED, entity_id=None, actor_id="agent:orchestrator",
            actor_role="agent", agent_name="orchestrator", workflow_state="DISCOVERY", txn_id=None,
            source="orchestrator_loop", reason="turn cost instrumentation", before=None,
            after={"agent_name": "discovery", "mode": "intake", "cost_usd": 0.05, "context_tokens": 150},
            session_id="session-1",
        ),
        project.events_path,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["status", project.slug, "--cost"])

    assert result.exit_code == 0, result.output
    assert "COST" in result.output
    assert "discovery" in result.output
    assert "intake" in result.output
    assert "0.0500" in result.output  # rich highlights bare numbers; "$" stays outside the escape span


def test_ppa_history_reports_no_entity_for_an_unknown_id(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["history", project.slug, "DEC-999"])

    assert result.exit_code == 0, result.output
    assert "No entity" in result.output


def test_ppa_why_reports_provenance_alongside_the_decision(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)

    decision_after = dict(
        id="PENDING", version=1, created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
        created_by="agent:discovery", updated_by="agent:discovery", history=[],
        status="DECIDED", question="Auth approach?", blocking=True, affects=None, owner="user:local",
        owner_type="user", identified_at=NOW.isoformat(), expected_decision_date=None,
        decided_at=NOW.isoformat(), defer_reason=None, options=[], chosen_option="OAuth",
        rationale="simplest to integrate", prerequisites=[], current_assumption=None,
        related_requirements=[], related_research=[],
    )
    write_result = append_event_with_id(
        dict(
            ts=NOW, type="decision.decided", entity_id=None, actor_id="agent:discovery", actor_role="agent",
            agent_name="discovery", workflow_state="DISCOVERY", txn_id=None, source="manage_decision",
            reason="decided", before=None, after=decision_after, session_id="session-1",
        ),
        project.events_path, id_prefix="DEC",
    )
    dec_id = write_result.entity_id

    from ppa.ledger.audit import AuditResult, record_audit

    record_audit(
        agent="discovery", tool="manage_decision", operation="write", workflow_state="DISCOVERY",
        inputs={"chosen_option": "OAuth"}, reason="decision recorded", result=AuditResult(success=True),
        path=project.audit_path, entity_id=dec_id, ledger_version_before=1, ledger_version_after=2,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["why", project.slug, dec_id])

    assert result.exit_code == 0, result.output
    assert "Auth approach?" in result.output
    assert "discovery" in result.output
    assert "manage_decision" in result.output
    assert "DISCOVERY" in result.output


def test_ppa_force_ready_records_every_skipped_blocker(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from ppa.cli import app
    from ppa.ledger.events import EventType

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["force-ready", project.slug, "--reason", "demo override for a test"])

    assert result.exit_code == 0, result.output
    assert "overridden" in result.output.lower()

    from ppa.orchestrator.context import read_events

    events = read_events(project.events_path)
    forced = [e for e in events if e.type is EventType.USER_FORCED_READY]
    assert len(forced) == 1
    assert forced[0].after["skipped_blockers"]


class _AsksThenDoneAgent(BaseAgent):
    """A minimal `Agent` (T20's protocol) that asks one real question via
    `ask_user` on its first call — leaving a genuine `Q-nnn` `PENDING` on
    the ledger, exactly what `ppa chat`'s own answer loop needs to exercise
    — then reports `NOT_IMPLEMENTED` on every call after, ending the
    session. Swapped in for `ppa.orchestrator.loop.select_agent`, never
    registered in the real `ppa.agents.registry` — the same fixture-agent
    pattern `tests/test_agents/test_loop.py::_FixtureAgent` already
    establishes for proving outer-loop mechanics without a model."""

    id = "discovery"
    system_prompt = "fixture agent for T31 chat tests"

    def __init__(self, project):
        self.project = project
        self.calls = 0

    def invoke(self, ctx):
        from ppa.tools.interaction import ask_user

        self.calls += 1
        if self.calls == 1:
            result = ask_user(
                [{
                    "text": "Which payment processor?",
                    "why_asked": "determines integration scope",
                    "suggested_options": ["Stripe", "Braintree"],
                }],
                self.project, actor_id="agent:discovery", session_id=ctx.session_id, workflow_state=ctx.workflow_state,
            )
            assert result.success, result.error
            return AgentResult(status=AgentResultStatus.HUMAN_INPUT_REQUIRED, summary="asked one question")
        return AgentResult(status=AgentResultStatus.NOT_IMPLEMENTED, summary="fixture has nothing further to do")


def test_ppa_chat_runs_a_full_clarification_round_end_to_end(tmp_path, monkeypatch):
    """Done when: "A full clarification session runs end-to-end in the
    terminal." Proven here without a model — see `_AsksThenDoneAgent`'s own
    docstring for why that satisfies this task's "Needs a model: No"."""

    from typer.testing import CliRunner

    from ppa.cli import app

    monkeypatch.chdir(tmp_path)
    project = _project(tmp_path)
    agent = _AsksThenDoneAgent(project)
    monkeypatch.setattr(orchestrator_loop, "select_agent", lambda state: agent)

    runner = CliRunner()
    result = runner.invoke(app, ["chat", project.slug], input="Stripe\n")

    assert result.exit_code == 0, result.output
    assert "Which payment processor?" in result.output
    assert "PLANNING STATUS" in result.output  # the final status board, printed at session end

    entities = current_entities(project.events_path)
    answers = [e for eid, e in entities.items() if eid.startswith("ANS-")]
    assert len(answers) == 1
    assert answers[0].answer_kind == "answered"
    assert answers[0].answer_text == "Stripe"
