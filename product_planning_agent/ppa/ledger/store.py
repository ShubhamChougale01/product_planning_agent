"""Append-only event log (DESIGN.md §2.14, §6.6, S2.1).

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
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

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
    clean_fields = dict(fields)
    for field_name in _SCANNABLE_STRING_FIELDS:
        value = clean_fields.get(field_name)
        if isinstance(value, str):
            redacted, _findings = scan_and_redact(value)
            clean_fields[field_name] = redacted

    lock = _lock_for(path)
    with lock:
        event_id = _next_event_id(path)
        event = Event(event_id=event_id, **clean_fields)

        path.parent.mkdir(parents=True, exist_ok=True)
        line = event.model_dump_json() + "\n"
        with path.open("ab") as fh:
            fh.write(line.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())

        return event_id
