"""Event log append tests (T06). Every Done-when box in
tasks/t06_event_log_and_secret_scanning.md that concerns the log maps to at
least one test here.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ppa.ledger.events import Event
from ppa.ledger.store import append_event

NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)


def _fields(**overrides) -> dict:
    base = dict(
        ts=NOW,
        type="project.created",
        entity_id=None,
        actor_id="user:shubham",
        actor_role="user",
        agent_name=None,
        workflow_state="DISCOVERY",
        txn_id=None,
        source="intake",
        reason="project created for T06 append tests",
        before=None,
        after={"name": "demo"},
        session_id="sess-001",
    )
    base.update(overrides)
    return base


def test_single_append_returns_a_well_formed_event_id(tmp_path):
    path = tmp_path / "events.ndjson"
    event_id = append_event(_fields(), path)
    assert event_id == "EVT-000001"


def test_appended_line_round_trips_as_an_event(tmp_path):
    path = tmp_path / "events.ndjson"
    append_event(_fields(reason="first event"), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = Event.model_validate_json(lines[0])
    assert event.event_id == "EVT-000001"
    assert event.reason == "first event"


def test_ids_are_sequential_across_appends(tmp_path):
    path = tmp_path / "events.ndjson"
    ids = [append_event(_fields(), path) for _ in range(5)]
    assert ids == ["EVT-000001", "EVT-000002", "EVT-000003", "EVT-000004", "EVT-000005"]


def test_each_line_is_newline_terminated_utf8_json(tmp_path):
    path = tmp_path / "events.ndjson"
    for _ in range(3):
        append_event(_fields(), path)

    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    for line in raw.decode("utf-8").splitlines():
        json.loads(line)  # must not raise


def test_ids_recover_correctly_after_a_fresh_process_reads_existing_file(tmp_path):
    """Simulates a restart: a second, independent append to a path that
    already has events must continue the sequence, not restart it — proven
    by clearing this module's in-memory cache for the path first."""
    path = tmp_path / "events.ndjson"
    append_event(_fields(), path)
    append_event(_fields(), path)

    import ppa.ledger.store as store_module

    key = str(path.resolve())
    store_module._last_event_number_cache.pop(key, None)

    third_id = append_event(_fields(), path)
    assert third_id == "EVT-000003"


# ---------------------------------------------------------------------------
# Done when: 1000 concurrent appends produce exactly 1000 well-formed lines,
# no interleaving, no lost IDs; event IDs are strictly monotonic under
# concurrency.
# ---------------------------------------------------------------------------


def test_1000_concurrent_appends_produce_1000_well_formed_unique_sequential_ids(tmp_path):
    path = tmp_path / "events.ndjson"

    def _do_append(i: int) -> str:
        return append_event(_fields(reason=f"concurrent append {i}"), path)

    with ThreadPoolExecutor(max_workers=32) as pool:
        returned_ids = list(pool.map(_do_append, range(1000)))

    assert len(returned_ids) == 1000
    assert len(set(returned_ids)) == 1000, "an id was handed out twice"

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1000, "interleaving or a lost write changed the line count"

    parsed_ids = []
    for line in lines:
        event = Event.model_validate_json(line)  # each line must parse as exactly one Event
        parsed_ids.append(event.event_id)

    numbers = sorted(int(eid.rsplit("-", 1)[-1]) for eid in parsed_ids)
    assert numbers == list(range(1, 1001)), "ids are not a contiguous, gap-free, sorted sequence"
    assert set(parsed_ids) == set(returned_ids)


# ---------------------------------------------------------------------------
# Done when: a fixture answer containing postgres://u:p@host/db is stored
# redacted, and the raw credential appears nowhere in events.ndjson.
# ---------------------------------------------------------------------------


def test_credential_in_reason_is_redacted_before_it_reaches_the_log(tmp_path):
    path = tmp_path / "events.ndjson"
    append_event(
        _fields(reason="the client's answer was: postgres://appuser:S3cretPass@db.internal/prod"),
        path,
    )

    raw = path.read_text(encoding="utf-8")
    assert "S3cretPass" not in raw
    assert "appuser:S3cretPass" not in raw
    assert "[REDACTED:credential]" in raw


def test_credential_in_source_is_also_redacted(tmp_path):
    path = tmp_path / "events.ndjson"
    append_event(_fields(source="webhook DB_TOKEN=abcdefghijklmnopqrstuvwx received"), path)

    raw = path.read_text(encoding="utf-8")
    assert "abcdefghijklmnopqrstuvwx" not in raw


# ---------------------------------------------------------------------------
# Misc: append still enforces Event's own validators (reason required,
# tz-aware ts) — the store doesn't bypass the schema it writes.
# ---------------------------------------------------------------------------


def test_append_rejects_a_blank_reason(tmp_path):
    path = tmp_path / "events.ndjson"
    with pytest.raises(ValidationError):
        append_event(_fields(reason=""), path)
    assert not path.exists() or path.read_text(encoding="utf-8") == ""


def test_append_rejects_a_naive_timestamp(tmp_path):
    path = tmp_path / "events.ndjson"
    with pytest.raises(ValidationError):
        append_event(_fields(ts=datetime(2026, 9, 24, 12, 0, 0)), path)
