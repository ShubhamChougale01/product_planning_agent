"""Digest projection tests (T09). Every Done-when box in
tasks/t09_digest_projection.md maps to at least one test here.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from ppa.config.profiles import UserProfile
from ppa.ledger.digest import estimate_tokens, generate_digest, read_digest
from ppa.ledger.materialize import rebuild_all
from ppa.ledger.project import create_project
from ppa.ledger.store import append_event_with_id

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _event_fields(**overrides) -> dict:
    base = dict(
        ts=NOW,
        type="requirement.created",
        entity_id=None,
        actor_id="user:shubham",
        actor_role="user",
        agent_name=None,
        workflow_state="DISCOVERY",
        txn_id=None,
        source="intake",
        reason="test fixture event",
        before=None,
        after=None,
        session_id="sess-001",
    )
    base.update(overrides)
    return base


def _requirement_after(**overrides) -> dict:
    base = dict(
        id="PENDING",
        version=1,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        confidence="HIGH",
        confidence_basis="user said it directly",
        status="PROPOSED",
        statement="A requirement",
        type="functional",
        covers_areas=[],
        derived_from_answers=[],
        depends_on_assumptions=[],
        depends_on_decisions=[],
        priority="must",
        needs_user_confirmation=False,
        custom_fields={},
    )
    base.update(overrides)
    return base


def _assumption_after(**overrides) -> dict:
    base = dict(
        id="PENDING",
        version=1,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        confidence="MEDIUM",
        confidence_basis="strongly implied",
        status="PROPOSED",
        statement="An assumption",
        reason="inferred",
        impact="HIGH",
        affects_requirements=[],
        affects_areas=[],
        user_confirmation_required=True,
        confirmed_at=None,
        confirmed_by=None,
        provisional=False,
    )
    base.update(overrides)
    return base


def _unknown_after(**overrides) -> dict:
    base = dict(
        id="PENDING",
        version=1,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        status="OPEN",
        question="What is unknown?",
        area="platform",
        why_it_matters="blocks the platform decision",
        blocking=True,
        route="USER_DECISION",
        owner_type="user",
        converted_to=None,
    )
    base.update(overrides)
    return base


def _make_project(tmp_path, name="Digest Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _add_requirement(project, **overrides) -> str:
    result = append_event_with_id(
        _event_fields(after=_requirement_after(**overrides)),
        project.events_path,
        id_prefix="REQ",
    )
    return result.entity_id


def _add_assumption(project, **overrides) -> str:
    result = append_event_with_id(
        _event_fields(type="assumption.created", after=_assumption_after(**overrides)),
        project.events_path,
        id_prefix="ASM",
    )
    return result.entity_id


def _add_unknown(project, **overrides) -> str:
    result = append_event_with_id(
        _event_fields(type="unknown.recorded", after=_unknown_after(**overrides)),
        project.events_path,
        id_prefix="UNK",
    )
    return result.entity_id


# ---------------------------------------------------------------------------
# Done when: a 50-entity ledger digests to under 2k tokens.
# ---------------------------------------------------------------------------


def test_fifty_entity_ledger_digests_under_2k_tokens(tmp_path):
    project = _make_project(tmp_path)

    for i in range(44):
        _add_requirement(project, statement=f"Requirement number {i}")
    for i in range(2):
        _add_unknown(project, question=f"Unknown {i}", why_it_matters="matters a lot")
    for i in range(2):
        _add_assumption(project, statement=f"High-impact assumption {i}", impact="HIGH")
    for i in range(2):
        _add_assumption(project, statement=f"Low-impact assumption {i}", impact="LOW", status="CONFIRMED")

    entities = rebuild_all(project.events_path)
    assert len(entities) == 50

    digest = generate_digest(project, entities, now=NOW)
    assert estimate_tokens(digest) < 2000


# ---------------------------------------------------------------------------
# Done when: zero blocking items are omitted or truncated, at any ledger
# size.
# ---------------------------------------------------------------------------


def test_zero_blocking_items_omitted_at_larger_ledger_sizes(tmp_path):
    project = _make_project(tmp_path)

    blocking_ids = []
    for i in range(5):
        blocking_ids.append(_add_unknown(project, question=f"Blocking unknown {i}"))
    for i in range(80):
        _add_requirement(project, statement=f"Filler requirement {i}")

    entities = rebuild_all(project.events_path)
    digest = generate_digest(project, entities, now=NOW)

    for entity_id in blocking_ids:
        assert f"{entity_id} [FULL]" in digest
        assert "why_it_matters" in digest.split(f"{entity_id} [FULL]")[1].splitlines()[0]


def test_resolved_unknown_is_not_treated_as_blocking(tmp_path):
    project = _make_project(tmp_path)
    unknown_id = _add_unknown(project, status="RESOLVED", blocking=True)

    entities = rebuild_all(project.events_path)
    digest = generate_digest(project, entities, now=NOW)

    assert f"{unknown_id} [FULL]" not in digest
    assert unknown_id in digest  # still appears, just as a title


# ---------------------------------------------------------------------------
# Done when: zero unconfirmed HIGH-impact assumptions are omitted.
# ---------------------------------------------------------------------------


def test_zero_unconfirmed_high_assumptions_omitted(tmp_path):
    project = _make_project(tmp_path)

    high_ids = [_add_assumption(project, statement=f"High {i}", impact="HIGH") for i in range(4)]
    _add_assumption(project, statement="Confirmed high", impact="HIGH", status="CONFIRMED")
    _add_assumption(project, statement="Low impact", impact="LOW")
    for i in range(60):
        _add_requirement(project, statement=f"Filler {i}")

    entities = rebuild_all(project.events_path)
    digest = generate_digest(project, entities, now=NOW)

    for entity_id in high_ids:
        assert f"{entity_id} [FULL]" in digest


# ---------------------------------------------------------------------------
# Done when: a write followed immediately by `read_digest` reflects that
# write.
# ---------------------------------------------------------------------------


def test_write_followed_immediately_by_read_digest_reflects_the_write(tmp_path):
    project = _make_project(tmp_path)
    digest_before = read_digest(project, now=NOW)
    assert "Brand new requirement" not in digest_before

    _add_requirement(project, statement="Brand new requirement")

    digest_after = read_digest(project, now=NOW)
    assert "Brand new requirement" in digest_after


# ---------------------------------------------------------------------------
# Done when: digest generation for a 500-event project takes under 200ms.
# ---------------------------------------------------------------------------


def test_digest_generation_for_500_event_project_is_fast(tmp_path):
    project = _make_project(tmp_path)
    for i in range(499):
        _add_requirement(project, statement=f"Requirement {i}")

    start = time.perf_counter()
    read_digest(project, now=NOW)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 200, f"digest generation took {elapsed_ms:.1f}ms"


# ---------------------------------------------------------------------------
# Coverage rendering and misc.
# ---------------------------------------------------------------------------


def test_coverage_defaults_to_untouched_when_no_coverage_supplied(tmp_path):
    project = _make_project(tmp_path)
    entities = rebuild_all(project.events_path)
    digest = generate_digest(project, entities, now=NOW)
    assert "Critical coverage: 0/" in digest


def test_coverage_marks_critical_areas_and_counts_sufficient_ones(tmp_path):
    project = _make_project(tmp_path, name="Coverage Render")
    entities = rebuild_all(project.events_path)

    from ppa.config.profiles import critical_areas

    critical = critical_areas(project.profile)
    coverage = {key: "SUFFICIENT" for key in critical}

    digest = generate_digest(project, entities, coverage=coverage, now=NOW)
    assert f"Critical coverage: {len(critical)}/{len(critical)}" in digest


def test_due_soon_decision_is_listed(tmp_path):
    project = _make_project(tmp_path)
    decision_after = dict(
        id="PENDING",
        version=1,
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        status="OPEN",
        question="Which vendor?",
        blocking=False,
        owner="user:shubham",
        owner_type="user",
        identified_at=NOW.isoformat(),
        expected_decision_date=(NOW + timedelta(days=2)).isoformat(),
        decided_at=None,
        defer_reason=None,
        options=[],
        chosen_option=None,
        rationale=None,
        prerequisites=[],
        current_assumption=None,
        related_requirements=[],
        related_research=[],
    )
    append_event_with_id(
        _event_fields(type="decision.opened", after=decision_after),
        project.events_path,
        id_prefix="DEC",
    )

    entities = rebuild_all(project.events_path)
    digest = generate_digest(project, entities, now=NOW)

    assert "Which vendor?" in digest.split("## Due within 3 days")[1]
