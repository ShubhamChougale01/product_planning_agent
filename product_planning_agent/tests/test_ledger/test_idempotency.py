"""ID allocation and idempotency tests (T07). Every Done-when box in
tasks/t07_materializer_ids_idempotency.md that concerns S2.3/S2.4 maps to at
least one test here.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ppa.ledger.materialize import rebuild_all
from ppa.ledger.store import allocate_id, append_event_with_id

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


def _requirement_after(**overrides) -> dict:
    base = dict(
        id="PENDING",
        version=1,
        created_at=NOW_ISO,
        updated_at=NOW_ISO,
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        confidence="HIGH",
        confidence_basis="user said it directly",
        status="PROPOSED",
        statement="Users can log in",
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


# ---------------------------------------------------------------------------
# Done when: parallel allocation of 100 IDs yields 100 distinct sequential IDs.
# ---------------------------------------------------------------------------


def test_allocate_id_is_sequential_for_serial_calls(tmp_path):
    events_path = tmp_path / "events.ndjson"
    ids = [allocate_id("REQ", events_path) for _ in range(5)]
    assert ids == ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]


def test_allocate_id_persists_counters_in_project_json(tmp_path):
    events_path = tmp_path / "events.ndjson"
    allocate_id("REQ", events_path)
    allocate_id("REQ", events_path)
    allocate_id("ASM", events_path)

    meta = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert meta["id_counters"] == {"REQ": 2, "ASM": 1}


def test_parallel_allocation_of_100_ids_yields_100_distinct_sequential_ids(tmp_path):
    events_path = tmp_path / "events.ndjson"

    with ThreadPoolExecutor(max_workers=16) as pool:
        allocated = list(pool.map(lambda _: allocate_id("REQ", events_path), range(100)))

    assert len(allocated) == 100
    assert len(set(allocated)) == 100, "an id was handed out twice"

    numbers = sorted(int(a.rsplit("-", 1)[-1]) for a in allocated)
    assert numbers == list(range(1, 101)), "ids are not a contiguous, gap-free sequence"


def test_allocate_id_keeps_separate_counters_per_prefix(tmp_path):
    events_path = tmp_path / "events.ndjson"
    assert allocate_id("REQ", events_path) == "REQ-001"
    assert allocate_id("ASM", events_path) == "ASM-001"
    assert allocate_id("REQ", events_path) == "REQ-002"


# ---------------------------------------------------------------------------
# Done when: the same write called three times produces one entity and one
# event.
# ---------------------------------------------------------------------------


def test_append_event_with_id_allocates_and_injects_the_entity_id(tmp_path):
    events_path = tmp_path / "events.ndjson"
    result = append_event_with_id(
        _event_fields(after=_requirement_after()),
        events_path,
        id_prefix="REQ",
        idem_key="create-req-login",
    )

    assert result.entity_id == "REQ-001"
    assert result.replayed is False

    entities = rebuild_all(events_path)
    assert entities["REQ-001"].id == "REQ-001"


def test_same_write_called_three_times_produces_one_entity_and_one_event(tmp_path):
    events_path = tmp_path / "events.ndjson"

    results = [
        append_event_with_id(
            _event_fields(after=_requirement_after()),
            events_path,
            id_prefix="REQ",
            idem_key="create-req-login",
        )
        for _ in range(3)
    ]

    # One real write, two replays.
    assert [r.replayed for r in results] == [False, True, True]
    assert len({r.event_id for r in results}) == 1
    assert len({r.entity_id for r in results}) == 1

    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "a replayed idem_key must not append a second event"

    entities = rebuild_all(events_path)
    assert len(entities) == 1


def test_different_idem_keys_produce_independent_writes(tmp_path):
    events_path = tmp_path / "events.ndjson"

    first = append_event_with_id(
        _event_fields(after=_requirement_after(statement="first")),
        events_path,
        id_prefix="REQ",
        idem_key="create-req-a",
    )
    second = append_event_with_id(
        _event_fields(after=_requirement_after(statement="second")),
        events_path,
        id_prefix="REQ",
        idem_key="create-req-b",
    )

    assert first.entity_id == "REQ-001"
    assert second.entity_id == "REQ-002"
    assert first.replayed is False
    assert second.replayed is False

    entities = rebuild_all(events_path)
    assert set(entities) == {"REQ-001", "REQ-002"}


def test_a_replayed_idem_key_does_not_consume_a_new_id(tmp_path):
    events_path = tmp_path / "events.ndjson"

    append_event_with_id(
        _event_fields(after=_requirement_after()),
        events_path,
        id_prefix="REQ",
        idem_key="create-req-login",
    )
    append_event_with_id(
        _event_fields(after=_requirement_after()),
        events_path,
        id_prefix="REQ",
        idem_key="create-req-login",
    )

    # The id counter must still be at 1 — a replay must not have allocated
    # (and orphaned) REQ-002.
    next_id = allocate_id("REQ", events_path)
    assert next_id == "REQ-002"


def test_write_without_id_prefix_or_idem_key_behaves_like_a_plain_append(tmp_path):
    events_path = tmp_path / "events.ndjson"
    result = append_event_with_id(
        _event_fields(entity_id="REQ-777", after=_requirement_after(id="REQ-777")),
        events_path,
    )

    assert result.entity_id == "REQ-777"
    assert result.replayed is False
    assert not (tmp_path / "project.json").exists(), (
        "no id_prefix and no idem_key means nothing needed writing to project.json"
    )
