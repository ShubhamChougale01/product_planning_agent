"""Materializer — fold events into current entity state (DESIGN.md §1.8,
§2.14, S2.2).

Entity JSON files under `entities/` (a sibling of `events.ndjson`) are a
materialized *view*, never a second source of truth. `rebuild_all()` proves
that: deleting every entity file and calling it again must reproduce them
byte-identically, because the only real state is the event log.

Folding an entity down to "the latest committed `after` snapshot wins" is
deliberate, not a simplification that loses information — `after` is already
a full, validated entity dict at the time of the event (`ppa/ledger/
store.py`'s own note: `before`/`after` are structured snapshots, not diffs),
so nothing is lost by discarding every earlier one per `entity_id`.

Events tagged with a `txn_id` that never reaches a matching `txn.commit` are
excluded before folding starts — that is the entire rollback mechanism
(§2.14). Nothing invalid is ever materialized, so nothing ever needs undoing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ppa.ledger.events import Event, EventType
from ppa.ledger.models import ENTITY_TYPES, BaseEntity, EntityType

_PREFIX_TO_ENTITY_TYPE: dict[str, EntityType] = {
    "REQ": EntityType.REQUIREMENT,
    "ASM": EntityType.ASSUMPTION,
    "DEC": EntityType.DECISION,
    "UNK": EntityType.UNKNOWN,
    "Q": EntityType.QUESTION_ANSWER,
    "ANS": EntityType.QUESTION_ANSWER,
    "RES": EntityType.RESEARCH_FINDING,
    "RSK": EntityType.RISK,
}


def entity_type_for(entity_id: str) -> EntityType:
    """`"REQ-003"` -> `EntityType.REQUIREMENT`, from the id's own prefix —
    the same prefixes `ppa/ledger/models.py` validates ids against."""

    prefix = entity_id.split("-", 1)[0]
    try:
        return _PREFIX_TO_ENTITY_TYPE[prefix]
    except KeyError as exc:
        raise ValueError(f"unrecognized entity id prefix in {entity_id!r}") from exc


def _read_events(events_path: Path) -> list[Event]:
    if not events_path.exists():
        return []
    events: list[Event] = []
    with events_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                events.append(Event.model_validate_json(line))
    return events


def _effective_events(events: list[Event]) -> list[Event]:
    """Every event outside a transaction, plus every event whose `txn_id`
    reached a `txn.commit` — in original log order. An aborted or
    never-closed transaction's events are dropped entirely."""

    committed_txns = {e.txn_id for e in events if e.type == EventType.TXN_COMMIT and e.txn_id}
    return [e for e in events if e.txn_id is None or e.txn_id in committed_txns]


def _latest_snapshots(events: list[Event]) -> dict[str, dict[str, Any]]:
    """`entity_id -> after`, keeping only the last effective event that
    carried an `after` snapshot for that id, in log order."""

    snapshots: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.entity_id is None or event.after is None:
            continue
        snapshots[event.entity_id] = event.after
    return snapshots


def materialize(entity_id: str, events_path: Path | str) -> BaseEntity | None:
    """Fold `events_path` down to `entity_id`'s current state, honoring
    transaction commit/abort. `None` if the id never appears with a
    committed `after` snapshot."""

    events_path = Path(events_path)
    snapshot = _latest_snapshots(_effective_events(_read_events(events_path))).get(entity_id)
    if snapshot is None:
        return None
    model_cls = ENTITY_TYPES[entity_type_for(entity_id)]
    return model_cls.model_validate(snapshot)


def _entity_file_path(entities_dir: Path, entity_id: str) -> Path:
    return entities_dir / f"{entity_id}.json"


def current_entities(events_path: Path | str) -> dict[str, BaseEntity]:
    """Fold `events_path` down to every entity's current state, in memory
    only — no `entities/` file is read or written. This is what `rebuild_all`
    itself computes before persisting; callers that only need a fresh
    snapshot to read (T09's digest, at every turn) should use this directly
    rather than pay to rewrite every entity file on every read."""

    events_path = Path(events_path)
    snapshots = _latest_snapshots(_effective_events(_read_events(events_path)))

    entities: dict[str, BaseEntity] = {}
    for entity_id, snapshot in snapshots.items():
        model_cls = ENTITY_TYPES[entity_type_for(entity_id)]
        entities[entity_id] = model_cls.model_validate(snapshot)
    return entities


def rebuild_all(events_path: Path | str) -> dict[str, BaseEntity]:
    """Regenerate every entity file under `entities/` (a sibling of
    `events_path`) from scratch, replacing whatever was already there —
    the rebuilt content depends only on `events_path`, never on prior
    directory state."""

    events_path = Path(events_path)
    entities_dir = events_path.parent / "entities"

    entities = current_entities(events_path)

    if entities_dir.exists():
        for existing in entities_dir.glob("*.json"):
            existing.unlink()
    entities_dir.mkdir(parents=True, exist_ok=True)

    for entity_id, entity in entities.items():
        _entity_file_path(entities_dir, entity_id).write_text(
            entity.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    return entities
