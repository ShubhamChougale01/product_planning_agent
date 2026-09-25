"""Conflict candidate detection tests (T11). Every Done-when box in
tasks/t11_impact_graph_and_conflicts.md that concerns conflict detection
maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ppa.engines.conflicts import find_conflict_candidates
from ppa.ledger.models import Assumption, QuestionAnswer, Requirement

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)


def _answer(entity_id: str, answer_text: str, *, target_areas=(), **overrides) -> QuestionAnswer:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        status="ANSWERED",
        text="a question",
        why_asked="probing scope",
        target_areas=list(target_areas),
        round=1,
        answer_kind="answered",
        answer_text=answer_text,
        answered_at=NOW,
    )
    base.update(overrides)
    return QuestionAnswer(**base)


def _requirement(entity_id: str, statement: str, *, status="CONFIRMED", covers_areas=(), **overrides) -> Requirement:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        confidence="HIGH",
        confidence_basis="user said it directly",
        status=status,
        statement=statement,
        type="functional",
        covers_areas=list(covers_areas),
        priority="must",
    )
    base.update(overrides)
    return Requirement(**base)


def _assumption(entity_id: str, statement: str, *, status="CONFIRMED", affects_areas=(), **overrides) -> Assumption:
    base = dict(
        id=entity_id,
        created_at=NOW,
        updated_at=NOW,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        confidence="MEDIUM",
        confidence_basis="strongly implied",
        status=status,
        statement=statement,
        reason="inferred",
        impact="MEDIUM",
        affects_areas=list(affects_areas),
    )
    base.update(overrides)
    return Assumption(**base)


# ---------------------------------------------------------------------------
# Done when: the fixture pair "internal tool, 20 users" vs "public launch"
# is flagged as a candidate.
# ---------------------------------------------------------------------------


def test_internal_tool_vs_public_launch_is_flagged():
    new_answer = _answer("ANS-010", "This is an internal tool, 20 users to start")
    ledger = {
        "REQ-002": _requirement("REQ-002", "The product is for public launch", status="CONFIRMED"),
    }

    candidates = find_conflict_candidates(new_answer, ledger)

    assert len(candidates) == 1
    assert candidates[0].candidate_id == "REQ-002"
    assert "mutually_exclusive_terms" in candidates[0].signals


def test_shared_area_signal_fires():
    new_answer = _answer("ANS-011", "We need it to run on Kubernetes", target_areas=["platform"])
    ledger = {
        "REQ-003": _requirement("REQ-003", "Runs entirely on AWS Lambda", covers_areas=["platform"]),
    }

    candidates = find_conflict_candidates(new_answer, ledger)

    assert any(c.candidate_id == "REQ-003" and "shared_area" in c.signals for c in candidates)


def test_negation_signal_fires():
    new_answer = _answer("ANS-012", "We do not support offline mode")
    ledger = {
        "ASM-001": _assumption("ASM-001", "The app must support offline mode for field workers"),
    }

    candidates = find_conflict_candidates(new_answer, ledger)

    assert any(c.candidate_id == "ASM-001" and "negation" in c.signals for c in candidates)


def test_quantity_contradiction_signal_fires():
    new_answer = _answer("ANS-013", "We expect about 50 concurrent users")
    ledger = {
        "REQ-004": _requirement("REQ-004", "Must support 50,000 concurrent users at peak"),
    }

    candidates = find_conflict_candidates(new_answer, ledger)

    assert any(c.candidate_id == "REQ-004" and "quantity_contradiction" in c.signals for c in candidates)


def test_shared_entity_reference_signal_fires():
    new_answer = _answer("ANS-014", "This changes what REQ-007 actually needs to do")
    ledger = {
        "REQ-007": _requirement("REQ-007", "Exports data as CSV, referencing REQ-007's own scope"),
    }

    candidates = find_conflict_candidates(new_answer, ledger)

    assert any(c.candidate_id == "REQ-007" and "shared_entity_reference" in c.signals for c in candidates)


# ---------------------------------------------------------------------------
# Done when: ten non-conflicting pairs produce zero candidates.
# ---------------------------------------------------------------------------


_NON_CONFLICTING_PAIRS = [
    ("Export reports as PDF", "The dashboard shows a weekly summary chart"),
    ("Users log in with email and password", "Passwords are hashed with bcrypt"),
    ("The app supports English and French", "Translations are stored in JSON files"),
    ("Notifications are sent via email", "Email templates live in a templates folder"),
    ("The search bar filters by category", "Categories are managed by an admin"),
    ("Orders are stored in a Postgres database", "Order history is paginated"),
    ("The team meets weekly for planning", "Planning notes go into a shared doc"),
    ("Images are resized before upload", "Thumbnails use a square aspect ratio"),
    ("The API returns JSON responses", "Error responses include a status code"),
    ("Reports can be scheduled to run daily", "Scheduled reports are cached for an hour"),
]


def test_ten_non_conflicting_pairs_produce_zero_candidates():
    for i, (answer_text, requirement_statement) in enumerate(_NON_CONFLICTING_PAIRS):
        new_answer = _answer(f"ANS-{100 + i}", answer_text)
        ledger = {f"REQ-{100 + i}": _requirement(f"REQ-{100 + i}", requirement_statement)}

        candidates = find_conflict_candidates(new_answer, ledger)

        assert candidates == [], f"unexpected candidate for pair {i}: {answer_text!r} vs {requirement_statement!r}"


# ---------------------------------------------------------------------------
# Done when: conflict detection runs without any model call.
# ---------------------------------------------------------------------------


def test_conflict_detection_never_imports_a_model_provider():
    import ppa.engines.conflicts as conflicts_module

    source = conflicts_module.__file__
    with open(source, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "ppa.providers" not in text
    assert "claude_agent_sdk" not in text


# ---------------------------------------------------------------------------
# Only CONFIRMED requirements/assumptions are compared against (§3.7 step 1).
# ---------------------------------------------------------------------------


def test_proposed_requirement_is_not_compared_against():
    new_answer = _answer("ANS-020", "This is an internal tool, 20 users to start")
    ledger = {
        "REQ-020": _requirement("REQ-020", "The product is for public launch", status="PROPOSED"),
    }

    candidates = find_conflict_candidates(new_answer, ledger)

    assert candidates == []
