"""Entity schema tests (T02). Every Done-when box in
tasks/t02_domain_entities_and_status_model.md maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ppa.ledger.models import (
    ENTITY_TYPES,
    Assumption,
    ConfidenceMixin,
    Decision,
    EntityType,
    HistoryEntry,
    QuestionAnswer,
    Requirement,
    ResearchFinding,
    Risk,
    Unknown,
)

NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def _common(prefix_id: str, **overrides) -> dict:
    base = dict(
        id=prefix_id,
        version=1,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
    )
    base.update(overrides)
    return base


def make_requirement(**overrides) -> Requirement:
    data = _common(
        "REQ-001",
        statement="The system must export a PDF report.",
        type="functional",
        priority="must",
        confidence="HIGH",
        confidence_basis="User stated this explicitly in round 1.",
    )
    data.update(overrides)
    return Requirement(**data)


def make_assumption(**overrides) -> Assumption:
    data = _common(
        "ASM-001",
        statement="The client uses PostgreSQL.",
        reason="Mentioned integrations suggest a relational store.",
        impact="MEDIUM",
        confidence="LOW",
        confidence_basis="Inferred from domain convention, not stated.",
    )
    data.update(overrides)
    return Assumption(**data)


def make_decision(**overrides) -> Decision:
    data = _common(
        "DEC-001",
        question="Which hosting provider?",
        owner="user:shubham",
        owner_type="user",
        identified_at=NOW,
    )
    data.update(overrides)
    return Decision(**data)


def make_unknown(**overrides) -> Unknown:
    data = _common(
        "UNK-001",
        question="What is the expected peak concurrency?",
        area="performance",
        why_it_matters="Drives infrastructure sizing decisions.",
        blocking=True,
        route="RESEARCH",
        owner_type="agent",
    )
    data.update(overrides)
    return Unknown(**data)


def make_question_answer(**overrides) -> QuestionAnswer:
    data = _common(
        "Q-001",
        text="Who are the primary users of this tool?",
        why_asked="Scope depends on audience.",
        round=1,
    )
    data.update(overrides)
    return QuestionAnswer(**data)


def make_research_finding(**overrides) -> ResearchFinding:
    data = _common(
        "RES-001",
        question="What do competitors charge?",
        method="web search",
        summary="Three comparable products found, priced $10-30/mo.",
        researched_at=NOW,
        confidence="MEDIUM",
        confidence_basis="Strongly implied by three consistent sources.",
    )
    data.update(overrides)
    return ResearchFinding(**data)


def make_risk(**overrides) -> Risk:
    data = _common(
        "RSK-001",
        statement="Vendor API may deprecate the endpoint we rely on.",
        likelihood="LOW",
        impact="HIGH",
        area="integrations",
    )
    data.update(overrides)
    return Risk(**data)


ALL_FACTORIES = [
    make_requirement,
    make_assumption,
    make_decision,
    make_unknown,
    make_question_answer,
    make_research_finding,
    make_risk,
]


# ---------------------------------------------------------------------------
# Done when: all seven entities round-trip to JSON and back unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", ALL_FACTORIES, ids=lambda f: f.__name__)
def test_round_trips_to_json_and_back_unchanged(factory):
    entity = factory()
    cls = type(entity)

    restored = cls.model_validate_json(entity.model_dump_json())

    assert restored == entity
    assert restored.model_dump() == entity.model_dump()


def test_all_seven_entity_types_are_registered():
    assert len(ENTITY_TYPES) == 7
    assert set(ENTITY_TYPES) == set(EntityType)


def test_history_entry_round_trips_inside_an_entity():
    entry = HistoryEntry(
        field="status",
        old_value="PROPOSED",
        new_value="CONFIRMED",
        changed_at=NOW,
        changed_by="user:shubham",
        reason="User confirmed in round 2.",
    )
    req = make_requirement(history=[entry], version=2)

    restored = Requirement.model_validate_json(req.model_dump_json())
    assert restored.history == [entry]


# ---------------------------------------------------------------------------
# Done when: a bad enum value raises ValidationError.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory, bad_field, bad_value",
    [
        (make_requirement, "status", "APPROVED"),
        (make_requirement, "type", "vibes"),
        (make_requirement, "priority", "urgent"),
        (make_assumption, "status", "MAYBE"),
        (make_assumption, "impact", "CRITICAL"),
        (make_decision, "status", "PENDING"),
        (make_decision, "owner_type", "robot"),
        (make_unknown, "status", "CLOSED"),
        (make_unknown, "route", "MAGIC"),
        (make_unknown, "owner_type", "nobody"),
        (make_question_answer, "status", "DRAFT"),
        (make_question_answer, "answer_kind", "shrug"),
        (make_research_finding, "status", "STALE"),
        (make_risk, "status", "IGNORED"),
        (make_risk, "likelihood", "MAYBE"),
    ],
)
def test_bad_enum_value_raises_validation_error(factory, bad_field, bad_value):
    with pytest.raises(ValidationError):
        factory(**{bad_field: bad_value})


def test_unknown_top_level_field_is_rejected():
    """extra='forbid' — a field outside the declared schema is a bug to catch
    now, not a value to silently accept."""
    with pytest.raises(ValidationError):
        make_requirement(this_field_does_not_exist="surprise")


def test_bad_id_shape_raises_validation_error():
    with pytest.raises(ValidationError):
        make_requirement(id="REQ-abc")

    with pytest.raises(ValidationError):
        make_requirement(id="ASM-001")  # wrong prefix for this entity


def test_question_answer_accepts_both_id_series():
    q = make_question_answer(id="Q-042")
    ans = make_question_answer(id="ANS-042", status="ANSWERED", answer_kind="answered")
    assert q.id == "Q-042"
    assert ans.id == "ANS-042"

    with pytest.raises(ValidationError):
        make_question_answer(id="REQ-042")


# ---------------------------------------------------------------------------
# Done when: an empty confidence_basis raises — it is required, not optional.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("basis", ["", "   ", "\t\n"])
def test_empty_confidence_basis_raises(basis):
    with pytest.raises(ValidationError):
        make_requirement(confidence_basis=basis)


def test_missing_confidence_basis_raises():
    with pytest.raises(ValidationError):
        make_assumption(confidence_basis=None)


def test_confidence_basis_is_required_not_optional():
    """No default is provided anywhere — omitting it entirely must also raise,
    not silently fall back to an empty string."""
    data = _common(
        "RES-002",
        question="x",
        method="x",
        summary="x",
        researched_at=NOW,
        confidence="HIGH",
        # confidence_basis intentionally omitted
    )
    with pytest.raises(ValidationError):
        ResearchFinding(**data)


# ---------------------------------------------------------------------------
# Done when: no field anywhere accepts a numeric confidence.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", [make_requirement, make_assumption, make_research_finding])
@pytest.mark.parametrize("numeric_value", [0.9, 0.6, 0.3, 1, 90])
def test_confidence_rejects_numeric_values(factory, numeric_value):
    with pytest.raises(ValidationError):
        factory(confidence=numeric_value)


def test_no_entity_declares_a_numeric_confidence_field():
    """Structural guard against the regression itself: scan every entity's
    schema for anything named 'confidence' and assert it is the three-value
    Literal, never int/float."""
    for entity_type, cls in ENTITY_TYPES.items():
        for name, field in cls.model_fields.items():
            if "confidence" not in name:
                continue
            if name == "confidence_basis":
                assert field.annotation is str
                continue
            assert field.annotation == ConfidenceMixin.model_fields["confidence"].annotation, (
                f"{entity_type.value}.{name} does not use the shared HIGH/MEDIUM/LOW literal"
            )


# ---------------------------------------------------------------------------
# Done when: Unknown has separate blocking and route — a blocking research
# item is representable.
# ---------------------------------------------------------------------------


def test_unknown_blocking_and_route_are_independent_fields():
    assert "blocking" in Unknown.model_fields
    assert "route" in Unknown.model_fields
    assert "classification" not in Unknown.model_fields


def test_unknown_can_be_blocking_and_routed_to_research_at_once():
    """The case an earlier draft's single classification enum could not
    represent (§2.7, T02 traps)."""
    unk = make_unknown(blocking=True, route="RESEARCH")
    assert unk.blocking is True
    assert unk.route == "RESEARCH"

    restored = Unknown.model_validate_json(unk.model_dump_json())
    assert restored.blocking is True
    assert restored.route == "RESEARCH"


@pytest.mark.parametrize("blocking", [True, False])
@pytest.mark.parametrize(
    "route", ["GUIDANCE", "RESEARCH", "USER_DECISION", "ASSUMPTION", "OPTIONAL", "FUTURE"]
)
def test_all_sixteen_blocking_route_combinations_are_representable(blocking, route):
    unk = make_unknown(blocking=blocking, route=route)
    assert unk.blocking is blocking
    assert unk.route == route


# ---------------------------------------------------------------------------
# Risk: declared but not written in v1 — schema exists, no writer here.
# ---------------------------------------------------------------------------


def test_risk_entity_exists_and_is_registered():
    risk = make_risk()
    assert risk.status == "OPEN"
    assert EntityType.RISK in ENTITY_TYPES
    assert ENTITY_TYPES[EntityType.RISK] is Risk
