"""Open items — the "Readiness" section of the status board, as data
(DESIGN.md §3.8, S4.5).

"Planning Progress" and "Open Items" are one command, not two concepts
(§1.15) — `render/status_board.py` (T31) draws the board straight from this
module's output plus `ppa/engines/coverage.py`'s; the model never composes
the board itself.

Collected here, each carrying owner, `owner_type`, a due date (if any), the
`blocking` flag, and what would resolve it:

- blocking Unknowns still `OPEN`
- Decisions with status `OPEN` or `DECIDE_LATER`
- unconfirmed HIGH-impact Assumptions
- Unknowns still `OPEN` and routed to `RESEARCH` ("queued RESEARCH_REQUIRED"
  items, in §1.15's vocabulary — `route`, not a status of its own)

An entity meeting more than one of these (a blocking Unknown that is also
routed to RESEARCH, say) appears exactly once — this is a list of *items*,
not a tally of *reasons*.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict

from ppa.ledger.materialize import entity_type_for
from ppa.ledger.models import BaseEntity, EntityType

Severity = Literal["blocking", "warning"]
Kind = Literal["blocking_unknown", "decision", "unconfirmed_high_assumption", "research_queued"]


class OpenItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    kind: Kind
    title: str
    owner: str | None
    owner_type: Literal["user", "external", "agent"] | None
    due_date: datetime | None
    blocking: bool
    severity: Severity
    resolution: str
    """What would clear this item — DESIGN.md's own requirement for every
    blocker, applied here too."""


_NO_DUE_DATE = datetime.max.replace(tzinfo=timezone.utc)
"""Sort key placeholder for items with no due date at all — sorts after
every real due date (overdue or upcoming), never mixed in among them."""

_RESOLUTION_BY_KIND: dict[Kind, str] = {
    "blocking_unknown": "resolve it, or convert it to an assumption/decision",
    "decision": "make the decision (or, if not blocking, defer it explicitly)",
    "unconfirmed_high_assumption": "confirm or reject this HIGH-impact assumption",
    "research_queued": "complete the research this item is waiting on",
}


def _open_item_for(entity_id: str, entity: BaseEntity, kind: Kind) -> OpenItem:
    if kind in ("blocking_unknown", "research_queued"):
        title = entity.question
    elif kind == "decision":
        title = entity.question
    else:
        title = entity.statement

    return OpenItem(
        entity_id=entity_id,
        kind=kind,
        title=title,
        owner=getattr(entity, "owner", None),
        owner_type=getattr(entity, "owner_type", None),
        due_date=getattr(entity, "expected_decision_date", None),
        blocking=bool(getattr(entity, "blocking", False)),
        severity="blocking" if getattr(entity, "blocking", False) else "warning",
        resolution=_RESOLUTION_BY_KIND[kind],
    )


def collect_open_items(entities: Mapping[str, BaseEntity]) -> list[OpenItem]:
    """One `OpenItem` per entity that belongs on the status board's
    "Readiness" section, sorted by due date then severity (overdue and
    soon-due items first, blocking ahead of warning within the same due
    date), matching DESIGN.md §3.8's layout."""

    items: dict[str, OpenItem] = {}

    for entity_id, entity in entities.items():
        entity_type = entity_type_for(entity_id)

        if entity_type is EntityType.UNKNOWN and entity.status == "OPEN":
            if entity.blocking:
                items[entity_id] = _open_item_for(entity_id, entity, "blocking_unknown")
            elif entity.route == "RESEARCH":
                items[entity_id] = _open_item_for(entity_id, entity, "research_queued")
            continue

        if entity_type is EntityType.DECISION and entity.status in ("OPEN", "DECIDE_LATER"):
            items[entity_id] = _open_item_for(entity_id, entity, "decision")
            continue

        if entity_type is EntityType.ASSUMPTION and entity.impact == "HIGH" and entity.status == "PROPOSED":
            items[entity_id] = _open_item_for(entity_id, entity, "unconfirmed_high_assumption")
            continue

    def sort_key(item: OpenItem) -> tuple[datetime, int]:
        # Ascending due date already puts overdue items (the earliest dates)
        # above merely-due ones; items with no due date sort last via the
        # placeholder. Blocking breaks a tie with warning-severity items
        # sharing the same due date (including "no due date").
        due = item.due_date if item.due_date is not None else _NO_DUE_DATE
        return (due, 0 if item.severity == "blocking" else 1)

    return sorted(items.values(), key=sort_key)
