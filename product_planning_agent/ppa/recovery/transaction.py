"""Transaction markers, checkpoint and rollback (T03 + T32, DESIGN.md
§2.14).

Event sourcing already makes rollback nearly free, and this build already
has the two halves that do it: `ppa.orchestrator.loop` opens exactly one
`txn.begin`/`txn.commit` pair per outer-loop iteration (T21), and
`ppa.ledger.materialize`'s own fold (`_effective_events`) already excludes
every event whose `txn_id` never reached a matching `txn.commit` before
computing entity state — a crash mid-transaction, or an explicit
`txn.abort`, leaves events on disk (the log is append-only; nothing is ever
erased) but they are already inert to every reader of ledger *state*.

This module makes that guarantee independently checkable rather than
trusted by construction alone: `checkpoint` captures materialized state
before a transaction begins, and `verify_rolled_back` proves — against a
project's real `events.ndjson`, after a real or simulated crash — that
current state is identical to the checkpoint. Nothing here duplicates
`ppa.orchestrator.loop`'s own `txn.begin`/`txn.commit`/`txn.abort` writers;
this is the verification half, not a second transaction mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ppa.ledger.materialize import current_entities
from ppa.ledger.models import BaseEntity
from ppa.ledger.store import ledger_version


@dataclass(frozen=True)
class Checkpoint:
    """Ledger state as of just before a transaction begins. `version` is a
    cheap, one-integer summary for logging; `entities` is what
    `verify_rolled_back` actually compares against — the materialized
    snapshot itself, not a proxy for it."""

    txn_id: str
    version: int
    entities: dict[str, BaseEntity] = field(default_factory=dict)


def checkpoint(events_path: Path | str, *, txn_id: str) -> Checkpoint:
    """Capture the ledger's current state under `txn_id` — call this
    immediately before opening the transaction (`ppa.orchestrator.loop.
    run_turn`'s own step 6), so a later `verify_rolled_back` has something
    real to compare against."""

    return Checkpoint(
        txn_id=txn_id,
        version=ledger_version(events_path),
        entities=current_entities(events_path),
    )


def verify_rolled_back(events_path: Path | str, before: Checkpoint) -> bool:
    """True iff `events_path`'s current materialized state is identical to
    `before` — the proof that a crash mid-transaction (events written,
    `txn.commit` never reached, or an explicit `txn.abort` recorded
    instead) left the ledger exactly where it started. Compares
    materialized entity state, not the raw event log — the log itself
    always grows (append-only, by design), so a line count alone would
    never prove rollback; `current_entities` already excludes any
    uncommitted `txn_id` before this comparison ever runs."""

    return current_entities(events_path) == before.entities
