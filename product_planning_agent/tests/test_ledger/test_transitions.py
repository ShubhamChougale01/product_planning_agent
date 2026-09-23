"""Status transition tests (T02). Every entity type must appear here — the
membership test at the bottom enforces it structurally rather than relying on
someone remembering to add a row.
"""

from __future__ import annotations

import pytest

from ppa.ledger.models import EntityType
from ppa.ledger.transitions import TRANSITIONS, IllegalTransition, validate_transition

# One legal and one illegal transition per entity type, chosen to exercise a
# real business rule rather than an arbitrary pair.
CASES: dict[EntityType, dict[str, tuple[str, str]]] = {
    EntityType.REQUIREMENT: {"legal": ("PROPOSED", "CONFIRMED"), "illegal": ("CONFIRMED", "PROPOSED")},
    EntityType.ASSUMPTION: {"legal": ("PROPOSED", "CONFIRMED"), "illegal": ("CONFIRMED", "PROPOSED")},
    EntityType.DECISION: {"legal": ("OPEN", "DECIDED"), "illegal": ("DECIDED", "OPEN")},
    EntityType.UNKNOWN: {"legal": ("OPEN", "RESOLVED"), "illegal": ("RESOLVED", "OPEN")},
    EntityType.QUESTION_ANSWER: {"legal": ("PENDING", "ANSWERED"), "illegal": ("ANSWERED", "PENDING")},
    EntityType.RESEARCH_FINDING: {"legal": ("ACTIVE", "SUPERSEDED"), "illegal": ("SUPERSEDED", "ACTIVE")},
    EntityType.RISK: {"legal": ("OPEN", "MITIGATED"), "illegal": ("MITIGATED", "OPEN")},
}


def test_every_entity_type_has_transition_coverage():
    """Done when: every entity type has transition coverage in tests."""
    assert set(CASES) == set(EntityType)
    assert set(TRANSITIONS) == set(EntityType)


@pytest.mark.parametrize("entity_type", list(EntityType), ids=lambda e: e.value)
def test_legal_transition_passes(entity_type):
    frm, to = CASES[entity_type]["legal"]
    validate_transition(entity_type, frm, to)  # must not raise


@pytest.mark.parametrize("entity_type", list(EntityType), ids=lambda e: e.value)
def test_illegal_transition_raises(entity_type):
    frm, to = CASES[entity_type]["illegal"]
    with pytest.raises(IllegalTransition):
        validate_transition(entity_type, frm, to)


# ---------------------------------------------------------------------------
# Done when: CONFIRMED -> PROPOSED raises; PROPOSED -> CONFIRMED passes.
# Spelled out explicitly, not just covered by the parametrized sweep above.
# ---------------------------------------------------------------------------


def test_confirmed_to_proposed_raises_exactly_as_the_task_specifies():
    with pytest.raises(IllegalTransition):
        validate_transition(EntityType.REQUIREMENT, "CONFIRMED", "PROPOSED")


def test_proposed_to_confirmed_passes_exactly_as_the_task_specifies():
    validate_transition(EntityType.REQUIREMENT, "PROPOSED", "CONFIRMED")


def test_illegal_transition_error_names_entity_type_and_both_statuses():
    with pytest.raises(IllegalTransition) as exc_info:
        validate_transition(EntityType.REQUIREMENT, "CONFIRMED", "PROPOSED")

    err = exc_info.value
    assert err.entity_type is EntityType.REQUIREMENT
    assert err.frm == "CONFIRMED"
    assert err.to == "PROPOSED"
    assert "CONFIRMED" in str(err) and "PROPOSED" in str(err)


# ---------------------------------------------------------------------------
# Terminal statuses stay terminal.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entity_type, terminal_status",
    [
        (EntityType.REQUIREMENT, "REJECTED"),
        (EntityType.REQUIREMENT, "SUPERSEDED"),
        (EntityType.ASSUMPTION, "REJECTED"),
        (EntityType.DECISION, "SUPERSEDED"),
        (EntityType.UNKNOWN, "RESOLVED"),
        (EntityType.UNKNOWN, "CONVERTED"),
        (EntityType.QUESTION_ANSWER, "SUPERSEDED"),
        (EntityType.RESEARCH_FINDING, "SUPERSEDED"),
        (EntityType.RISK, "CLOSED"),
    ],
)
def test_terminal_statuses_accept_no_further_transition(entity_type, terminal_status):
    assert TRANSITIONS[entity_type][terminal_status] == set()


# ---------------------------------------------------------------------------
# A decision deferred can come back to OPEN; nothing else regresses like this.
# ---------------------------------------------------------------------------


def test_decision_can_return_from_decide_later_to_open():
    validate_transition(EntityType.DECISION, "DECIDE_LATER", "OPEN")


def test_only_decision_allows_returning_to_an_earlier_status():
    for entity_type, table in TRANSITIONS.items():
        if entity_type is EntityType.DECISION:
            continue
        # No entity type other than Decision should have a status that both
        # (a) is reachable from another status, and (b) can transition back to it.
        for frm, tos in table.items():
            for to in tos:
                assert frm not in TRANSITIONS[entity_type].get(to, set()), (
                    f"{entity_type.value}: {frm} <-> {to} is a two-way transition, "
                    "only Decision (DECIDE_LATER <-> OPEN) should allow that"
                )


# ---------------------------------------------------------------------------
# Same-status is always legal — an idempotent re-save is not a status change.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity_type", list(EntityType), ids=lambda e: e.value)
def test_same_status_transition_is_always_legal(entity_type):
    any_status = next(iter(TRANSITIONS[entity_type]))
    validate_transition(entity_type, any_status, any_status)


def test_unknown_from_status_raises_illegal_transition_not_key_error():
    with pytest.raises(IllegalTransition):
        validate_transition(EntityType.REQUIREMENT, "NOT_A_REAL_STATUS", "CONFIRMED")
