"""Zero-cost tests for `ppa.agents.modes.clarify.evaluate_clarify_round` —
the pure round-diffing logic, independent of any real model call (that part
is `tests/eval/test_clarify.py`, marked `live_model`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.agents.modes.clarify import evaluate_clarify_round
from ppa.ledger.models import Assumption, QuestionAnswer, Unknown

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _question(entity_id: str, *, target_areas, **overrides) -> QuestionAnswer:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status="PENDING", text=f"question for {entity_id}", why_asked="closing a gap", target_areas=target_areas,
        round=2,
    )
    base.update(overrides)
    return QuestionAnswer(**base)


def _assumption(entity_id: str) -> Assumption:
    return Assumption(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="MEDIUM", confidence_basis="strongly implied", status="PROPOSED",
        statement=f"assumption {entity_id}", reason="inferred", impact="LOW", user_confirmation_required=True,
    )


def _unknown(entity_id: str, *, route="RESEARCH") -> Unknown:
    return Unknown(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status="OPEN", question=f"question for {entity_id}", area="nfr", why_it_matters="it matters",
        blocking=False, route=route, owner_type="agent",
    )


def test_a_well_shaped_round_has_no_violations():
    before = {}
    after = {
        "Q-001": _question("Q-001", target_areas=["platform"]),
        "Q-002": _question("Q-002", target_areas=["data"]),
        "ASM-001": _assumption("ASM-001"),
    }
    report = evaluate_clarify_round(before, after)
    assert report.ok, report.violations
    assert report.questions_asked_count == 2
    assert report.assumptions_recorded_count == 1


def test_exceeding_the_hard_cap_is_a_violation():
    before = {}
    after = {f"Q-{i:03d}": _question(f"Q-{i:03d}", target_areas=[f"area{i}"]) for i in range(6)}
    after["ASM-001"] = _assumption("ASM-001")
    report = evaluate_clarify_round(before, after)
    assert not report.ok
    assert any("hard cap" in v for v in report.violations)


def test_zero_assumptions_recorded_is_the_criterion_that_matters():
    before = {}
    after = {
        "Q-001": _question("Q-001", target_areas=["platform"]),
        "Q-002": _question("Q-002", target_areas=["data"]),
    }
    report = evaluate_clarify_round(before, after)
    assert not report.ok
    assert any("filter is not working" in v for v in report.violations)


def test_clustering_every_question_in_one_area_is_a_violation():
    before = {}
    after = {
        "Q-001": _question("Q-001", target_areas=["platform"]),
        "Q-002": _question("Q-002", target_areas=["platform"]),
        "Q-003": _question("Q-003", target_areas=["platform"]),
        "ASM-001": _assumption("ASM-001"),
    }
    report = evaluate_clarify_round(before, after)
    assert not report.ok
    assert any("spread across areas" in v for v in report.violations)


def test_a_single_question_is_never_penalized_for_clustering():
    before = {}
    after = {"Q-001": _question("Q-001", target_areas=["platform"]), "ASM-001": _assumption("ASM-001")}
    report = evaluate_clarify_round(before, after)
    assert report.ok, report.violations


def test_only_new_entities_are_counted_not_ones_that_already_existed():
    before = {"Q-000": _question("Q-000", target_areas=["problem"]), "ASM-000": _assumption("ASM-000")}
    after = dict(before)
    after["Q-001"] = _question("Q-001", target_areas=["platform"])
    after["ASM-001"] = _assumption("ASM-001")
    report = evaluate_clarify_round(before, after)
    assert report.questions_asked_count == 1
    assert report.assumptions_recorded_count == 1


def test_unknowns_routed_to_research_are_counted():
    before = {}
    after = {
        "Q-001": _question("Q-001", target_areas=["platform"]),
        "ASM-001": _assumption("ASM-001"),
        "UNK-001": _unknown("UNK-001", route="RESEARCH"),
        "UNK-002": _unknown("UNK-002", route="GUIDANCE"),
    }
    report = evaluate_clarify_round(before, after)
    assert report.unknowns_routed_to_research_count == 1
