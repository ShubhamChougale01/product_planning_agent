"""Question engine tests (T25). Every deterministic piece of the five-step
pipeline (DESIGN.md §3.2, §1.4) maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.engines.question_engine import (
    FATIGUE_THRESHOLD,
    MAX_QUESTIONS_PER_ROUND,
    SOFT_CAP_ROUND,
    detect_fatigue,
    find_gaps,
    question_priority,
    select_top_questions,
    should_offer_assumptions,
)
from ppa.ledger.models import Requirement

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _engineer() -> UserProfile:
    return UserProfile(role="engineer", technical_depth="high", domain_familiarity="high")


def _requirement(entity_id: str, *, covers_areas, status="CONFIRMED") -> Requirement:
    return Requirement(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="user:shubham", updated_by="user:shubham",
        confidence="HIGH", confidence_basis="user said it directly", status=status,
        statement=f"statement for {entity_id}", type="functional", covers_areas=list(covers_areas), priority="must",
    )


# ---------------------------------------------------------------------------
# Step A: find_gaps — deterministic, ranked critical-first.
# ---------------------------------------------------------------------------


def test_find_gaps_on_an_empty_ledger_returns_every_area():
    gaps = find_gaps({}, _engineer())
    assert len(gaps) == len(set(gaps))  # no duplicates
    assert "problem" in gaps and "users" in gaps


def test_find_gaps_ranks_critical_areas_before_non_critical():
    profile = _engineer()
    gaps = find_gaps({}, profile)
    from ppa.config.profiles import critical_areas

    critical = critical_areas(profile)
    critical_positions = [i for i, area in enumerate(gaps) if area in critical]
    non_critical_positions = [i for i, area in enumerate(gaps) if area not in critical]
    if critical_positions and non_critical_positions:
        assert max(critical_positions) < min(non_critical_positions)


def test_find_gaps_excludes_a_sufficiently_covered_area():
    entities = {"REQ-001": _requirement("REQ-001", covers_areas=["problem"], status="CONFIRMED")}
    gaps = find_gaps(entities, _engineer())
    assert "problem" not in gaps


def test_find_gaps_is_deterministic_across_repeated_calls():
    profile = _engineer()
    entities = {"REQ-001": _requirement("REQ-001", covers_areas=["scope_in"], status="CONFIRMED")}
    assert find_gaps(entities, profile) == find_gaps(entities, profile)


# ---------------------------------------------------------------------------
# Step D: question_priority / select_top_questions.
# ---------------------------------------------------------------------------


def test_blocking_questions_score_higher_than_equivalent_non_blocking():
    blocking = question_priority(blocking=True, information_gain=1.0, user_answerability=1.0, cognitive_cost=1.0)
    non_blocking = question_priority(blocking=False, information_gain=1.0, user_answerability=1.0, cognitive_cost=1.0)
    assert blocking == pytest.approx(2 * non_blocking)


def test_cognitive_cost_must_be_positive():
    with pytest.raises(ValueError, match="cognitive_cost"):
        question_priority(blocking=False, information_gain=1.0, user_answerability=1.0, cognitive_cost=0)


def test_select_top_questions_enforces_the_hard_cap():
    candidates = [{"text": f"q{i}", "priority": float(i)} for i in range(10)]
    selected = select_top_questions(candidates)
    assert len(selected) == MAX_QUESTIONS_PER_ROUND
    assert [c["text"] for c in selected] == ["q9", "q8", "q7", "q6", "q5"]


def test_select_top_questions_honors_a_smaller_max():
    candidates = [{"text": f"q{i}", "priority": float(i)} for i in range(10)]
    selected = select_top_questions(candidates, max_questions=3)
    assert len(selected) == 3


# ---------------------------------------------------------------------------
# Fatigue and the round-4 soft cap.
# ---------------------------------------------------------------------------


def test_fatigue_not_detected_before_the_threshold():
    assert detect_fatigue(["dont_know"] * (FATIGUE_THRESHOLD - 1)) is False


def test_fatigue_detected_at_the_threshold():
    assert detect_fatigue(["dont_know"] * FATIGUE_THRESHOLD) is True


def test_fatigue_not_detected_when_a_real_answer_breaks_the_streak():
    kinds = ["dont_know"] * (FATIGUE_THRESHOLD - 1) + ["answered"]
    assert detect_fatigue(kinds) is False


def test_fatigue_only_looks_at_the_most_recent_answers():
    kinds = ["answered"] + ["dont_know"] * FATIGUE_THRESHOLD
    assert detect_fatigue(kinds) is True


def test_offer_assumptions_before_round_4_is_never_triggered():
    assert should_offer_assumptions(SOFT_CAP_ROUND - 1, ready=False) is False


def test_offer_assumptions_at_round_4_when_not_ready():
    assert should_offer_assumptions(SOFT_CAP_ROUND, ready=False) is True


def test_offer_assumptions_not_triggered_once_ready():
    assert should_offer_assumptions(SOFT_CAP_ROUND, ready=True) is False
