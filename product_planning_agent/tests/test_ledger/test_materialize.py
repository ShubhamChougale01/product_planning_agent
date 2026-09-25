"""Materializer tests (T07). Every Done-when box in
tasks/t07_materializer_ids_idempotency.md that concerns folding events into
entity state maps to at least one test here.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from ppa.ledger.materialize import entity_type_for, materialize, rebuild_all
from ppa.ledger.models import EntityType, Requirement
from ppa.ledger.store import append_event

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()


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


def _requirement_dict(entity_id: str, statement: str = "Users can log in", **overrides) -> dict:
    base = dict(
        id=entity_id,
        version=1,
        created_at=NOW_ISO,
        updated_at=NOW_ISO,
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        confidence="HIGH",
        confidence_basis="user said it directly",
        status="PROPOSED",
        statement=statement,
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


def _assumption_dict(entity_id: str, statement: str = "Single tenant per project", **overrides) -> dict:
    base = dict(
        id=entity_id,
        version=1,
        created_at=NOW_ISO,
        updated_at=NOW_ISO,
        created_by="agent:discovery",
        updated_by="agent:discovery",
        history=[],
        confidence="MEDIUM",
        confidence_basis="strongly implied by the seed requirement",
        status="PROPOSED",
        statement=statement,
        reason="no multi-tenant language anywhere in the seed",
        impact="MEDIUM",
        affects_requirements=[],
        affects_areas=[],
        user_confirmation_required=False,
        confirmed_at=None,
        confirmed_by=None,
        provisional=False,
    )
    base.update(overrides)
    return base


def test_entity_type_for_maps_every_known_prefix():
    assert entity_type_for("REQ-001") == EntityType.REQUIREMENT
    assert entity_type_for("ASM-001") == EntityType.ASSUMPTION
    assert entity_type_for("DEC-001") == EntityType.DECISION
    assert entity_type_for("UNK-001") == EntityType.UNKNOWN
    assert entity_type_for("Q-001") == EntityType.QUESTION_ANSWER
    assert entity_type_for("ANS-001") == EntityType.QUESTION_ANSWER
    assert entity_type_for("RES-001") == EntityType.RESEARCH_FINDING
    assert entity_type_for("RSK-001") == EntityType.RISK


def test_materialize_returns_none_for_an_id_with_no_events(tmp_path):
    events_path = tmp_path / "events.ndjson"
    assert materialize("REQ-999", events_path) is None


def test_materialize_folds_a_single_creation_event(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(
        _event_fields(entity_id="REQ-001", after=_requirement_dict("REQ-001")),
        events_path,
    )

    entity = materialize("REQ-001", events_path)
    assert isinstance(entity, Requirement)
    assert entity.id == "REQ-001"
    assert entity.statement == "Users can log in"


def test_materialize_returns_the_latest_committed_snapshot(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(
        _event_fields(entity_id="REQ-001", after=_requirement_dict("REQ-001", statement="v1")),
        events_path,
    )
    append_event(
        _event_fields(
            type="requirement.revised",
            entity_id="REQ-001",
            after=_requirement_dict("REQ-001", statement="v2", version=2),
        ),
        events_path,
    )

    entity = materialize("REQ-001", events_path)
    assert entity.statement == "v2"
    assert entity.version == 2


# ---------------------------------------------------------------------------
# Done when: an aborted transaction leaves no trace in materialized state.
# ---------------------------------------------------------------------------


def test_aborted_transaction_revision_leaves_no_trace(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(
        _event_fields(entity_id="REQ-001", after=_requirement_dict("REQ-001", statement="v1")),
        events_path,
    )
    append_event(_event_fields(type="txn.begin", txn_id="TXN-0001"), events_path)
    append_event(
        _event_fields(
            type="requirement.revised",
            entity_id="REQ-001",
            txn_id="TXN-0001",
            after=_requirement_dict("REQ-001", statement="v2 — never should count", version=2),
        ),
        events_path,
    )
    append_event(
        _event_fields(type="txn.abort", txn_id="TXN-0001", reason="validation failed mid-sequence"),
        events_path,
    )

    entity = materialize("REQ-001", events_path)
    assert entity.statement == "v1"
    assert entity.version == 1


def test_aborted_transaction_never_materializes_a_brand_new_entity(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(_event_fields(type="txn.begin", txn_id="TXN-0002"), events_path)
    append_event(
        _event_fields(
            entity_id="REQ-002",
            txn_id="TXN-0002",
            after=_requirement_dict("REQ-002"),
        ),
        events_path,
    )
    append_event(_event_fields(type="txn.abort", txn_id="TXN-0002", reason="crash mid-sequence"), events_path)

    assert materialize("REQ-002", events_path) is None
    assert "REQ-002" not in rebuild_all(events_path)


def test_committed_transaction_events_do_materialize(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(_event_fields(type="txn.begin", txn_id="TXN-0003"), events_path)
    append_event(
        _event_fields(
            entity_id="REQ-003",
            txn_id="TXN-0003",
            after=_requirement_dict("REQ-003"),
        ),
        events_path,
    )
    append_event(_event_fields(type="txn.commit", txn_id="TXN-0003"), events_path)

    entity = materialize("REQ-003", events_path)
    assert entity is not None
    assert entity.id == "REQ-003"


# ---------------------------------------------------------------------------
# Done when: deleting every entity file and running rebuild_all() reproduces
# them byte-identically.
# ---------------------------------------------------------------------------


def test_rebuild_all_reproduces_entity_files_byte_identically_after_deletion(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(
        _event_fields(entity_id="REQ-001", after=_requirement_dict("REQ-001")),
        events_path,
    )
    append_event(
        _event_fields(
            type="assumption.created",
            entity_id="ASM-001",
            after=_assumption_dict("ASM-001"),
        ),
        events_path,
    )

    entities_dir = tmp_path / "entities"
    rebuild_all(events_path)
    first_bytes = {p.name: p.read_bytes() for p in sorted(entities_dir.glob("*.json"))}
    assert set(first_bytes) == {"REQ-001.json", "ASM-001.json"}

    for f in entities_dir.glob("*.json"):
        f.unlink()
    assert list(entities_dir.glob("*.json")) == []

    rebuild_all(events_path)
    second_bytes = {p.name: p.read_bytes() for p in sorted(entities_dir.glob("*.json"))}

    assert second_bytes == first_bytes


def test_rebuild_all_returns_a_mapping_of_entity_id_to_model(tmp_path):
    events_path = tmp_path / "events.ndjson"
    append_event(
        _event_fields(entity_id="REQ-001", after=_requirement_dict("REQ-001")),
        events_path,
    )

    result = rebuild_all(events_path)
    assert set(result) == {"REQ-001"}
    assert isinstance(result["REQ-001"], Requirement)


# ---------------------------------------------------------------------------
# Done when: rebuilding a 500-event log completes in under a second.
# ---------------------------------------------------------------------------


def test_rebuild_all_handles_500_events_in_under_a_second(tmp_path):
    events_path = tmp_path / "events.ndjson"
    for i in range(1, 501):
        entity_id = f"REQ-{i:03d}"
        append_event(
            _event_fields(entity_id=entity_id, after=_requirement_dict(entity_id, statement=f"req {i}")),
            events_path,
        )

    started = time.perf_counter()
    result = rebuild_all(events_path)
    elapsed = time.perf_counter() - started

    assert len(result) == 500
    assert elapsed < 1.0, f"rebuild_all took {elapsed:.3f}s for 500 events"
