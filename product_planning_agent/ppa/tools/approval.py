"""Approval gate for external/irreversible/bulk actions (T18, DESIGN.md
§2.19.2, S5.9).

Permission (T14) asks *may this agent call this tool*. Approval asks *does
the user want this specific batch executed*. Different questions, different
gates — a tool can be fully permitted and still refuse to run without a
matching approval.

Five steps (§2.19.2), of which this module implements the mechanics behind
three (`scope_hash`, the gate check, the events) and leaves two to the
caller (DRY RUN rendering is `render_dry_run`; PRESENT is a caller/CLI
concern, T31):

```
1 DRY RUN   render_dry_run() — nothing leaves the system
2 PRESENT   caller's job (T31's CLI)
3 APPROVE   grant_approval() -> approval.granted{scope_hash, story_ids[], ...}
4 EXECUTE   @requires_approval checks the approval covers THIS scope_hash
5 RECORD    caller's job — per-issue results, once Linear is real (v3)
```

`scope_hash` is computed over the exact story set (`compute_scope_hash`) —
edit, add or remove a story and the hash changes, so an approval that
covered the old set no longer covers the new one. Approvals expire (default
24h, `grant_approval`'s `ttl_hours`) so a stale one from an earlier session
can never be replayed.

**No agent is ever granted a tool to call `grant_approval` itself** — check
`ppa/agents/registry.py::GRANTS` for any agent and note the absence. This is
deliberate: approval is the *user's* decision, not something an agent can
manufacture for itself by calling a tool. `grant_approval`/`revoke_approval`
are plain functions for the CLI (T31) or an escalation flow to call, never
MCP-registered tools.

**No dedicated `Approval` entity type.** `approval.granted`/`approval.
revoked` are system/meta events (the same category as `txn.*`,
`coverage.recomputed`) — they carry no `entity_id` and are never
materialized into `entities/` alongside the seven real ledger entities
(T02). `current_approval` folds them itself, the same "last write wins"
principle `ppa/ledger/materialize.py` uses for real entities, just scoped
to these two event types instead of an id.
"""

from __future__ import annotations

import functools
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ConfigDict

from ppa.ledger.events import Event, EventType
from ppa.ledger.store import append_event
from ppa.results.categories import CATEGORY_RULES, ErrorCategory
from ppa.results.envelope import ErrorInfo, ToolResult

_DEFAULT_TTL_HOURS = 24


class Approval(BaseModel):
    """One granted, not-yet-revoked approval — the currently active one, per
    `current_approval`. Never written to `entities/`; folded on demand from
    `approval.granted`/`approval.revoked` events."""

    model_config = ConfigDict(extra="forbid")

    scope_hash: str
    story_ids: list[str]
    granted_by: str
    granted_at: datetime
    expires_at: datetime


