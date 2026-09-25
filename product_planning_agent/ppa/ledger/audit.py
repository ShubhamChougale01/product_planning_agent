"""Audit log — every tool invocation, inputs stored by reference (DESIGN.md
§2.16, §2.19.1, S2.6).

Two logs, deliberately separate: `events.ndjson` stays semantic and
replayable, the source of truth for what the ledger *is*; `audit.ndjson` is
observability for what the agent *did* — every tool call including reads,
rejections and retries, none of which ever becomes an event. This is what
lets `ppa why <id>` (S13.4) eventually answer not just what changed but
which agent changed it, under which tool, in which state, and why.

`inputs_ref` is a content hash plus an optional entity pointer, **never the
raw tool input** — so a value that happened to slip past T06's inbound
scanner does not get a second, unredacted home here. The raw `inputs` dict
passed to `record_audit` exists only for the duration of `hash_inputs`'s own
call; it is never stored on `AuditRecord` and never written to disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ppa.results.categories import ErrorCategory

_locks_guard = threading.Lock()
_path_locks: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[key] = lock
        return lock


AuditOperation = Literal["read", "write", "reject", "retry"]
"""The task's own wording: "every tool invocation, including reads,
rejections and retries" — plus the ordinary case, a write that succeeds."""


class InputsRef(BaseModel):
    """A content hash and, where the call concerns one entity, its id —
    never the raw payload."""

    model_config = ConfigDict(extra="forbid")

    input_hash: str
    entity_id: str | None = None


class AuditResult(BaseModel):
    """`result(success|category|code)` from the task's own record shape."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    category: ErrorCategory | None = None
    code: str | None = None

    @model_validator(mode="after")
    def _category_and_code_only_on_failure(self) -> "AuditResult":
        if self.success and (self.category is not None or self.code is not None):
            raise ValueError("success=True must not carry an error category/code")
        if not self.success and (self.category is None or self.code is None):
            raise ValueError("success=False must carry both a category and a code")
        return self


class AuditRecord(BaseModel):
    """One line in `audit.ndjson`:

    `agent · tool · operation · ts · workflow_state · inputs_ref · reason ·
    result(success|category|code) · validation_layer_failed · retry_attempt ·
    ledger_version_before · ledger_version_after · txn_id`
    """

    model_config = ConfigDict(extra="forbid")

    agent: str
    tool: str
    operation: AuditOperation
    ts: datetime
    workflow_state: str
    inputs_ref: InputsRef
    reason: str
    result: AuditResult
    validation_layer_failed: str | None = None
    retry_attempt: int = Field(default=0, ge=0)
    ledger_version_before: int = Field(ge=0)
    ledger_version_after: int = Field(ge=0)
    txn_id: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_is_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason is required and cannot be empty or whitespace")
        return v


def hash_inputs(payload: dict[str, Any]) -> str:
    """A deterministic content hash of `payload` — the only trace of a tool's
    raw input this module ever produces. Same payload, same hash, regardless
    of key order; different payload, a different hash, so `ppa why` can at
    least confirm "was this the same input as last time" without ever
    reconstructing what it was."""

    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_audit(
    *,
    agent: str,
    tool: str,
    operation: AuditOperation,
    workflow_state: str,
    inputs: dict[str, Any] | None,
    reason: str,
    result: AuditResult,
    path: Path | str,
    entity_id: str | None = None,
    validation_layer_failed: str | None = None,
    retry_attempt: int = 0,
    ledger_version_before: int = 0,
    ledger_version_after: int = 0,
    txn_id: str | None = None,
    ts: datetime | None = None,
) -> AuditRecord:
    """Build one `AuditRecord` and append it to `path` (a project's
    `audit.ndjson`). `inputs` is hashed by `hash_inputs` and then discarded —
    it is never attached to the record that gets constructed or written."""

    record = AuditRecord(
        agent=agent,
        tool=tool,
        operation=operation,
        ts=ts if ts is not None else datetime.now(timezone.utc),
        workflow_state=workflow_state,
        inputs_ref=InputsRef(input_hash=hash_inputs(inputs or {}), entity_id=entity_id),
        reason=reason,
        result=result,
        validation_layer_failed=validation_layer_failed,
        retry_attempt=retry_attempt,
        ledger_version_before=ledger_version_before,
        ledger_version_after=ledger_version_after,
        txn_id=txn_id,
    )
    _append(record, Path(path))
    return record


def _append(record: AuditRecord, path: Path) -> None:
    lock = _lock_for(path)
    line = record.model_dump_json() + "\n"
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as fh:
            fh.write(line.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())


def read_audit_records(path: Path | str) -> list[AuditRecord]:
    """Every record in `path`, in log order. Read-only — `audit.ndjson` is
    observability, never replayed into ledger state (that is exactly what
    distinguishes it from `events.ndjson`)."""

    path = Path(path)
    if not path.exists():
        return []
    records: list[AuditRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                records.append(AuditRecord.model_validate_json(line))
    return records
