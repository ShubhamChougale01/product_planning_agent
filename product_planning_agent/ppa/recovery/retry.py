"""Bounded retry with a per-operation budget (T32, DESIGN.md §2.14, §2.15,
S11.1-S11.4).

**Budget of 3 per operation, not global.** Each call to `retry_operation`
gets its own fresh budget — a batch of five operations retried through
`retry_batch` can spend up to 3 attempts on *each* of the five, never a
shared pool of 3 across all of them.

**Only `TRANSIENT` is retried.** Every other category (`VALIDATION`,
`BUSINESS`, `PERMISSION`, `NOT_IMPLEMENTED`) is `is_retryable=False`
(`ppa/results/categories.py`'s own fixed mapping) — resending an identical
`VALIDATION` failure would produce the identical failure, so this module
never tries.

**Exhaustion never returns a bare failure.** `retry_batch`'s own return
shape matches this task's own worked JSON exactly: `status`,
`attempted`/`successful`/`failed`, `error_category`, `partial_results`,
`next_action`. A caller (an Orchestrator, a subagent) always has something
to act on — the whole point DESIGN.md §2.14 states directly.
"""

from __future__ import annotations

import time
from typing import Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ppa.results.categories import ErrorCategory
from ppa.results.envelope import ToolResult

DEFAULT_RETRY_BUDGET = 3
"""DESIGN.md §2.14's own number, matching `ppa.orchestrator.loop.
DEFAULT_RETRY_BUDGET` — this module is the general-purpose version of the
same policy that module already applies at the orchestrator level."""

_BASE_BACKOFF_SECONDS = 0.01
"""A small base so tests exercising a full 3-attempt exhaustion run fast —
real backoff timing is governed by `retry_after_ms` when a server states
one; this is only the fallback when it doesn't."""


def _is_transient(result: ToolResult) -> bool:
    return not result.success and result.error is not None and result.error.category is ErrorCategory.TRANSIENT


def _backoff_seconds(attempt: int, result: ToolResult) -> float:
    """Honors `retry_after_ms` when the failure states one (DESIGN.md's own
    "exponential backoff honouring `retry_after_ms`"); otherwise a plain
    exponential fallback, doubling per attempt."""

    if result.error is not None and result.error.retry_after_ms is not None:
        return result.error.retry_after_ms / 1000
    return _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))


def retry_operation(
    operation: Callable[[], ToolResult],
    *,
    budget: int = DEFAULT_RETRY_BUDGET,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[ToolResult, int]:
    """Call `operation` until it succeeds, its failure isn't `TRANSIENT`, or
    `budget` attempts are spent — whichever comes first. Returns
    `(final_result, attempts_made)`; the caller decides what "exhausted"
    means for its own context (a bare `ToolResult` here, or folded into
    `retry_batch`'s own `PARTIAL_FAILURE` shape below)."""

    attempts = 0
    while True:
        result = operation()
        attempts += 1
        if result.success or not _is_transient(result) or attempts >= budget:
            return result, attempts
        sleep(_backoff_seconds(attempts, result))


class RetryBatchResult(BaseModel):
    """The worked `PARTIAL_FAILURE` JSON shape from `t32_transactions_
    retry_recovery.md`, verbatim. `attempted == successful + failed` always
    — one row per operation in the batch, not a running retry-attempt
    counter (each operation's own internal attempt count is not this
    field's concern; `partial_results` carries each operation's own final
    `ToolResult` for a caller that needs that detail)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["OK", "PARTIAL_FAILURE"]
    attempted: int
    successful: int
    failed: int
    error_category: ErrorCategory | None = None
    partial_results: list[ToolResult] = Field(default_factory=list)
    next_action: str | None = None


def retry_batch(
    operations: Sequence[Callable[[], ToolResult]],
    *,
    budget: int = DEFAULT_RETRY_BUDGET,
    sleep: Callable[[float], None] = time.sleep,
) -> RetryBatchResult:
    """Retry every operation in `operations` independently (its own fresh
    `budget`), then fold the results into one `RetryBatchResult`. `OK` iff
    every operation eventually succeeded; otherwise `PARTIAL_FAILURE`,
    carrying every operation's own final result and the last-seen failure
    category — never a bare, undifferentiated failure."""

    partial_results: list[ToolResult] = []
    successful = 0
    failed = 0
    last_category: ErrorCategory | None = None

    for operation in operations:
        result, _attempts = retry_operation(operation, budget=budget, sleep=sleep)
        partial_results.append(result)
        if result.success:
            successful += 1
        else:
            failed += 1
            if result.error is not None:
                last_category = result.error.category

    attempted = len(operations)
    if failed == 0:
        return RetryBatchResult(
            status="OK", attempted=attempted, successful=successful, failed=failed,
            partial_results=partial_results,
        )
    return RetryBatchResult(
        status="PARTIAL_FAILURE", attempted=attempted, successful=successful, failed=failed,
        error_category=last_category, partial_results=partial_results,
        next_action="ESCALATE_TO_ORCHESTRATOR",
    )
