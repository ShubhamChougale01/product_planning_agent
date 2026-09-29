"""The status board — progress AND open items, one surface (T31,
DESIGN.md §3.8, §1.15, S10.3-S10.4).

**"The model contributes nothing to it, which is what makes the numbers
trustworthy."** Every number here is folded straight from `entities` (a
`ppa.ledger.materialize.current_entities` snapshot) through engines already
built and proven elsewhere in this codebase — `ppa/engines/coverage.py`,
`ppa/engines/readiness.py`, `ppa/engines/open_items.py`, `ppa/engines/dates.py`
— plus two small event-log folds this module owns directly (which session
this is, how many rounds have run, which `DiscoveryMode` the project is
currently in). Nothing here calls a model, formats a model's prose, or
accepts a caller-supplied number for anything an engine can derive.

`status` and `--items` are **one command, not two concepts** (§1.15):
`render_status_board` draws the whole board; `render_open_items` draws just
the "Readiness" section plus the due/overdue line — the same data, filtered,
never a second computation.

**Externally-owned items are visually distinct from user-owned ones**: every
line that names an owner renders `owner: you` for `owner_type == "user"` and
`owner: client` for `owner_type == "external"` — never the same word for both.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from ppa.config.areas import AREA_KEYS
from ppa.config.profiles import UserProfile, critical_areas
from ppa.engines.coverage import compute_coverage
from ppa.engines.dates import due_within, is_overdue
from ppa.engines.open_items import collect_open_items
from ppa.engines.readiness import Blocker, check_readiness
from ppa.ledger.audit import AuditRecord, read_audit_records
from ppa.ledger.models import BaseEntity, EntityType, HistoryEntry
from ppa.ledger.project import Project

_BAR_WIDTH = 12
_DUE_SOON_WINDOW_DAYS = 3

_DONE_STATES = {"SUFFICIENT", "CONFIRMED"}
_AREA_MARKER = {
    "UNTOUCHED": "○",  # ○
    "PARTIAL": "◐",  # ◐
    "SUFFICIENT": "✓",  # ✓
    "CONFIRMED": "✓",  # ✓
}

_HARD_BLOCKER_ICON = "\U0001f534"  # 🔴
_SOFT_BLOCKER_ICON = "⚠"  # ⚠
_WARNING_ONLY_CONDITIONS = {"unconfirmed_high_assumption"}
"""Every other `Condition` in `ppa/engines/readiness.py` renders with the
hard-blocker icon; this one alone renders with the softer warning icon,
matching DESIGN.md §3.8's own example board — it is still a real blocker
(all seven conditions gate READY equally), the icon only signals a
different *kind* of gap to the reader, never a different severity in the
gate itself."""

_MODE_META_KEY = "discovery_mode"
"""Mirrors `ppa.agents.turn._MODE_META_KEY` — duplicated as a bare string
rather than imported, so this render module never has to import
`ppa.agents.turn` (and, transitively, the Claude Agent SDK) just to read one
project-meta key. Kept in sync by convention, the same way this module's own
docstring already states every number here is an engine fold, not a second
source of truth for what a mode even is."""


def _progress_bar(numerator: int, denominator: int, *, width: int = _BAR_WIDTH) -> str:
    if denominator <= 0:
        filled = 0
    else:
        filled = round(width * (numerator / denominator))
        filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _owner_label(owner_type: str | None) -> str | None:
    """`"owner: you"` vs `"owner: client"` — deliberately different words,
    never the same label with a parenthetical tacked on, so an externally-
    owned item reads as visually distinct at a glance, not just on close
    reading (this task's own Done-when box)."""

    if owner_type == "user":
        return "owner: you"
    if owner_type == "external":
        return "owner: client"
    return None


def _format_due(due: datetime | None) -> str | None:
    if due is None:
        return None
    return f"due {due:%b} {due.day}"


_MAX_TITLE_WIDTH = 24
"""Long enough for a real title, short enough that even the worst-case
blocker line (icon + entity id + title + owner + due, see `_blocker_line`)
still fits an 80-column terminal — this task's own Done-when box."""


def _truncate(text: str, *, width: int = _MAX_TITLE_WIDTH) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "…"


def _entity_title(entity: BaseEntity | None, fallback: str) -> str:
    if entity is None:
        return _truncate(fallback)
    title = getattr(entity, "question", None) or getattr(entity, "statement", None) or fallback
    return _truncate(title)


def _session_and_round_counts(events) -> tuple[int, int]:
    """`(session_number, round_count)` — the *current* session's ordinal
    (how many distinct `session_id`s have appeared so far, in first-seen
    order) and how many outer-loop rounds (committed `txn_id` groups) have
    run in total. Both are plain folds over `events.ndjson`, nothing more —
    see `ppa.orchestrator.context.rounds_from_events`, reused here rather
    than re-deriving round boundaries a second way."""

    from ppa.orchestrator.context import rounds_from_events

    seen: list[str] = []
    for event in events:
        if event.session_id not in seen:
            seen.append(event.session_id)
    session_number = len(seen) if seen else 1
    round_count = len(rounds_from_events(events))
    return session_number, round_count


def _current_mode_label(project: Project) -> str:
    from ppa.ledger.store import read_project_meta

    meta = read_project_meta(project.events_path)
    return meta.get(_MODE_META_KEY, "INTAKE")


def gate_inputs(project: Project) -> tuple[bool, set[str], list[dict]]:
    """`(review_approved, confirmed_areas, unresolved_conflicts)` — the same
    three readiness-gate inputs `ppa.orchestrator.loop.run_turn` threads
    through, folded here straight from the event log so the board never
    needs a caller to supply them (decision #19's own resolution, T30)."""

    from ppa.agents.modes.change import unresolved_conflicts_from_events
    from ppa.agents.modes.review import readiness_gate_inputs

    review_approved, confirmed_areas = readiness_gate_inputs(project.events_path)
    unresolved = unresolved_conflicts_from_events(project.events_path)
    return review_approved, confirmed_areas, unresolved


def _blocker_line(blocker: Blocker, entities: Mapping[str, BaseEntity]) -> str:
    entity = entities.get(blocker.entity_id) if blocker.entity_id else None
    icon = _SOFT_BLOCKER_ICON if blocker.condition in _WARNING_ONLY_CONDITIONS else _HARD_BLOCKER_ICON

    if blocker.condition == "unconfirmed_high_assumption" and entity is not None:
        detail = f'"{_truncate(entity.statement)}" — HIGH impact, unconfirmed'
    elif entity is not None:
        title = _entity_title(entity, blocker.description)
        suffix = " (blocking)" if getattr(entity, "blocking", False) else ""
        detail = f"{title}{suffix}"
    else:
        detail = _truncate(blocker.description, width=70)

    prefix = f"{blocker.entity_id}  " if blocker.entity_id else ""
    tail_parts = [p for p in (_owner_label(getattr(entity, "owner_type", None)), _format_due(getattr(entity, "expected_decision_date", None))) if p]
    tail = ("  " + "  ".join(tail_parts)) if tail_parts else ""
    return f"  {icon}  {prefix}{detail}{tail}"


def _ledger_section(entities: Mapping[str, BaseEntity]) -> list[str]:
    requirements = [e for eid, e in entities.items() if _type_of(eid) is EntityType.REQUIREMENT]
    assumptions = [e for eid, e in entities.items() if _type_of(eid) is EntityType.ASSUMPTION]
    decisions = [e for eid, e in entities.items() if _type_of(eid) is EntityType.DECISION]
    unknowns = [e for eid, e in entities.items() if _type_of(eid) is EntityType.UNKNOWN]

    lines = ["Ledger"]

    req_parts = []
    for status, label in (("CONFIRMED", "confirmed"), ("PROPOSED", "proposed"), ("REJECTED", "rejected"), ("SUPERSEDED", "superseded")):
        n = sum(1 for r in requirements if r.status == status)
        if n:
            req_parts.append(f"{n} {label}")
    req_detail = " · ".join(req_parts) if req_parts else "none yet"
    lines.append(f"  {'Requirements':<13} {len(requirements):>3}   ({req_detail})")

    confirmed_asm = sum(1 for a in assumptions if a.status == "CONFIRMED")
    awaiting_asm = [a for a in assumptions if a.status == "PROPOSED"]
    high_awaiting = sum(1 for a in awaiting_asm if a.impact == "HIGH")
    asm_detail = f"{confirmed_asm} confirmed · {len(awaiting_asm)} awaiting review"
    if high_awaiting:
        asm_detail += f" {_SOFT_BLOCKER_ICON} {high_awaiting} HIGH impact"
    lines.append(f"  {'Assumptions':<13} {len(assumptions):>3}   ({asm_detail})")

    decided = sum(1 for d in decisions if d.status == "DECIDED")
    decide_later = sum(1 for d in decisions if d.status == "DECIDE_LATER")
    open_decisions = [d for d in decisions if d.status == "OPEN"]
    blocking_open = sum(1 for d in open_decisions if d.blocking)
    dec_detail = f"{decided} decided · {decide_later} decide-later · {len(open_decisions)} open"
    if blocking_open:
        dec_detail += f" {_HARD_BLOCKER_ICON} blocking"
    lines.append(f"  {'Decisions':<13} {len(decisions):>3}   ({dec_detail})")

    blocking_unk = sum(1 for u in unknowns if u.status == "OPEN" and u.blocking)
    research_unk = sum(1 for u in unknowns if u.status == "OPEN" and not u.blocking and u.route == "RESEARCH")
    unk_detail = f"{blocking_unk} blocking · {research_unk} research"
    lines.append(f"  {'Unknowns':<13} {len(unknowns):>3}   ({unk_detail})")

    return lines


def _type_of(entity_id: str):
    from ppa.ledger.materialize import entity_type_for

    return entity_type_for(entity_id)


def _coverage_rows(entities: Mapping[str, BaseEntity], profile: UserProfile) -> list[str]:
    coverage = compute_coverage(entities, profile)
    critical = critical_areas(profile)
    other = [a for a in AREA_KEYS if a not in critical]
    critical_ordered = [a for a in AREA_KEYS if a in critical]

    lines: list[str] = []

    done = [a for a in critical_ordered if coverage[a].value in _DONE_STATES]
    gap = [a for a in critical_ordered if coverage[a].value not in _DONE_STATES]

    critical_line = "  critical  " + " ".join(f"{_AREA_MARKER[coverage[a].value]} {a}" for a in done)
    lines.append(critical_line.rstrip())
    for area in gap:
        state = coverage[area].value
        lines.append(f"            {_AREA_MARKER[state]} {area} ({state})")

    other_line = "  other     " + " ".join(f"{_AREA_MARKER[coverage[a].value]} {a}" for a in other)
    lines.append(other_line.rstrip())

    return lines


def render_status_board(
    project: Project,
    entities: Mapping[str, BaseEntity],
    *,
    now: datetime | None = None,
) -> str:
    """The whole board — DESIGN.md §3.8's layout, drawn entirely from
    `project`/`entities` and the engines already proven elsewhere in this
    codebase. Critical coverage is reported as the headline fraction, total
    areas secondary, per this task's own instruction."""

    from ppa.orchestrator.context import read_events

    now = now or datetime.now(timezone.utc)
    profile = project.profile
    events = read_events(project.events_path)
    session_number, round_count = _session_and_round_counts(events)
    mode = _current_mode_label(project)

    critical = critical_areas(profile)
    coverage = compute_coverage(entities, profile)
    crit_sufficient = sum(1 for a in critical if coverage[a].value in _DONE_STATES)
    all_sufficient = sum(1 for a in AREA_KEYS if coverage[a].value in _DONE_STATES)

    header_left = f"PLANNING STATUS — {project.name}"
    header_right = f"Session {session_number} · {now:%Y-%m-%d %H:%M}"
    pad = max(2, 78 - len(header_left) - len(header_right))
    lines = [header_left + (" " * pad) + header_right, ""]

    bar = _progress_bar(crit_sufficient, len(critical))
    lines.append(
        f"Coverage  {crit_sufficient}/{len(critical)} critical {bar}   "
        f"all areas {all_sufficient}/{len(AREA_KEYS)}   Round {round_count} · {mode}"
    )
    lines.append("")
    lines.extend(_coverage_rows(entities, profile))
    lines.append("")
    lines.extend(_ledger_section(entities))
    lines.append("")
    lines.extend(_readiness_section(project, entities, profile, now=now))

    return "\n".join(lines)


def _readiness_section(
    project: Project,
    entities: Mapping[str, BaseEntity],
    profile: UserProfile,
    *,
    now: datetime,
) -> list[str]:
    review_approved, confirmed_areas, unresolved_conflicts = gate_inputs(project)
    ready, blockers = check_readiness(
        entities,
        profile,
        confirmed_areas=confirmed_areas,
        unresolved_conflicts=unresolved_conflicts,
        review_approved=review_approved,
    )

    lines: list[str] = []
    if ready:
        lines.append("Readiness   READY")
    else:
        lines.append(f"Readiness   NOT READY — {len(blockers)} blocker{'s' if len(blockers) != 1 else ''}")
        for blocker in blockers:
            lines.append(_blocker_line(blocker, entities))

    lines.append("")
    open_items = collect_open_items(entities)
    due_soon = due_within(open_items, _DUE_SOON_WINDOW_DAYS, now)
    overdue = [item for item in open_items if is_overdue(item, now)]
    lines.append(f"Open items due within {_DUE_SOON_WINDOW_DAYS} days: {len(due_soon)}      Overdue: {len(overdue)}")

    return lines


def render_open_items(
    project: Project,
    entities: Mapping[str, BaseEntity],
    *,
    now: datetime | None = None,
) -> str:
    """`--items` — the same "Readiness" section `render_status_board` draws,
    on its own, plus the full open-items list beneath it (entity id, title,
    owner, due date), so filtering to just the list never loses the detail
    a caller would otherwise have to cross-reference the full board for."""

    now = now or datetime.now(timezone.utc)
    profile = project.profile
    lines = _readiness_section(project, entities, profile, now=now)

    lines.append("")
    lines.append("Open items")
    open_items = collect_open_items(entities)
    if not open_items:
        lines.append("  (none)")
    for item in open_items:
        entity = entities.get(item.entity_id)
        tail_parts = [p for p in (_owner_label(item.owner_type), _format_due(item.due_date)) if p]
        tail = ("  " + "  ".join(tail_parts)) if tail_parts else ""
        marker = _HARD_BLOCKER_ICON if item.blocking else _SOFT_BLOCKER_ICON
        lines.append(f"  {marker}  {item.entity_id}  {_truncate(item.title)}{tail}")

    return "\n".join(lines)


def render_history(entity_id: str, entities: Mapping[str, BaseEntity]) -> str:
    """`ppa history <id>` — the version trail: every `HistoryEntry` an
    entity carries, oldest first, purely from `entities` (no event-log read
    needed — `BaseEntity.history` already accumulates every field change,
    T02's own shape)."""

    entity = entities.get(entity_id)
    if entity is None:
        return f"No entity {entity_id!r} found in this project's ledger."

    history: list[HistoryEntry] = entity.history
    lines = [f"# {entity_id} — version trail", ""]
    if not history:
        lines.append("No recorded changes yet — still at its original version.")
        return "\n".join(lines)

    for entry in history:
        reason = f" — {entry.reason}" if entry.reason else ""
        lines.append(
            f"- {entry.changed_at:%Y-%m-%d %H:%M} · {entry.field}: "
            f"{entry.old_value!r} → {entry.new_value!r} (by {entry.changed_by}){reason}"
        )
    return "\n".join(lines)


def render_provenance(entity_id: str, audit_path) -> str:
    """The other half of `ppa why <id>`'s own Done-when box: **"reports
    agent, tool and workflow state, not just what changed."** `render_why`
    (`ppa.render.guidance_card`, T28) already answers what changed and why
    for a Decision, from ledger content alone; this answers *who did it,
    with which tool, in which workflow state* — folded from `audit.ndjson`,
    the log this codebase built exactly for that question (`ppa.ledger.
    audit`'s own module docstring)."""

    records: list[AuditRecord] = [
        r for r in read_audit_records(audit_path) if r.inputs_ref.entity_id == entity_id
    ]
    lines = ["", "**Provenance (agent · tool · workflow state):**"]
    if not records:
        lines.append("No audit record references this entity directly.")
        return "\n".join(lines)

    for record in records:
        outcome = "ok" if record.result.success else f"{record.result.category}/{record.result.code}"
        lines.append(
            f"- {record.ts:%Y-%m-%d %H:%M} · {record.agent} used `{record.tool}` "
            f"({record.operation}) in {record.workflow_state} — {outcome} — {record.reason}"
        )
    return "\n".join(lines)
