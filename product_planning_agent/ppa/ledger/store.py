"""Append-only event log, ID allocation and idempotency (DESIGN.md §2.14,
§6.6, S2.1, S2.3, S2.4).

`append_event()` is the only place `events.ndjson` is ever opened for
writing. Every free-text field is scanned and redacted (`ppa/ledger/
secrets.py`) *before* the event is constructed — the log is append-only, so
there is no unwriting a mistake (§2.19.1).

**Single-writer assumption.** The lock this module takes is an in-process
`threading.Lock`, keyed by resolved file path — enough to make concurrent
appends from multiple threads in the *same* process safe (no interleaved
lines, no duplicate or skipped event ids), and enough to match this project's
actual usage: one CLI process, one project, one writer. It does **not**
protect against two separate OS processes appending to the same
`events.ndjson` at once — that would need a cross-process file lock (e.g.
`msvcrt.locking` / `fcntl.flock`), which nothing here provides. This is
documented in `README.md` as a real, load-bearing assumption, not an
implementation detail — see `blockers.md` for why it was made this way.

**IDs and idempotency (T07) share `append_event`'s own per-path lock**, not a
second one — `project.json` (a sibling of `events.ndjson`) holds the id
counters and the idem_key -> result map, and both are only ever read/written
while that lock is held. `allocate_id()` alone still shares the lock (so two
concurrent allocations never collide), but only `append_event_with_id()`
allocates *and* appends inside one lock acquisition — that's what actually
closes the "or orphaned" half of S2.3's requirement: a crash between a
standalone `allocate_id()` and a later, separate `append_event()` call could
still burn an id no event ever references. Real write tools (T13+) should go
through `append_event_with_id()`, not compose the two calls themselves.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, NamedTuple

from ppa.ledger.events import Event
from ppa.ledger.secrets import scan_and_redact

_SCANNABLE_STRING_FIELDS = ("source", "reason")
"""Free-text fields scanned before construction. `before`/`after` carry
structured entity snapshots (dicts of already-validated model fields, not
free text a user typed) and are not scanned — see the module docstring in
`secrets.py` for the same boundary."""

_locks_guard = threading.Lock()
_path_locks: dict[str, threading.Lock] = {}

_last_event_number_cache: dict[str, int] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[key] = lock
        return lock


def _read_last_event_number(path: Path) -> int:
    """Recover the last allocated event number from disk. Used once per path
    per process — after that, the in-memory cache is authoritative because
    every append to this path from this process goes through the same lock."""

    if not path.exists():
        return 0

    last_line: bytes | None = None
    with path.open("rb") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                last_line = raw

    if last_line is None:
        return 0

    data = json.loads(last_line)
    return int(str(data["event_id"]).rsplit("-", 1)[-1])


def _next_event_id(path: Path) -> str:
    key = str(path.resolve())
    if key not in _last_event_number_cache:
        _last_event_number_cache[key] = _read_last_event_number(path)
    _last_event_number_cache[key] += 1
    return f"EVT-{_last_event_number_cache[key]:06d}"


def _redact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    clean_fields = dict(fields)
    for field_name in _SCANNABLE_STRING_FIELDS:
        value = clean_fields.get(field_name)
        if isinstance(value, str):
            redacted, _findings = scan_and_redact(value)
            clean_fields[field_name] = redacted
    return clean_fields


def _append_locked(fields: dict[str, Any], path: Path) -> str:
    """Allocate an `event_id` and write one NDJSON line. Caller must already
    hold `_lock_for(path)` — this is the atomic core both `append_event` and
    `append_event_with_id` build on."""

    event_id = _next_event_id(path)
    event = Event(event_id=event_id, **fields)

    path.parent.mkdir(parents=True, exist_ok=True)
    line = event.model_dump_json() + "\n"
    with path.open("ab") as fh:
        fh.write(line.encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())

    return event_id


def append_event(fields: dict[str, Any], path: Path | str) -> str:
    """Redact, allocate an `event_id`, validate, append one NDJSON line, fsync,
    and return the allocated `event_id`.

    `fields` is every `Event` field except `event_id` — the id can't be known
    until it's allocated, and allocation has to happen under the same lock as
    the write (DESIGN.md S2.1, S2.3), so the caller can't supply it up front.

    Redaction happens before `Event(...)` is ever constructed: a raw
    credential must never exist as a Python object beyond `scan_and_redact`'s
    own stack frame, let alone reach the log.
    """

    path = Path(path)
    clean_fields = _redact_fields(fields)

    lock = _lock_for(path)
    with lock:
        return _append_locked(clean_fields, path)


# ---------------------------------------------------------------------------
# project.json — id counters and the idem_key -> result map (T07, S2.3, S2.4)
# ---------------------------------------------------------------------------


def _project_meta_path(events_path: Path) -> Path:
    return events_path.parent / "project.json"


def _read_project_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"id_counters": {}, "idempotency": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("id_counters", {})
    data.setdefault("idempotency", {})
    return data


def _write_project_meta(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def project_meta_path(events_path: Path | str) -> Path:
    """Public accessor for `project.json`'s path — `ppa/ledger/project.py`
    (T08) stores project-level fields (name, slug, profile, workflow_state)
    in the same file as T07's own `id_counters`/`idempotency`, under the same
    per-path lock (`path_lock`, below), so the two never race each other."""

    return _project_meta_path(Path(events_path))


def read_project_meta(events_path: Path | str) -> dict[str, Any]:
    """Read `project.json` beside `events_path`. Caller should hold
    `path_lock(events_path)` if this read-modify-write needs to be atomic
    against concurrent writers."""

    return _read_project_meta(project_meta_path(events_path))


def write_project_meta(events_path: Path | str, meta: dict[str, Any]) -> None:
    """Write `project.json` beside `events_path`, atomically (temp file +
    `os.replace`), same as `allocate_id`'s own writes."""

    _write_project_meta(project_meta_path(events_path), meta)


