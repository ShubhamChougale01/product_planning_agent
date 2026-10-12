"""T31 tests — the status board (`ppa/render/status_board.py`). Every
Done-when box in `tasks/t31_cli_and_status_board.md` that concerns the board
itself (not the interactive `chat` loop) maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.config.profiles import UserProfile
from ppa.ledger.audit import AuditResult, record_audit
from ppa.ledger.events import EventType
from ppa.ledger.models import Assumption, Decision, Requirement, Unknown
from ppa.ledger.project import create_project
from ppa.ledger.store import append_event
from ppa.render.status_board import (
    render_cost_report,
    render_history,
    render_open_items,
    render_provenance,
    render_status_board,
)

NOW = datetime(2026, 9, 21, 14, 32, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="product", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _requirement(entity_id: str, *, covers_areas, status="CONFIRMED", **overrides) -> Requirement:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="user:local", updated_by="user:local",
        confidence="HIGH", confidence_basis="user said it directly", status=status,
        statement=f"statement for {entity_id}", type="functional", covers_areas=list(covers_areas),
        priority="must",
    )
    base.update(overrides)
    return Requirement(**base)


def _assumption(entity_id: str, *, affects_areas=(), impact="MEDIUM", status="PROPOSED", **overrides) -> Assumption:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="MEDIUM", confidence_basis="strongly implied", status=status,
        statement=f"assumption for {entity_id}", reason="inferred", impact=impact,
        affects_areas=list(affects_areas),
    )
    base.update(overrides)
    return Assumption(**base)


def _decision(entity_id: str, *, status="OPEN", blocking=True, owner="user:local", owner_type="user", **overrides) -> Decision:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status=status, question=f"question for {entity_id}", blocking=blocking, owner=owner,
        owner_type=owner_type, identified_at=NOW,
    )
    base.update(overrides)
    return Decision(**base)


def _unknown(entity_id: str, *, status="OPEN", blocking=False, route="USER_DECISION", owner_type="user", **overrides) -> Unknown:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status=status, question=f"question for {entity_id}", area="platform", why_it_matters="it matters",
        blocking=blocking, route=route, owner_type=owner_type,
    )
    base.update(overrides)
    return Unknown(**base)


def _project(tmp_path):
    return create_project(
        "Invoice Tracker", "track invoices for freelancers", _profile(), projects_root=tmp_path / "projects",
    )


def _fixture_entities():
    """Product profile's critical set is exactly {problem, users, jobs,
    scope_in, scope_out, success, rollout} — 7 areas, matching DESIGN.md
    §3.8's own example board's 6/7-critical shape. `scope_out` is left
    PARTIAL (an Assumption only, no CONFIRMED Requirement), the other six
    CONFIRMED — the same single-gap shape the example board itself shows."""

    entities = {}
    for n, area in enumerate(("problem", "users", "jobs", "scope_in", "success", "rollout"), start=1):
        rid = f"REQ-{n:03d}"
        entities[rid] = _requirement(rid, covers_areas=[area])
    entities["REQ-007"] = _requirement("REQ-007", covers_areas=["constraints"], status="PROPOSED")
    entities["REQ-008"] = _requirement("REQ-008", covers_areas=["constraints"], status="PROPOSED")

    # existing_system/platform CONFIRMED ("other" section, done); data/nfr/constraints untouched.
    entities["REQ-009"] = _requirement("REQ-009", covers_areas=["existing_system"])
    entities["REQ-010"] = _requirement("REQ-010", covers_areas=["platform"])

    entities["ASM-001"] = _assumption("ASM-001", affects_areas=["scope_out"], impact="MEDIUM", status="PROPOSED")
    entities["ASM-002"] = _assumption("ASM-002", impact="LOW", status="CONFIRMED")
    entities["ASM-003"] = _assumption("ASM-003", impact="HIGH", status="PROPOSED", statement="Web only for v1")

    entities["DEC-001"] = _decision("DEC-001", status="DECIDED", blocking=False, chosen_option="A", rationale="picked A")
    entities["DEC-002"] = _decision("DEC-002", status="DECIDE_LATER", blocking=False, defer_reason="not urgent")
    entities["DEC-003"] = _decision(
        "DEC-003", status="OPEN", blocking=True, owner="user:local", owner_type="user",
        question="Auth approach undecided",
    )
    entities["DEC-004"] = _decision(
        "DEC-004", status="OPEN", blocking=True, owner="client", owner_type="external",
        question="Which payment processor the client will contract with",
    )

    entities["UNK-001"] = _unknown(
        "UNK-001", status="OPEN", blocking=True, route="USER_DECISION", owner_type="user",
        question="Compliance scope unknown",
    )
    entities["UNK-002"] = _unknown("UNK-002", status="OPEN", blocking=False, route="RESEARCH")
    entities["UNK-003"] = _unknown("UNK-003", status="RESOLVED", blocking=True)

    return entities


# ---------------------------------------------------------------------------
# Done when: the status board matches the layout above from fixture data.
# ---------------------------------------------------------------------------


def test_status_board_layout_and_section_order(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    board = render_status_board(project, entities, now=NOW)

    assert "PLANNING STATUS" in board
    assert "Invoice Tracker" in board
    assert "Coverage  6/7 critical" in board
    assert "all areas" in board
    assert "Round " in board and "·" in board
    assert "critical" in board
    assert "other" in board
    assert "Ledger" in board
    assert "Requirements" in board
    assert "Assumptions" in board
    assert "Decisions" in board
    assert "Unknowns" in board
    assert "Readiness" in board
    assert "Open items due within 3 days" in board

    # Sections appear in the documented order.
    order = ["PLANNING STATUS", "Coverage", "critical", "other", "Ledger", "Requirements",
             "Assumptions", "Decisions", "Unknowns", "Readiness", "Open items due within"]
    positions = [board.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_scope_out_gap_reported_on_its_own_line_with_state(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    board = render_status_board(project, entities, now=NOW)

    assert "◐ scope_out (PARTIAL)" in board
    # The six CONFIRMED critical areas appear checked, on the summary line.
    for area in ("problem", "users", "jobs", "scope_in", "success", "rollout"):
        assert f"✓ {area}" in board


def test_ledger_counts_reflect_entity_status_breakdown(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    board = render_status_board(project, entities, now=NOW)

    assert "Requirements" in board and "10" in board
    assert "8 confirmed · 2 proposed" in board
    assert "Assumptions" in board
    assert "1 confirmed · 2 awaiting review ⚠ 1 HIGH impact" in board
    assert "Decisions" in board
    assert "1 decided · 1 decide-later · 2 open \U0001f534 blocking" in board
    assert "Unknowns" in board
    assert "1 blocking · 1 research" in board


def test_readiness_not_ready_lists_blockers_with_icons(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    board = render_status_board(project, entities, now=NOW)

    assert "NOT READY" in board
    assert "\U0001f534" in board  # a hard blocker rendered
    assert "⚠" in board  # the HIGH-impact assumption rendered as a warning
    assert "Auth approach undecided" in board


def test_externally_owned_items_are_visually_distinct_from_user_owned(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    board = render_status_board(project, entities, now=NOW)

    assert "owner: you" in board
    assert "owner: client" in board


def test_board_renders_within_an_80_column_terminal(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    board = render_status_board(project, entities, now=NOW)

    for line in board.splitlines():
        assert len(line) <= 80, f"line exceeds 80 columns: {line!r}"


def test_items_flag_shows_only_readiness_and_open_items(tmp_path):
    project = _project(tmp_path)
    entities = _fixture_entities()

    items_view = render_open_items(project, entities, now=NOW)

    assert "Readiness" in items_view
    assert "Open items" in items_view
    assert "Ledger" not in items_view
    assert "Coverage" not in items_view
    assert "PLANNING STATUS" not in items_view
    assert "UNK-001" in items_view


# ---------------------------------------------------------------------------
# Done when: `history <id>` — the version trail.
# ---------------------------------------------------------------------------


def test_render_history_lists_every_change_oldest_first():
    from ppa.ledger.models import HistoryEntry

    entities = _fixture_entities()
    entity = entities["DEC-003"]
    entity.history = [
        HistoryEntry(field="status", old_value="OPEN", new_value="OPEN", changed_at=NOW, changed_by="agent:discovery", reason="reaffirmed"),
    ]

    trail = render_history("DEC-003", entities)
    assert "DEC-003" in trail
    assert "status" in trail
    assert "agent:discovery" in trail


def test_render_history_for_unknown_entity_says_so():
    trail = render_history("DEC-999", {})
    assert "No entity" in trail


# ---------------------------------------------------------------------------
# Done when: `why <id>` reports agent, tool and workflow state.
# ---------------------------------------------------------------------------


def test_render_provenance_reports_agent_tool_and_workflow_state(tmp_path):
    project = _project(tmp_path)
    record_audit(
        agent="discovery", tool="manage_decision", operation="write", workflow_state="DISCOVERY",
        inputs={"question": "Auth approach"}, reason="decision opened", result=AuditResult(success=True),
        path=project.audit_path, entity_id="DEC-003", ledger_version_before=1, ledger_version_after=2,
    )

    provenance = render_provenance("DEC-003", project.audit_path)
    assert "discovery" in provenance
    assert "manage_decision" in provenance
    assert "DISCOVERY" in provenance


def test_render_provenance_with_no_matching_records_says_so(tmp_path):
    project = _project(tmp_path)
    provenance = render_provenance("DEC-999", project.audit_path)
    assert "No audit record" in provenance


def _record_turn_cost(project, *, agent_name, mode, cost_usd, context_tokens) -> None:
    append_event(
        dict(
            ts=NOW, type=EventType.TURN_COST_RECORDED, entity_id=None, actor_id="agent:orchestrator",
            actor_role="agent", agent_name="orchestrator", workflow_state="DISCOVERY", txn_id=None,
            source="orchestrator_loop", reason="turn cost instrumentation", before=None,
            after={
                "agent_name": agent_name, "mode": mode, "cost_usd": cost_usd, "context_tokens": context_tokens,
            },
            session_id="session-1",
        ),
        project.events_path,
    )


def test_render_cost_report_breaks_down_by_agent_and_mode(tmp_path):
    project = _project(tmp_path)
    _record_turn_cost(project, agent_name="discovery", mode="intake", cost_usd=0.01, context_tokens=100)
    _record_turn_cost(project, agent_name="discovery", mode="clarify", cost_usd=0.02, context_tokens=200)
    _record_turn_cost(project, agent_name="guidance", mode="guidance", cost_usd=0.03, context_tokens=300)

    report = render_cost_report(project)

    assert "3 turns" in report
    assert "$0.0600" in report  # total
    assert "~600 tokens" in report  # total
    assert "discovery" in report
    assert "guidance" in report
    assert "intake" in report
    assert "clarify" in report


def test_render_cost_report_with_no_turns_recorded_says_so(tmp_path):
    project = _project(tmp_path)
    report = render_cost_report(project)
    assert "no turns recorded" in report.lower()
