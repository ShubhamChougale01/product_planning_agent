"""Digest projection — a bounded, always-fresh view of ledger state
(DESIGN.md §1.11, S3.1-S3.2).

By round five a real project has 20+ requirements, 10+ assumptions, a Q&A
log and research findings — dumping all of it into every turn's context is
expensive and degrades attention. Every agent prompt from T23 onward is
written against this shape, so it has to exist before any agent does, not be
bolted on as a later optimization.

The asymmetry that makes it useful: things that *block* progress are shown
in full, always — omitting a blocking item or an unconfirmed HIGH-impact
assumption here is a correctness bug, never a size tradeoff. Everything else
gets a title; detail is fetched on demand via `query_ledger` (T15+).

**Coverage state is not computed here.** `ppa/engines/coverage.py` (T10) is
the one place an area's state may be derived — "nothing outside this engine
may set an area's state," and that includes reading it into existence a
second, independent way. This module only renders whatever `coverage`
mapping it is handed; a caller built before T10 exists can pass `{}` (every
area then reads as `UNTOUCHED`) without this module needing to know that
engine exists yet.

**"Due within 3 days" reuses T12's own engines** (`ppa/engines/open_items.py`
`collect_open_items` + `ppa/engines/dates.py` `due_within`) rather than
re-deriving open items or date-window math here a second time — this module
was written before T12 existed and originally hand-rolled a narrower,
Decision-only version of this section; see `blockers.md` decision #21 for
why it was replaced rather than left to drift from the real engines.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from ppa.config.areas import AREA_KEYS, AREAS_BY_KEY, AreaStatus
from ppa.config.profiles import critical_areas
from ppa.engines.dates import due_within
from ppa.engines.open_items import collect_open_items
from ppa.ledger.events import EventType
from ppa.ledger.materialize import current_entities, entity_type_for
from ppa.ledger.models import BaseEntity, EntityType
from ppa.ledger.project import Project

_UNCONFIRMED_ASSUMPTION_STATUS = "PROPOSED"
_DUE_SOON_WINDOW_DAYS = 3


def estimate_tokens(text: str) -> int:
    """~4 characters per token — the standard estimation heuristic absent an
    actual tokenizer dependency. Good enough to budget-check a digest,
    nowhere near precise enough to bill against."""

    return max(1, len(text) // 4)


def _title_for(entity_id: str, entity: BaseEntity) -> str:
    text = (
        getattr(entity, "statement", None)
        or getattr(entity, "question", None)
        or getattr(entity, "text", None)
        or "(no title field on this entity type)"
    )
    return f"{entity_id}: {text}"


def _full_dump(entity_id: str, entity: BaseEntity) -> str:
    return f"{entity_id} [FULL]: {json.dumps(entity.model_dump(mode='json'), sort_keys=True)}"


def _is_open_blocker(entity_id: str, entity: BaseEntity) -> bool:
    """A blocking Unknown still `OPEN`, or a blocking Decision not yet
    `DECIDED` — the two entity types that carry a `blocking` field at all."""

    entity_type = entity_type_for(entity_id)
    if entity_type is EntityType.UNKNOWN:
        return bool(entity.blocking) and entity.status == "OPEN"
    if entity_type is EntityType.DECISION:
        return bool(entity.blocking) and entity.status in {"OPEN", "DECIDE_LATER"}
    return False


def _is_unconfirmed_high_assumption(entity_id: str, entity: BaseEntity) -> bool:
    if entity_type_for(entity_id) is not EntityType.ASSUMPTION:
        return False
    return entity.impact == "HIGH" and entity.status == _UNCONFIRMED_ASSUMPTION_STATUS


def _seed_requirement(events_path: Path) -> str | None:
    """`project.created` is always the first line of a fresh project's
    `events.ndjson` (`ppa/ledger/project.py::create_project`), so this reads
    at most one line in the common case — a raw `json.loads`, not the full
    `Event` model, since nothing here needs the rest of the envelope."""

    if not events_path.exists():
        return None
    with events_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("type") == EventType.PROJECT_CREATED.value:
                after = data.get("after") or {}
                return after.get("seed_requirement")
    return None


def generate_digest(
    project: Project,
    entities: Mapping[str, BaseEntity],
    *,
    coverage: Mapping[str, AreaStatus | str] | None = None,
    round_number: int | None = None,
    now: datetime | None = None,
) -> str:
    """Render the bounded view every agent prompt is written against.

    `entities` is a materialized snapshot — `rebuild_all`'s own return shape
    (`ppa/ledger/materialize.py`). This function does no ledger I/O beyond
    the one small read needed for the seed requirement; freshness is
    `read_digest`'s job, below.
    """

    now = now or datetime.now(timezone.utc)
    coverage = coverage or {}
    critical = critical_areas(project.profile)

    lines: list[str] = []

    lines.append(f"# Project: {project.name} ({project.slug})")
    seed = _seed_requirement(project.events_path)
    if seed:
        lines.append(f"Seed requirement: {seed}")
    lines.append(f"Workflow state: {project.workflow_state}")
    lines.append(f"Round: {round_number if round_number is not None else 'not yet tracked'}")

    lines.append("")
    lines.append("## Coverage")
    critical_sufficient = 0
    for key in AREA_KEYS:
        state = coverage.get(key, AreaStatus.UNTOUCHED)
        state_label = state.value if isinstance(state, AreaStatus) else str(state)
        is_critical = key in critical
        if is_critical and state_label in ("SUFFICIENT", "CONFIRMED"):
            critical_sufficient += 1
        marker = "critical" if is_critical else "optional"
        lines.append(f"- {AREAS_BY_KEY[key].label} [{marker}]: {state_label}")
    lines.append(f"Critical coverage: {critical_sufficient}/{len(critical)}")

    blocking_items: list[tuple[str, BaseEntity]] = []
    unconfirmed_high: list[tuple[str, BaseEntity]] = []
    rest: list[tuple[str, BaseEntity]] = []
    for entity_id, entity in entities.items():
        if _is_open_blocker(entity_id, entity):
            blocking_items.append((entity_id, entity))
        elif _is_unconfirmed_high_assumption(entity_id, entity):
            unconfirmed_high.append((entity_id, entity))
        else:
            rest.append((entity_id, entity))

    lines.append("")
    lines.append(f"## Blocking items ({len(blocking_items)})")
    lines.extend(f"- {_full_dump(eid, e)}" for eid, e in blocking_items)
    if not blocking_items:
        lines.append("(none)")

    lines.append("")
    lines.append(f"## Unconfirmed HIGH-impact assumptions ({len(unconfirmed_high)})")
    lines.extend(f"- {_full_dump(eid, e)}" for eid, e in unconfirmed_high)
    if not unconfirmed_high:
        lines.append("(none)")

    lines.append("")
    lines.append("## Counts")
    counts: dict[tuple[str, str], int] = {}
    for entity_id, entity in entities.items():
        key = (entity_type_for(entity_id).value, entity.status)
        counts[key] = counts.get(key, 0) + 1
    for (etype, status), n in sorted(counts.items()):
        lines.append(f"- {etype} / {status}: {n}")

    lines.append("")
    lines.append(f"## Everything else ({len(rest)})")
    for entity_id, entity in sorted(rest, key=lambda pair: pair[0]):
        lines.append(f"- {_title_for(entity_id, entity)}")

    due_soon = due_within(collect_open_items(entities), _DUE_SOON_WINDOW_DAYS, now)
    lines.append("")
    lines.append(f"## Due within {_DUE_SOON_WINDOW_DAYS} days ({len(due_soon)})")
    lines.extend(f"- {item.entity_id}: {item.title}" for item in due_soon)
    if not due_soon:
        lines.append("(none)")

    return "\n".join(lines)


def read_digest(
    project: Project,
    *,
    coverage: Mapping[str, AreaStatus | str] | None = None,
    round_number: int | None = None,
    now: datetime | None = None,
) -> str:
    """Rebuild entity state fresh from `events.ndjson` and render the
    digest — the write-then-read freshness guarantee (S3.2) lives here: it
    never trusts an in-memory or previously materialized snapshot, only
    what the event log says right now. Deliberately uses `current_entities`,
    not `rebuild_all` — a digest read should never have the side effect of
    rewriting every entity file on disk."""

    entities = current_entities(project.events_path)
    return generate_digest(project, entities, coverage=coverage, round_number=round_number, now=now)