def path_lock(path: Path | str) -> threading.Lock:
    """The same in-process, per-resolved-path lock `append_event` and
    `allocate_id` take — exposed so other modules (`ppa/ledger/project.py`)
    can guard their own `project.json` updates against those same writers,
    rather than inventing a second, uncoordinated lock over the same file."""

    return _lock_for(Path(path))


def ledger_version(path: Path | str) -> int:
    """The number of the most recently appended event for `path` — DESIGN.md
    §2.16's "ledger 12 -> 13" audit vocabulary. Zero for an empty or
    not-yet-created log. Always computed from `events.ndjson` itself, never
    cached in `project.json`, so it can never drift from the one real source
    of truth (unlike `id_counters`, nothing here needs to survive a process
    restart faster than a file read)."""

    return _read_last_event_number(Path(path))


def allocate_id(prefix: str, path: Path | str) -> str:
    """Allocate the next sequential id for `prefix` (e.g. `"REQ"` ->
    `"REQ-001"`) from the counters kept in `project.json` beside `path`,
    under the same per-path lock `append_event` uses for that path — so an
    id can never be handed out twice (DESIGN.md S2.3).

    Standalone use is safe against collisions but, on its own, can still
    orphan a counter slot if the caller crashes before ever writing the event
    that was meant to use it — `append_event_with_id` is what closes that gap
    by allocating and appending in one lock acquisition.
    """

    path = Path(path)
    meta_path = _project_meta_path(path)
    lock = _lock_for(path)
    with lock:
        meta = _read_project_meta(meta_path)
        counters = meta["id_counters"]
        counters[prefix] = counters.get(prefix, 0) + 1
        allocated = f"{prefix}-{counters[prefix]:03d}"
        _write_project_meta(meta_path, meta)
        return allocated


class WriteResult(NamedTuple):
    """Returned by `append_event_with_id`. `replayed=True` means `idem_key`
    had already been recorded — `event_id`/`entity_id` are the *original*
    result, and this call appended nothing new (DESIGN.md S2.4)."""

    event_id: str
    entity_id: str | None
    replayed: bool


def append_event_with_id(
    fields: dict[str, Any],
    path: Path | str,
    *,
    id_prefix: str | None = None,
    idem_key: str | None = None,
) -> WriteResult:
    """`append_event`, plus optional id allocation and idempotency, all
    inside one lock acquisition so neither an id nor a write can be orphaned
    by a crash between separate calls (DESIGN.md S2.3, S2.4).

    - `id_prefix`: allocate a fresh `entity_id`, inject it into
      `fields["entity_id"]`, and — if `fields["after"]` is a dict — into
      `fields["after"]["id"]` too, so the entity snapshot and the event agree
      on the id that was actually handed out. Allocation happens *after* the
      idem_key check below, so a replay never burns an id it will discard.
    - `idem_key`: if this key has already been recorded (by an earlier,
      successful call for this same `path`), return that original result
      untouched and append nothing — a replayed write must never create a
      second entity or a second event.
    """

    path = Path(path)
    clean_fields = _redact_fields(fields)
    meta_path = _project_meta_path(path)

    lock = _lock_for(path)
    with lock:
        meta = _read_project_meta(meta_path)

        if idem_key is not None:
            recorded = meta["idempotency"].get(idem_key)
            if recorded is not None:
                return WriteResult(
                    event_id=recorded["event_id"],
                    entity_id=recorded.get("entity_id"),
                    replayed=True,
                )

        entity_id = clean_fields.get("entity_id")
        if id_prefix is not None:
            counters = meta["id_counters"]
            counters[id_prefix] = counters.get(id_prefix, 0) + 1
            entity_id = f"{id_prefix}-{counters[id_prefix]:03d}"
            clean_fields["entity_id"] = entity_id
            if isinstance(clean_fields.get("after"), dict):
                clean_fields["after"] = {**clean_fields["after"], "id": entity_id}

        event_id = _append_locked(clean_fields, path)

        if idem_key is not None:
            meta["idempotency"][idem_key] = {"event_id": event_id, "entity_id": entity_id}
        if idem_key is not None or id_prefix is not None:
            _write_project_meta(meta_path, meta)

        return WriteResult(event_id=event_id, entity_id=entity_id, replayed=False)
