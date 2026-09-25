"""`ask_user` tests (T17). Every Done-when box in
`tasks/t17_ask_user_tool.md` maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ppa.config.profiles import UserProfile
from ppa.ledger.audit import read_audit_records
from ppa.ledger.materialize import current_entities
from ppa.ledger.project import create_project
from ppa.render.question_card import render_answer_summary, render_question_card
from ppa.results.categories import ErrorCategory
from ppa.tools.interaction import ASK_USER_SPEC, ask_user
from ppa.tools.registry import get, restore, snapshot

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _preserve_registry():
    saved = snapshot()
    yield
    restore(saved)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _make_project(tmp_path, name="Ask User Test"):
    return create_project(name, "seed requirement", _profile(), projects_root=tmp_path / "projects")


def _ask_kwargs(**overrides) -> dict:
    base = dict(actor_id="user:shubham", session_id="sess-001", now=NOW)
    base.update(overrides)
    return base


def _question(**overrides) -> dict:
    base = dict(text="Which payment processor?", why_asked="determines integration scope")
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Done when: a 6-question batch is rejected as VALIDATION.
# ---------------------------------------------------------------------------


def test_six_question_batch_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    questions = [_question(text=f"q{i}") for i in range(6)]
    result = ask_user(questions, project, **_ask_kwargs())
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "BATCH_TOO_LARGE"

    entities = current_entities(project.events_path)
    assert entities == {}


def test_five_question_batch_is_accepted(tmp_path):
    project = _make_project(tmp_path)
    questions = [_question(text=f"q{i}") for i in range(5)]
    result = ask_user(questions, project, **_ask_kwargs())
    assert result.success is True
    assert result.result_count == 5


def test_empty_batch_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user([], project, **_ask_kwargs())
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION


# ---------------------------------------------------------------------------
# Done when: a question missing why_asked is rejected.
# ---------------------------------------------------------------------------


def test_question_missing_why_asked_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user([{"text": "Which payment processor?"}], project, **_ask_kwargs())
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "MISSING_WHY_ASKED"


def test_question_missing_text_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user([{"why_asked": "matters"}], project, **_ask_kwargs())
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "MISSING_TEXT"


# ---------------------------------------------------------------------------
# Done when: all four answer_kind values round-trip correctly.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        {"answer_kind": "answered", "answer_text": "Stripe"},
        {"answer_kind": "dont_know"},
        {"answer_kind": "decide_later"},
        {"answer_kind": "not_relevant", "answer_text": "we don't take payments in v1"},
    ],
)
def test_each_answer_kind_round_trips(tmp_path, answer):
    project = _make_project(tmp_path)
    result = ask_user([_question(answer=answer)], project, **_ask_kwargs())
    assert result.success is True, result.error
    entry = result.data[0]
    assert entry["answer_kind"] == answer["answer_kind"]
    assert entry["answer_id"] is not None
    assert entry["answer_id"].startswith("ANS-")

    entities = current_entities(project.events_path)
    answer_entity = entities[entry["answer_id"]]
    assert answer_entity.status == "ANSWERED"
    assert answer_entity.answer_kind == answer["answer_kind"]

    card = render_question_card(_question(answer=answer))
    assert "Which payment processor?" in card
    assert "determines integration scope" in card
    summary = render_answer_summary(answer)
    assert answer["answer_kind"] in summary or summary  # every kind renders to a non-empty summary


def test_question_without_an_embedded_answer_stays_pending(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user([_question()], project, **_ask_kwargs())
    assert result.success is True
    entry = result.data[0]
    assert entry["question_id"].startswith("Q-")
    assert entry["answer_id"] is None

    entities = current_entities(project.events_path)
    question_entity = entities[entry["question_id"]]
    assert question_entity.status == "PENDING"


# ---------------------------------------------------------------------------
# Done when: every question is persisted as Q-nnn and every answer as
# ANS-nnn.
# ---------------------------------------------------------------------------


def test_answered_question_leaves_the_q_record_replaced_and_a_new_ans_record(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user(
        [_question(answer={"answer_kind": "answered", "answer_text": "Stripe"})],
        project, **_ask_kwargs(),
    )
    assert result.success is True
    entry = result.data[0]

    entities = current_entities(project.events_path)
    assert entities[entry["question_id"]].status == "REPLACED"
    assert entities[entry["answer_id"]].status == "ANSWERED"
    assert entities[entry["answer_id"]].text == "Which payment processor?"
    assert entities[entry["answer_id"]].why_asked == "determines integration scope"


# ---------------------------------------------------------------------------
# Done when: answers pass through secret scanning before being written.
# ---------------------------------------------------------------------------


def test_answer_text_is_secret_scanned(tmp_path):
    project = _make_project(tmp_path)
    leaky = "our db is postgres://admin:hunter2@db.internal:5432/prod"
    result = ask_user(
        [_question(answer={"answer_kind": "answered", "answer_text": leaky})],
        project, **_ask_kwargs(),
    )
    assert result.success is True
    entities = current_entities(project.events_path)
    stored = entities[result.data[0]["answer_id"]].answer_text
    assert "hunter2" not in stored
    assert "[REDACTED:credential]" in stored


# ---------------------------------------------------------------------------
# Done when: not_relevant records a reason rather than discarding the
# question.
# ---------------------------------------------------------------------------


def test_not_relevant_without_a_reason_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user(
        [_question(answer={"answer_kind": "not_relevant"})],
        project, **_ask_kwargs(),
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "MISSING_ANSWER_TEXT"


def test_not_relevant_with_a_reason_records_it(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user(
        [_question(answer={"answer_kind": "not_relevant", "answer_text": "out of scope for v1"})],
        project, **_ask_kwargs(),
    )
    assert result.success is True
    entities = current_entities(project.events_path)
    answer_entity = entities[result.data[0]["answer_id"]]
    assert answer_entity.status == "ANSWERED"
    assert answer_entity.answer_kind == "not_relevant"
    assert answer_entity.answer_text == "out of scope for v1"


# ---------------------------------------------------------------------------
# Invalid answer_kind and general audit coverage.
# ---------------------------------------------------------------------------


def test_invalid_answer_kind_is_rejected(tmp_path):
    project = _make_project(tmp_path)
    result = ask_user(
        [_question(answer={"answer_kind": "maybe"})],
        project, **_ask_kwargs(),
    )
    assert result.success is False
    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "INVALID_ANSWER_KIND"


def test_answered_question_produces_three_audit_records(tmp_path):
    project = _make_project(tmp_path)
    ask_user(
        [_question(answer={"answer_kind": "answered", "answer_text": "Stripe"})],
        project, **_ask_kwargs(),
    )
    records = read_audit_records(project.audit_path)
    assert len(records) == 3
    assert all(r.tool == "ask_user" for r in records)
    assert all(r.result.success for r in records)


def test_rejected_batch_produces_exactly_one_reject_audit_record(tmp_path):
    project = _make_project(tmp_path)
    ask_user([_question(text="")], project, **_ask_kwargs())
    records = read_audit_records(project.audit_path)
    assert len(records) == 1
    assert records[0].operation == "reject"
    assert records[0].result.success is False


# ---------------------------------------------------------------------------
# ToolSpec registration completeness.
# ---------------------------------------------------------------------------


def test_ask_user_toolspec_is_registered_and_complete():
    registered = get("ask_user")
    assert registered.spec is ASK_USER_SPEC
    assert len(registered.spec.examples) >= 2
    assert len(registered.spec.use_when) >= 2
    assert len(registered.spec.do_not_use_when) >= 2
    assert "discovery" in registered.owner_agents
