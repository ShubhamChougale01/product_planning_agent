"""T35 tests — the two "Done when" boxes `ppa/recovery/transaction.py` (T32)
doesn't itself prove: that a *killed process*, not just a mid-transaction
crash caught in-flight, resumes with no manual repair when the next session
starts cold (`ppa chat <project>` calling `ppa.orchestrator.loop.run_turn`
again); and that a project untouched for a week restores full context from
`ppa.ledger.digest.read_digest`, with "due soon" computed against the real
current moment, never against how old the ledger's own timestamps are.

Neither box needed new production code — `ppa.ledger.materialize.
current_entities` already excludes any `txn_id` with no matching
`txn.commit` (T07), and `read_digest`/`open_project` already rebuild
everything fresh from `events.ndjson`/`project.json` on every call, with no
cached state and no dependency on wall-clock age anywhere in the read path
(`tasks/t35_hardening_and_documentation.md`'s own "Why this task exists").
These tests prove that guarantee end to end, from the CLI's own entry
points, rather than trusting it by construction alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ppa.agents.base import Agent, AgentResult, AgentResultStatus, BaseAgent
from ppa.config.profiles import UserProfile
from ppa.ledger.digest import read_digest
from ppa.ledger.events import EventType
from ppa.ledger.materialize import current_entities
from ppa.ledger.models import Decision
from ppa.ledger.project import create_project, open_project
from ppa.ledger.store import allocate_id, append_event
from ppa.orchestrator import loop

NOW = datetime(2026, 9, 30, 9, 0, 0, tzinfo=timezone.utc)


def _profile() -> UserProfile:
    return UserProfile(role="engineer", technical_depth="medium", domain_familiarity="medium")


def _project(tmp_path, **overrides):
    kwargs = dict(
        name=overrides.pop("name", "Resume Test Project"),
        seed_requirement=overrides.pop("seed_requirement", "users need to export their invoices"),
        profile=overrides.pop("profile", _profile()),
        projects_root=tmp_path / "projects",
    )
    kwargs.update(overrides)
    return create_project(**kwargs)


# ---------------------------------------------------------------------------
# Done when: a killed session resumes with no manual repair.
# ---------------------------------------------------------------------------


class _OneShotAgent(BaseAgent):
    """A real top-level agent the way `select_agent` would hand one back —
    swapped in only for this test, never registered in `ppa.agents.
    registry`. Returns OK on every call; the point of this test is what
    happens *around* it (the orphaned pre-crash event), not the agent
    itself."""

    id = "discovery"
    system_prompt = "fixture agent for T35 resume-after-kill tests"

    def invoke(self, ctx) -> AgentResult:
        return AgentResult(status=AgentResultStatus.OK, summary="post-crash turn completed normally")


def test_a_killed_session_resumes_with_no_manual_repair(tmp_path, monkeypatch):
    project = _project(tmp_path)

    # Simulate the process dying mid-transaction: a real event lands on
    # disk (append-only — nothing is ever un-written), but the matching
    # `txn.commit` never arrives because the process was killed right here,
    # exactly like T32's own crash-mid-transaction test, but from the next
    # session's entry point rather than `verify_rolled_back` directly.
    orphaned_txn = allocate_id("TXN", project.events_path)
    orphaned_decision = Decision(
        id="DEC-001", created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status="OPEN", question="a decision written mid-crash, never committed", owner="user:local",
        owner_type="user", identified_at=NOW,
    )
    append_event(
        dict(
            ts=NOW, type=EventType.DECISION_OPENED, entity_id="DEC-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=orphaned_txn,
            source="manage_decision", reason="crash test — never committed", before=None,
            after=orphaned_decision.model_dump(mode="json"), session_id="session-1",
        ),
        project.events_path,
    )

    # "No manual repair": nothing above this line runs any recovery step.
    # A cold-started next session just opens the project and calls
    # `run_turn` again, exactly as `ppa chat <project>` would.
    reopened = open_project(project.slug, projects_root=tmp_path / "projects")
    monkeypatch.setattr(loop, "select_agent", lambda state: _OneShotAgent())

    step = loop.run_turn(reopened, reopened.profile, session_id="session-2", now=NOW + timedelta(minutes=1))

    assert step.outcome is loop.StepOutcome.ADVANCED

    entities = current_entities(reopened.events_path)
    assert "DEC-001" not in entities  # the orphaned, never-committed decision stays invisible


# ---------------------------------------------------------------------------
# Done when: a week-old project resumes with full context from the digest.
# ---------------------------------------------------------------------------


def test_a_week_old_project_resumes_with_full_context_from_the_digest(tmp_path):
    project = _project(tmp_path, name="Week Old Project", seed_requirement="users need SSO login")

    a_week_ago = NOW - timedelta(days=7)
    true_now = NOW  # "today" — when the user actually comes back

    # Everything below is timestamped a week in the past, as if this
    # project was last touched then and nobody has opened it since.
    decision = Decision(
        id="DEC-001", created_at=a_week_ago, updated_at=a_week_ago, created_by="agent:discovery",
        updated_by="agent:discovery", status="OPEN", question="which auth provider to use", owner="user:local",
        owner_type="user", identified_at=a_week_ago,
        expected_decision_date=true_now + timedelta(days=2),  # due soon relative to TODAY, not a week ago
    )
    append_event(
        dict(
            ts=a_week_ago, type=EventType.DECISION_OPENED, entity_id="DEC-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=None,
            source="manage_decision", reason="decision opened a week ago", before=None,
            after=decision.model_dump(mode="json"), session_id="session-1",
        ),
        project.events_path,
    )

    # A brand new process, days later, with nothing but the project slug —
    # exactly `ppa chat <project>`'s own first move.
    reopened = open_project(project.slug, projects_root=tmp_path / "projects")

    digest = read_digest(reopened, now=true_now)

    assert "SSO login" in digest  # the seed requirement, from the very first event
    assert "DEC-001" in digest
    assert "## Due within 3 days (1)" in digest  # anchored to true_now, not the week-old event timestamps

    # And the digest a caller would have gotten the day the decision was
    # opened would NOT have shown it as "due soon" yet (due date was still
    # 9 days out from back then) — proving this isn't just always showing
    # everything, but genuinely re-anchoring to whenever "now" really is.
    digest_back_then = read_digest(reopened, now=a_week_ago)
    assert "## Due within 3 days (0)" in digest_back_then
