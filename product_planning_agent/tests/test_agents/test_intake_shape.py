"""Zero-cost tests for `ppa.agents.modes.intake.evaluate_intake_shape` — the
pure shape-checking logic, independent of any real model call (that part is
`tests/eval/test_intake.py`, marked `live_model`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.agents.modes.intake import MAX_REPLY_SENTENCES, evaluate_intake_shape
from ppa.ledger.models import Assumption, QuestionAnswer, Requirement

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _requirement(entity_id: str, **overrides) -> Requirement:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="LOW", confidence_basis="inferred from the seed requirement", status="PROPOSED",
        statement=f"statement for {entity_id}", type="functional", covers_areas=[], priority="should",
    )
    base.update(overrides)
    return Requirement(**base)


def _assumption(entity_id: str, **overrides) -> Assumption:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        confidence="LOW", confidence_basis="inferred", status="PROPOSED", statement=f"assumption {entity_id}",
        reason="inferred", impact="LOW", user_confirmation_required=True,
    )
    base.update(overrides)
    return Assumption(**base)


def _question(entity_id: str, **overrides) -> QuestionAnswer:
    base = dict(
        id=entity_id, created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        status="PENDING", text="where am I wrong?", why_asked="confirm the initial understanding", round=1,
    )
    base.update(overrides)
    return QuestionAnswer(**base)


def _shaped_entities(*, requirement_count=3, assumption_count=2, question_count=1, unflagged=0):
    entities = {}
    for i in range(requirement_count):
        rid = f"REQ-{i:03d}"
        entities[rid] = _requirement(rid)
    for i in range(assumption_count):
        aid = f"ASM-{i:03d}"
        flagged = i >= unflagged
        entities[aid] = _assumption(aid, user_confirmation_required=flagged)
    for i in range(question_count):
        qid = f"Q-{i:03d}"
        entities[qid] = _question(qid)
    return entities


def test_a_correctly_shaped_intake_turn_has_no_violations():
    entities = _shaped_entities()
    report = evaluate_intake_shape(entities, reply_text="I understand this as a small internal tool. Where am I wrong?")
    assert report.ok, report.violations


def test_fewer_than_three_proposed_requirements_is_a_violation():
    entities = _shaped_entities(requirement_count=2)
    report = evaluate_intake_shape(entities, reply_text="Short reply. Where am I wrong?")
    assert not report.ok
    assert any("requirement" in v for v in report.violations)


def test_fewer_than_two_assumptions_is_a_violation():
    entities = _shaped_entities(assumption_count=1)
    report = evaluate_intake_shape(entities, reply_text="Short reply. Where am I wrong?")
    assert not report.ok
    assert any("assumption" in v for v in report.violations)


def test_a_silent_unflagged_assumption_is_a_violation():
    entities = _shaped_entities(unflagged=1)
    report = evaluate_intake_shape(entities, reply_text="Short reply. Where am I wrong?")
    assert not report.ok
    assert any("user_confirmation_required" in v for v in report.violations)


def test_zero_questions_is_a_violation():
    entities = _shaped_entities(question_count=0)
    report = evaluate_intake_shape(entities, reply_text="Short reply, no question at all.")
    assert not report.ok
    assert any("pending question" in v for v in report.violations)


def test_more_than_one_question_is_a_violation():
    entities = _shaped_entities(question_count=2)
    report = evaluate_intake_shape(entities, reply_text="Short reply. One? Two?")
    assert not report.ok
    assert any("pending question" in v for v in report.violations)


def test_a_wall_of_text_reply_is_a_violation():
    entities = _shaped_entities()
    wall_of_text = ". ".join(f"Sentence number {i}" for i in range(MAX_REPLY_SENTENCES + 5)) + "."
    report = evaluate_intake_shape(entities, reply_text=wall_of_text)
    assert not report.ok
    assert any("wall of text" in v for v in report.violations)


def test_non_requirement_and_non_assumption_entities_are_not_counted_toward_either():
    entities = _shaped_entities()
    entities["Q-999"] = _question("Q-999", status="ANSWERED")  # answered, not pending — must not count
    report = evaluate_intake_shape(entities, reply_text="I understand this. Where am I wrong?")
    assert report.pending_question_count == 1
