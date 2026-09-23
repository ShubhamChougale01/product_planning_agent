"""Event envelope tests (T03). Every Done-when box in
tasks/t03_event_model_and_transactions.md maps to at least one test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ppa.ledger.events import Event, EventType
from ppa.ledger.models import EntityType
from ppa.ledger.transitions import TRANSITIONS

NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def _event(**overrides) -> dict:
    base = dict(
        event_id="EVT-000001",
        ts=NOW,
        type=EventType.REQUIREMENT_CREATED,
        entity_id="REQ-001",
        actor_id="user:shubham",
        actor_role="user",
        agent_name=None,
        workflow_state="DISCOVERY",
        txn_id=None,
        source="intake",
        reason="user stated the requirement directly",
        before=None,
        after={"statement": "must support SSO"},
        session_id="sess-001",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Done when: every state change in T02's entity set maps to exactly one event
# type — enumerate and verify.
# ---------------------------------------------------------------------------

# The designated event type for every status a given entity type can be
# created into or transition into, per TRANSITIONS. Risk is deliberately
# excluded — T02 declared it "not written in v1" and nothing creates one yet,
# so it has no reachable status with a real event to record.
STATUS_EVENT_MAP: dict[EntityType, dict[str, EventType]] = {
    EntityType.REQUIREMENT: {
        "PROPOSED": EventType.REQUIREMENT_CREATED,
        "CONFIRMED": EventType.REQUIREMENT_CONFIRMED,
        "REJECTED": EventType.REQUIREMENT_REJECTED,
        "SUPERSEDED": EventType.REQUIREMENT_SUPERSEDED,
    },
    EntityType.ASSUMPTION: {
        "PROPOSED": EventType.ASSUMPTION_CREATED,
        "CONFIRMED": EventType.ASSUMPTION_CONFIRMED,
        "REJECTED": EventType.ASSUMPTION_REJECTED,
        "SUPERSEDED": EventType.ASSUMPTION_SUPERSEDED,
    },
    EntityType.DECISION: {
        "OPEN": EventType.DECISION_OPENED,
        "DECIDE_LATER": EventType.DECISION_DEFERRED,
        "DECIDED": EventType.DECISION_DECIDED,
        "SUPERSEDED": EventType.DECISION_SUPERSEDED,
    },
    EntityType.UNKNOWN: {
        "OPEN": EventType.UNKNOWN_RECORDED,
        "RESOLVED": EventType.UNKNOWN_RESOLVED,
        "CONVERTED": EventType.UNKNOWN_CONVERTED,
    },
    EntityType.QUESTION_ANSWER: {
        "PENDING": EventType.QUESTION_ASKED,
        "ANSWERED": EventType.ANSWER_RECORDED,
        "REPLACED": EventType.QUESTION_REPLACED,
    },
    EntityType.RESEARCH_FINDING: {
        "ACTIVE": EventType.RESEARCH_RECORDED,
        "REPLACED": EventType.RESEARCH_REPLACED,
    },
}


def test_every_entity_type_except_risk_has_a_status_event_map():
    assert set(STATUS_EVENT_MAP) == set(EntityType) - {EntityType.RISK}


@pytest.mark.parametrize(
    "entity_type", list(STATUS_EVENT_MAP), ids=lambda e: e.value
)
def test_every_reachable_status_has_a_designated_event_type(entity_type):
    table = TRANSITIONS[entity_type]
    reachable = set(table.keys()) | {s for tos in table.values() for s in tos}
    mapped = set(STATUS_EVENT_MAP[entity_type])
    missing = reachable - mapped
    assert not missing, f"{entity_type.value}: no event type designated for {missing}"


def test_status_event_map_names_are_unique_per_entity():
    for entity_type, mapping in STATUS_EVENT_MAP.items():
        assert len(set(mapping.values())) == len(mapping), (
            f"{entity_type.value}: two statuses collapsed onto the same event type"
        )


def test_risk_has_no_event_types_yet():
    """Documents the exclusion rather than leaving it silent: Risk is declared
    in T02's schema for v2 but nothing in v1 creates or transitions one."""
    risk_events = [e for e in EventType if e.value.startswith("risk.")]
    assert risk_events == []


# ---------------------------------------------------------------------------
# Done when: reason is required and rejects empty strings.
# ---------------------------------------------------------------------------


def test_reason_is_required():
    payload = _event()
    del payload["reason"]
    with pytest.raises(ValidationError):
        Event(**payload)


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_reason_rejects_blank_strings(blank):
    with pytest.raises(ValidationError, match="reason"):
        Event(**_event(reason=blank))


def test_reason_accepts_a_real_value():
    event = Event(**_event(reason="user confirmed in round 2"))
    assert event.reason == "user confirmed in round 2"


# ---------------------------------------------------------------------------
# Done when: timestamps are timezone-aware; naive datetimes are rejected.
# ---------------------------------------------------------------------------


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        Event(**_event(ts=datetime(2026, 9, 23, 12, 0, 0)))


def test_timezone_aware_timestamp_is_accepted():
    event = Event(**_event(ts=NOW))
    assert event.ts.tzinfo is not None


# ---------------------------------------------------------------------------
# Done when: txn.begin / txn.commit / txn.abort exist and carry txn_id.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event_type", [EventType.TXN_BEGIN, EventType.TXN_COMMIT, EventType.TXN_ABORT]
)
def test_txn_events_carry_a_txn_id(event_type):
    event = Event(
        **_event(
            type=event_type,
            entity_id=None,
            txn_id="TXN-000007",
            reason="clarification round 3 batch write",
            after={"checkpoint_version": 12} if event_type is EventType.TXN_BEGIN else None,
        )
    )
    assert event.txn_id == "TXN-000007"


def test_txn_id_is_optional_for_ordinary_events():
    event = Event(**_event(txn_id=None))
    assert event.txn_id is None


def test_ordinary_event_can_carry_a_txn_id_while_a_transaction_is_open():
    event = Event(**_event(txn_id="TXN-000007"))
    assert event.txn_id == "TXN-000007"


# ---------------------------------------------------------------------------
# Done when: an event can be serialized to a single NDJSON line and parsed
# back identically.
# ---------------------------------------------------------------------------


def test_round_trips_through_a_single_ndjson_line():
    original = Event(**_event())
    line = original.model_dump_json()

    assert "\n" not in line
    assert "\r" not in line

    restored = Event.model_validate_json(line)
    assert restored == original


def test_ndjson_round_trip_preserves_none_fields():
    original = Event(**_event(entity_id=None, agent_name=None, txn_id=None, before=None))
    restored = Event.model_validate_json(original.model_dump_json())
    assert restored.entity_id is None
    assert restored.agent_name is None
    assert restored.txn_id is None
    assert restored.before is None


# ---------------------------------------------------------------------------
# Misc schema guarantees.
# ---------------------------------------------------------------------------


def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        Event(**_event(unexpected_field="nope"))


def test_malformed_event_id_is_rejected():
    with pytest.raises(ValidationError, match="event_id"):
        Event(**_event(event_id="not-an-id"))


def test_event_type_values_are_all_unique():
    values = [e.value for e in EventType]
    assert len(values) == len(set(values))
