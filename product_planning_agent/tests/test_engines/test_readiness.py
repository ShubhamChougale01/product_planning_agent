"""Readiness gate tests (T10). Every Done-when box in
tasks/t10_coverage_and_readiness_engines.md that concerns the readiness gate
maps to at least one test here — including one test per gate condition that
fails **in isolation** (all other conditions satisfied in that fixture).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.config.profiles import UserProfile
from ppa.engines.readiness import check_readiness, force_ready
from ppa.ledger.models import Assumption, Decision, Requirement, Unknown
from ppa.ledger.project import create_project

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _engineer() -> UserProfile:
    # Engineer's critical set (ppa/config/profiles.py): problem, users,
    # scope_in, scope_out, constraints, existing_system, platform, data, nfr.
    return UserProfile(role="engineer", technical_depth="high", domain_familiarity="high")


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


def _assumption(entity_id: str, *, status="CONFIRMED", impact="LOW", **overrides) -> Assumption:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        confidence="MEDIUM",
        confidence_basis="strongly implied",
        status=status,
        statement=f"assumption for {entity_id}",
        reason="inferred",
        impact=impact,
    )
    base.update(overrides)
    return Assumption(**base)


def _unknown(entity_id: str, *, status="RESOLVED", blocking=False, owner_type="user", **overrides) -> Unknown:
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


def _decision(entity_id: str, *, status="DECIDED", blocking=False, **overrides) -> Decision:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        status=status,
        question=f"question for {entity_id}",
        blocking=blocking,
        owner="user:shubham",
        owner_type="user",
        identified_at=NOW,
    )
    base.update(overrides)
    return Decision(**base)


_ENGINEER_CRITICAL = (
    "problem",
    "users",
    "scope_in",
    "scope_out",
    "constraints",
    "existing_system",
    "platform",
    "data",
    "nfr",
)


def _fully_ready_entities() -> dict:
    """Every gate condition satisfied except `review_approved` (a separate,
    explicit kwarg) — the baseline every isolated-failure test starts from
    and perturbs exactly one way."""

    entities = {}
    for i, area in enumerate(_ENGINEER_CRITICAL):
        req_id = f"REQ-{i:03d}"
        entities[req_id] = _requirement(req_id, status="CONFIRMED", covers_areas=[area])
    return entities


def _check(entities, **kwargs):
    kwargs.setdefault("review_approved", True)
    return check_readiness(entities, _engineer(), **kwargs)


# ---------------------------------------------------------------------------
# The fully-satisfied baseline is actually READY.
# ---------------------------------------------------------------------------


def test_fully_satisfied_ledger_is_ready():
    ready, blockers = _check(_fully_ready_entities())
    assert ready is True
    assert blockers == []


# ---------------------------------------------------------------------------
# Done when: each of the seven gate conditions has a test that fails the
# gate in isolation.
# ---------------------------------------------------------------------------


def test_condition_1_critical_area_not_sufficient():
    entities = _fully_ready_entities()
    # Downgrade "problem" to only a PROPOSED requirement — PARTIAL, not
    # SUFFICIENT, but a Requirement still covers it (condition 5 stays green).
    entities["REQ-000"] = _requirement("REQ-000", status="PROPOSED", covers_areas=["problem"])

    ready, blockers = _check(entities)

    assert ready is False
    conditions = {b.condition for b in blockers}
    assert "critical_area_coverage" in conditions
    assert "requirement_missing_for_critical_area" not in conditions


def test_condition_2_blocking_unknown_open_and_user_owned():
    entities = _fully_ready_entities()
    entities["UNK-001"] = _unknown("UNK-001", status="OPEN", blocking=True, owner_type="user")

    ready, blockers = _check(entities)

    assert ready is False
    assert any(b.condition == "blocking_unknown" and b.entity_id == "UNK-001" for b in blockers)


def test_condition_3_high_assumption_not_confirmed_or_rejected():
    entities = _fully_ready_entities()
    entities["ASM-001"] = _assumption("ASM-001", status="PROPOSED", impact="HIGH")

    ready, blockers = _check(entities)

    assert ready is False
    assert any(b.condition == "unconfirmed_high_assumption" and b.entity_id == "ASM-001" for b in blockers)


def test_condition_4_blocking_decision_not_decided():
    entities = _fully_ready_entities()
    entities["DEC-001"] = _decision("DEC-001", status="DECIDE_LATER", blocking=True)

    ready, blockers = _check(entities)

    assert ready is False
    assert any(b.condition == "blocking_decision_not_decided" and b.entity_id == "DEC-001" for b in blockers)


def test_condition_5_no_requirement_at_all_for_a_critical_area():
    entities = _fully_ready_entities()
    del entities["REQ-000"]  # "problem" now has zero covering requirements

    ready, blockers = _check(entities)

    assert ready is False
    assert any(
        b.condition == "requirement_missing_for_critical_area" and b.area == "problem"
        for b in blockers
    )


def test_condition_6_unresolved_conflict():
    entities = _fully_ready_entities()

    ready, blockers = _check(entities, unresolved_conflicts=[{"id": "CFL-001"}])

    assert ready is False
    assert any(b.condition == "unresolved_conflict" and b.entity_id == "CFL-001" for b in blockers)


def test_condition_7_review_not_approved():
    ready, blockers = check_readiness(_fully_ready_entities(), _engineer(), review_approved=False)

    assert ready is False
    assert any(b.condition == "review_not_approved" for b in blockers)


# ---------------------------------------------------------------------------
# Done when: an external-owned blocking unknown does not block READY.
# ---------------------------------------------------------------------------


def test_external_owned_blocking_unknown_does_not_block_ready():
    entities = _fully_ready_entities()
    entities["UNK-001"] = _unknown("UNK-001", status="OPEN", blocking=True, owner_type="external")

    ready, blockers = _check(entities)

    assert ready is True
    assert blockers == []


# ---------------------------------------------------------------------------
# Done when: a non-blocking RESEARCH unknown does not block READY, and a
# blocking RESEARCH unknown does.
# ---------------------------------------------------------------------------


def test_non_blocking_research_unknown_does_not_block_ready():
    entities = _fully_ready_entities()
    entities["UNK-001"] = _unknown(
        "UNK-001", status="OPEN", blocking=False, route="RESEARCH", owner_type="user"
    )

    ready, blockers = _check(entities)

    assert ready is True
    assert blockers == []


def test_blocking_research_unknown_does_block_ready():
    entities = _fully_ready_entities()
    entities["UNK-001"] = _unknown(
        "UNK-001", status="OPEN", blocking=True, route="RESEARCH", owner_type="user"
    )

    ready, blockers = _check(entities)

    assert ready is False
    assert any(b.condition == "blocking_unknown" and b.entity_id == "UNK-001" for b in blockers)


# ---------------------------------------------------------------------------
# force_ready — user override, emits user.forced_ready listing every skipped
# blocker.
# ---------------------------------------------------------------------------


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def test_force_ready_emits_user_forced_ready_listing_skipped_blockers(tmp_path):
    project = create_project("Force Ready", "seed", _profile(), projects_root=tmp_path / "projects")
    entities = {}  # nothing satisfied — every condition should show up as skipped

    force_ready(
        entities,
        _engineer(),
        "client demo tomorrow, shipping with known gaps",
        project.events_path,
        actor_id="user:shubham",
        session_id="sess-001",
        review_approved=False,
    )

    lines = project.events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # project.created + user.forced_ready
    import json

    forced_event = json.loads(lines[-1])
    assert forced_event["type"] == "user.forced_ready"
    assert forced_event["reason"] == "client demo tomorrow, shipping with known gaps"
    skipped = forced_event["after"]["skipped_blockers"]
    assert len(skipped) > 0
    assert any(b["condition"] == "review_not_approved" for b in skipped)
