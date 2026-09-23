"""Event envelope and transaction markers (DESIGN.md §1.8, §2.14, S1.3).

The event log is the source of truth; every entity file T07's materializer
writes is a projection of this stream, never the other way round. Getting the
envelope right here means version history, change reasons, audit attribution
and crash recovery all fall out for free later — retrofitting any one of them
onto an already-running log is much more expensive than declaring it now.

This module owns the *shape* of an event and the full list of event types.
Writing events to disk, locking, monotonic ID allocation and secret scanning
belong to T06 (`ppa/ledger/store.py`, `ppa/ledger/secrets.py`), not here.

Transactions are markers, not a separate mechanism: `txn.begin` opens one,
ordinary events carry its `txn_id` while it's open, `txn.commit` closes it.
A `txn_id` with no matching `txn.commit` is ignored wholesale by the
materializer (T07) — that is the entire rollback story. Nothing invalid is
ever committed, so nothing ever needs to be undone.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any, Literal


class EventType(str, Enum):
    """One member per state change T02's entity set can undergo, plus the
    handful of system/meta events (transactions, approvals, anomalies) that
    don't belong to any single entity.

    Four members do not appear in T03's own enumeration and were added to
    close a real gap found while checking this list against
    `ppa/ledger/transitions.py` (the same kind of gap decision #7 found in
    T02, logged the same way rather than fixed silently):

    - `ASSUMPTION_SUPERSEDED` — `Assumption` can reach `SUPERSEDED`
      (`transitions.py`), but the task's list only gave assumptions
      created/confirmed/rejected/modified. Without this, a real assumption
      status change would have no event type to record it under.
    - `DECISION_SUPERSEDED` — same gap for `Decision`, which can also reach
      `SUPERSEDED`.
    - `QUESTION_REPLACED` — `QuestionAnswer` can reach `REPLACED` from either
      `PENDING` or `ANSWERED` (decision #7's confirmed enum); the task's list
      only gave `question.asked` and `answer.recorded`.
    - `RESEARCH_REPLACED` — `ResearchFinding` can reach `REPLACED`; the task's
      list only gave `research.recorded`.

    `Risk` gets no event types here on purpose: T02 declared it "not written
    in v1" and no Discovery tool creates one, so it has no state changes to
    map yet. Revisit when Planning lands in v2.
    """

    PROJECT_CREATED = "project.created"

    REQUIREMENT_CREATED = "requirement.created"
    REQUIREMENT_REVISED = "requirement.revised"
    REQUIREMENT_CONFIRMED = "requirement.confirmed"
    REQUIREMENT_REJECTED = "requirement.rejected"
    REQUIREMENT_SUPERSEDED = "requirement.superseded"

    ASSUMPTION_CREATED = "assumption.created"
    ASSUMPTION_CONFIRMED = "assumption.confirmed"
    ASSUMPTION_REJECTED = "assumption.rejected"
    ASSUMPTION_MODIFIED = "assumption.modified"
    ASSUMPTION_SUPERSEDED = "assumption.superseded"

    DECISION_OPENED = "decision.opened"
    DECISION_DEFERRED = "decision.deferred"
    DECISION_DECIDED = "decision.decided"
    DECISION_SUPERSEDED = "decision.superseded"

    UNKNOWN_RECORDED = "unknown.recorded"
    UNKNOWN_CLASSIFIED = "unknown.classified"
    UNKNOWN_RESOLVED = "unknown.resolved"
    UNKNOWN_CONVERTED = "unknown.converted"

    QUESTION_ASKED = "question.asked"
    QUESTION_REPLACED = "question.replaced"
    ANSWER_RECORDED = "answer.recorded"

    RESEARCH_RECORDED = "research.recorded"
    RESEARCH_REPLACED = "research.replaced"

    COVERAGE_RECOMPUTED = "coverage.recomputed"

    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REVOKED = "approval.revoked"

    TXN_BEGIN = "txn.begin"
    TXN_COMMIT = "txn.commit"
    TXN_ABORT = "txn.abort"

    ANOMALY_LOOP_CAP_REACHED = "anomaly.loop_cap_reached"
    USER_FORCED_READY = "user.forced_ready"


EVENT_ID_PATTERN = re.compile(r"EVT-\d{3,}")
"""Shape only. Allocation and strict monotonicity are T07's job
(`ppa/ledger/materialize.py`) and T06's job under the write lock
(`ppa/ledger/store.py`) — this module just refuses an obviously malformed id."""


class Event(BaseModel):
    """One line in the append-only log (DESIGN.md §1.8, §2.14).

    `reason` is required and non-empty everywhere, including system-generated
    events — "why did this happen" must always be answerable by reading the
    log, never inferred after the fact.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    ts: datetime
    type: EventType
    entity_id: str | None
    actor_id: str
    actor_role: Literal["agent", "user"]
    agent_name: str | None
    workflow_state: str
    txn_id: str | None
    source: str
    reason: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    session_id: str

    @field_validator("event_id")
    @classmethod
    def _event_id_matches_shape(cls, v: str) -> str:
        if not EVENT_ID_PATTERN.fullmatch(v):
            raise ValueError(f"event_id must look like EVT-nnnnnn (>=3 digits), got {v!r}")
        return v

    @field_validator("ts")
    @classmethod
    def _ts_is_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("ts must be timezone-aware — naive datetimes are rejected")
        return v

    @field_validator("reason")
    @classmethod
    def _reason_is_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason is required and cannot be empty or whitespace")
        return v