def compute_scope_hash(story_ids: list[str], payload: dict[str, Any] | None = None) -> str:
    """Deterministic hash over the exact scope being approved — same story
    set (and, optionally, the same rendered payload) in, same hash out,
    regardless of list order. Anything that changes what would actually be
    created must change this hash."""

    canonical = json.dumps({"story_ids": sorted(story_ids), "payload": payload or {}}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_dry_run(story_ids: list[str], payload: dict[str, Any] | None = None) -> str:
    """Step 1 — render exactly what would be created. Nothing leaves the
    system: this is a pure string, no I/O, no network call."""

    lines = [f"DRY RUN — would create {len(story_ids)} Linear issue(s). Nothing leaves the system."]
    lines.extend(f"  - {sid}" for sid in story_ids)
    if payload:
        lines.append(f"  payload: {json.dumps(payload, sort_keys=True, default=str)}")
    return "\n".join(lines)


def _read_all_events(events_path: Path) -> list[Event]:
    if not events_path.exists():
        return []
    events: list[Event] = []
    with events_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                events.append(Event.model_validate_json(line))
    return events


def grant_approval(
    events_path: Path | str,
    *,
    scope_hash: str,
    story_ids: list[str],
    granted_by: str,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    reason: str = "batch approved",
    now: datetime | None = None,
    ttl_hours: int = _DEFAULT_TTL_HOURS,
) -> str:
    """Step 3 — record `approval.granted`. Returns the appended event's id."""

    ts = now or datetime.now(timezone.utc)
    expires_at = ts + timedelta(hours=ttl_hours)
    after = dict(
        scope_hash=scope_hash, story_ids=list(story_ids), granted_by=granted_by,
        granted_at=ts.isoformat(), expires_at=expires_at.isoformat(),
    )
    return append_event(
        dict(
            ts=ts, type=EventType.APPROVAL_GRANTED, entity_id=None, actor_id=actor_id, actor_role="user",
            agent_name=None, workflow_state=workflow_state, txn_id=None, source="approval_gate",
            reason=reason, before=None, after=after, session_id=session_id,
        ),
        events_path,
    )


def revoke_approval(
    events_path: Path | str,
    *,
    actor_id: str,
    session_id: str,
    workflow_state: str = "DISCOVERY",
    reason: str = "approval revoked",
    now: datetime | None = None,
) -> str:
    """Record `approval.revoked` — `current_approval` treats every grant at
    or before this event as inactive again, until a later grant supersedes it."""

    ts = now or datetime.now(timezone.utc)
    return append_event(
        dict(
            ts=ts, type=EventType.APPROVAL_REVOKED, entity_id=None, actor_id=actor_id, actor_role="user",
            agent_name=None, workflow_state=workflow_state, txn_id=None, source="approval_gate",
            reason=reason, before=None, after={"revoked_at": ts.isoformat()}, session_id=session_id,
        ),
        events_path,
    )


def current_approval(events_path: Path | str) -> Approval | None:
    """The currently active approval, or `None` — folded from the event log
    itself, never cached, the same freshness guarantee `read_digest` (T09)
    gives ledger state."""

    events = _read_all_events(Path(events_path))
    active: Approval | None = None
    for event in events:
        if event.type == EventType.APPROVAL_GRANTED:
            active = Approval.model_validate(event.after)
        elif event.type == EventType.APPROVAL_REVOKED:
            active = None
    return active


def _error(category: ErrorCategory, code: str, description: str, context: dict[str, Any] | None = None) -> ToolResult:
    rule = CATEGORY_RULES[category]
    return ToolResult(
        success=False,
        error=ErrorInfo(
            category=category,
            code=code,
            is_retryable=bool(rule["is_retryable"]),
            recommended_action=rule["recommended_action"],  # type: ignore[arg-type]
            description=description,
            context=context or {},
        ),
    )


ScopeFn = Callable[[str, dict[str, Any]], "tuple[str, list[str]] | None"]
F = TypeVar("F", bound=Callable[..., ToolResult])


def requires_approval(scope_fn: ScopeFn) -> Callable[[F], F]:
    """Step 4 — the gate itself. `scope_fn(operation, kwargs)` returns
    `(scope_hash, story_ids)` when `operation` needs a gate check, or
    `None` when it doesn't (e.g. a read-only or non-creating operation on
    the same tool). Decorates a `(operation, project, **kwargs) ->
    ToolResult` writer — any external/irreversible tool must declare this,
    per the module docstring."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(operation: str, project: Any, **kwargs: Any) -> ToolResult:
            scoped = scope_fn(operation, kwargs)
            if scoped is not None:
                scope_hash, story_ids = scoped
                now = kwargs.get("now") or datetime.now(timezone.utc)
                approval = current_approval(project.events_path)
                if approval is None:
                    return _error(
                        ErrorCategory.BUSINESS, "APPROVAL_REQUIRED",
                        f"{fn.__name__}({operation}): no approval on record for this batch of {len(story_ids)} story ids",
                        context={"story_ids": story_ids},
                    )
                if now > approval.expires_at:
                    return _error(
                        ErrorCategory.BUSINESS, "APPROVAL_EXPIRED",
                        f"{fn.__name__}({operation}): approval expired at {approval.expires_at.isoformat()}, now {now.isoformat()}",
                    )
                if approval.scope_hash != scope_hash:
                    return _error(
                        ErrorCategory.BUSINESS, "APPROVAL_SCOPE_MISMATCH",
                        f"{fn.__name__}({operation}): approval scope_hash does not match this exact story set — "
                        "the set changed since approval, re-approve before retrying",
                    )
            return fn(operation, project, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
